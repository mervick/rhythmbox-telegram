# rhythmbox-telegram
# Copyright (C) 2023-2025 Andrey Izman <izmanw@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import rb
import json
from gi.repository import RB
from gi.repository import GObject, Gtk, Gio, GLib
from gi.repository import Peas, PeasGtk # noqa
from loader import AudioDownloader, AudioTempLoader
from telegram_search import TelegramSearchEntryType, TelegramSearchSource
from telegram_source import TelegramSource
from telegram_client import TelegramApi, TelegramAuthError
from prefs import TelegramPrefs  # import TelegramPrefs is REQUIRED for showing settings page  # noqa
from account import Account, KEY_CHANNELS, KEY_PAGE_GROUP, KEY_TOP_PICKS_COLUMN, KEY_IN_LIBRARY_COLUMN
from account import KEY_AUDIO_VISIBILITY, VAL_AV_ALL, VAL_AV_VISIBLE, VAL_AV_DUAL, VAL_AV_HIDDEN
from telegram_entry import TelegramEntryType
from common import get_location_data, show_error, to_location
from columns import TopPicks, InLibraryColumn
from storage import Audio, VISIBILITY_ALL, VISIBILITY_VISIBLE, VISIBILITY_HIDDEN


VERSION = "1.3.0"

def show_source(source_list):
    for source in source_list:
        source.show_thyself()

def hide_source(source_list):
    for source in source_list:
        source.hide_thyself()

def delete_source(source_list):
    for source in source_list:
        source.deactivate()
        source.delete_thyself()


class TelegramPlugin(GObject.GObject, Peas.Activatable):
    """
    The main plugin class for integrating Telegram with Rhythmbox.
    This class handles the activation, deactivation, and management of Telegram sources within Rhythmbox.
    """

    __gtype_name__ = 'Telegram'
    object = GObject.Property(type=GObject.GObject)

    __gsignals__ = {
        'reload_display_pages': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'update_download_info': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
        'audio_stats_changed': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT, GObject.TYPE_PYOBJECT, GObject.TYPE_PYOBJECT)),
        'entry_added_to_library': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
    }

    def __init__(self):
        """
        Initializes the TelegramPlugin class.
        Sets up the necessary properties, signals, and initializes the account and other components.
        """
        super(TelegramPlugin, self).__init__()
        TelegramApi.application_version = VERSION
        self.account = Account(self)
        self.app = Gio.Application.get_default()
        self.shell = None
        self.db = None
        self.top_picks = None
        self.icon = None
        self.display_icon = None
        self.settings = None
        self.connected = False
        self.is_api_loaded = False
        self.api = None
        self.storage = None
        self.loader = None
        self.downloader = None
        self.group_id = None
        self.require_restart_plugin = False
        self.rhythmdb_settings = None
        self.source = None
        self.toolbar = None
        self.display_pages = {}
        self.search_source = None
        self.sources = {}
        self.signals = {}
        self._created_group = False
        self._context_menu = []

    def _add_plugin_menu_item(self, action, label, add_to_playlist_popup=False):
        """
        Adds a menu item to the plugin's context menu.
        """
        item = Gio.MenuItem()
        item.set_label(label)
        action_name = action.get_name()
        item.set_detailed_action('app.%s' % action_name)
        self._context_menu.append([action_name, item, add_to_playlist_popup])

    def add_plugin_menu(self, playlist_popup=False):
        """
        Adds the plugin's context menu items to the application's menu.
        """
        for item in self._context_menu:
            if not playlist_popup or item[2]:
                if playlist_popup:
                    self.app.add_plugin_menu_item("playlist-popup", item[0], item[1])
                    self.app.add_plugin_menu_item("queue-popup", item[0], item[1])
                else:
                    self.app.add_plugin_menu_item("browser-popup", item[0], item[1])

    def remove_plugin_menu(self, playlist_popup=False):
        """
        Removes the plugin's context menu items from the application's menu.
        """
        for item in self._context_menu:
            if playlist_popup:
                if item[2]:
                    self.app.remove_plugin_menu_item("playlist-popup", item[0])
                    self.app.remove_plugin_menu_item("queue-popup", item[0])
            else:
                self.app.remove_plugin_menu_item("browser-popup", item[0])

    def do_activate(self):
        """
        Activates the plugin. This method is called when the plugin is loaded.
        Initializes the necessary components, connects to the Telegram API, and sets up the UI.
        """
        print('Telegram plugin activating')
        self.require_restart_plugin = False
        self.shell = self.object
        self.db = self.shell.props.db
        self.account.init()
        self.settings = self.account.settings
        self.icon = Gio.FileIcon.new(Gio.File.new_for_path(self.plugin_info.get_data_dir() + '/images/telegram.svg'))
        rb.append_plugin_source_path(self, "icons")
        self.display_icon = Gio.ThemedIcon.new("telegram-symbolic")
        self.rhythmdb_settings = Gio.Settings.new('org.gnome.rhythmbox.rhythmdb')
        self.downloader = AudioDownloader(self)
        self.loader = AudioTempLoader(self)
        self.group_id = None
        self.display_pages = {}
        self.search_source = None
        self.sources = {}
        self.signals = {}
        self._context_menu = []
        self.init_actions()
        self.add_plugin_menu(True)
        self.connect_api()
        self.top_picks = TopPicks(self.shell)
        if self.account.settings[KEY_TOP_PICKS_COLUMN]:
            GLib.timeout_add(4000, self.top_picks.collect)
        if self.account.settings[KEY_IN_LIBRARY_COLUMN]:
            GLib.timeout_add(4000, InLibraryColumn.init_once, self)

    def do_deactivate(self):
        """
        Deactivates the plugin. This method is called when the plugin is unloaded.
        Cleans up resources, disconnects signals, and removes the plugin's UI components.
        """
        print('Telegram plugin deactivating')
        self.delete_display_pages(True)
        self.remove_plugin_menu(True)

        for signal in self.signals.get('db', []):
            self.db.disconnect(signal)

        self.db = None
        self.storage = None
        self.signals = None

    def init_actions(self):
        """
        Initializes the actions and context menu items for the plugin.
        Connects signals for database changes and sets up the toolbar.
        """
        db_signals = list()
        db_signals.append(self.db.connect('entry-deleted', self.on_entry_deleted))
        db_signals.append(self.db.connect('entry-changed', self.on_entry_changed))
        self.signals['db'] = tuple(db_signals)

        app = Gio.Application.get_default()

        action = Gio.SimpleAction(name="tg-hide")
        action.connect("activate", self.hide_action_cb)
        app.add_action(action)
        self._add_plugin_menu_item(action, _("Hide selected"))

        action = Gio.SimpleAction(name="tg-unhide")
        action.connect("activate", self.unhide_action_cb)
        app.add_action(action)
        self._add_plugin_menu_item(action, _("Unhide selected"))

        action = Gio.SimpleAction(name="tg-browse")
        action.connect("activate", self.browse_action_cb)
        app.add_action(action)
        self._add_plugin_menu_item(action, _("View in Telegram"))

        action = Gio.SimpleAction(name="tg-file-manager")
        action.connect("activate", self.file_manager_action_cb)
        app.add_action(action)
        self._add_plugin_menu_item(action, _("View in File Manager"))

        action = Gio.SimpleAction(name="tg-download")
        action.connect("activate", self.download_action_cb)
        app.add_action(action)
        self._add_plugin_menu_item(action, _("Download to Library"))

        action = Gio.SimpleAction(name="tg-search-artist")
        action.connect("activate", self.search_artist_action_cb)
        app.add_action(action)
        self._add_plugin_menu_item(action, _("Search this Artist"), True)

        action = Gio.SimpleAction(name="tg-prefs")
        action.connect("activate", self.show_settings_action_cb)
        app.add_action(action)
        self._add_plugin_menu_item(action, _("Telegram Settings"), True)

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(self, "ui/toolbar.ui"))
        self.toolbar = builder.get_object("telegram-toolbar")
        app.link_shared_menus(self.toolbar)  # noqa

    def connect_api(self):
        """
        Connects to the Telegram API using the credentials stored in the account.
        If successful, it reloads the display pages to show the Telegram sources.
        """
        api_id, api_hash, phone_number, self.connected = self.account.get_secure()
        if self.connected:
            try:
                self.api = TelegramApi.api(api_id, api_hash, phone_number)
                self.api.login()
                self.storage = self.api.storage
                self.do_reload_display_pages()
            except TelegramAuthError as err:
                show_error(err.get_info())
        else:
            self.delete_display_pages()

    def on_entry_changed(self, db, entry, changes):
        """
        Handles changes to song entries in the Rhythmbox database.
        Updates the corresponding entries in the Telegram database if play count or rating changes.
        Together with the TelegramSource:on_entry_changed() method,
        they enable synchronization of ratings and play counts between
        standard song-type entries and Telegram-type entries.
        """
        # watch only for song entry type
        if entry.get_entry_type() != db.entry_type_get_by_name('song') or not self.storage or not self.api:
            return

        audio_changes = {}
        for change in changes:
            if change.prop == RB.RhythmDBPropType.PLAY_COUNT:
                audio_changes['play_count'] = entry.get_ulong(RB.RhythmDBPropType.PLAY_COUNT)
            elif change.prop == RB.RhythmDBPropType.RATING:
                audio_changes['rating'] = int(entry.get_double(RB.RhythmDBPropType.RATING))

        if audio_changes:
            uri = entry.get_string(RB.RhythmDBPropType.LOCATION)
            file_path = GLib.filename_from_uri(uri)[0]
            data = self.storage.select('audio', {'is_moved': 1, 'local_path': file_path}, limit=None) or list()

            for item in data:
                audio = Audio(item)

                if not (('play_count' in audio_changes and audio_changes['play_count'] > audio.play_count) or
                        ('rating' in audio_changes and audio_changes['rating'] != audio.rating)):
                    continue

                # update audio in db
                audio.save(audio_changes)
                self.emit('audio-stats-changed', entry, audio, audio_changes)

                # update tg entry on entry view
                tg_uri = to_location(self.api.hash, audio.chat_id, audio.message_id, audio.id)
                tg_entry = db.entry_lookup_by_location(tg_uri)
                if tg_entry:
                    if 'play_count' in audio_changes:
                        db.entry_set(tg_entry, RB.RhythmDBPropType.PLAY_COUNT, audio_changes['play_count'])
                    if 'rating' in audio_changes:
                        db.entry_set(tg_entry, RB.RhythmDBPropType.RATING, audio_changes['rating'])

    def on_entry_deleted(self, db, entry):
        """
        Handles the deletion of entries from the Rhythmbox database.
        If the deleted entry is a Telegram entry, it marks the corresponding audio as hidden in the Telegram database.
        """
        if str(entry.get_entry_type()).startswith('TelegramEntryType'):
            uri = entry.get_string(RB.RhythmDBPropType.LOCATION)
            chat_id, message_id = get_location_data(uri)
            if chat_id and message_id:
                audio = self.storage.get_audio(chat_id, message_id)
                if audio and audio.is_hidden != 1:
                    audio.save({"is_hidden": 1})

    def get_display_group(self):
        """
        Retrieves or creates the display group for the Telegram sources.
        The display group is used to organize the sources in the Rhythmbox UI.
        """
        if self.group_id:
            return RB.DisplayPageGroup.get_by_id(self.group_id)

        group_id = self.settings[KEY_PAGE_GROUP]

        if group_id == 'telegram' and not self._created_group:
            group = RB.DisplayPageGroup(shell=self.shell, id='telegram', name=_('Telegram'),
                                        category=RB.DisplayPageGroupType.TRANSIENT)
            self.shell.append_display_page(group, None)
            self._created_group = True
        else:
            group = RB.DisplayPageGroup.get_by_id(group_id)

        self.group_id = group_id
        return group

    def delete_display_pages(self, permanent=False):
        """
        Deletes or hides the display pages for the Telegram sources.
        If `permanent` is True, the sources are permanently removed; otherwise, they are just hidden.
        """
        for idx in self.sources:
            if permanent:
                delete_source(self.sources[idx])
            else:
                hide_source(self.sources[idx])
        if permanent:
            self.sources = {}

    def do_reload_display_pages(self):
        """
        Reloads the display pages for the Telegram sources based on the selected channels.
        This method is called when the plugin is activated or when the selected channels change.
        """
        selected = json.loads(self.settings[KEY_CHANNELS]) if self.connected else []

        if self.connected and selected:
            group = self.get_display_group()
            ids = []
            for chat in selected:
                chat_id = chat['id']
                ids.append(chat_id)
                if chat_id in self.sources:
                    show_source(self.sources[chat_id])
                else:
                    self.add_page(chat['id'], chat['title'], group)
            for idx in self.sources:
                if idx not in ids:
                    hide_source(self.sources[idx])
            self.add_search_page(group)
        else:
            for idx in self.sources:
                hide_source(self.sources[idx])

    def add_search_page(self, group):
        entry_type = TelegramSearchEntryType(self)
        source = GObject.new(TelegramSearchSource, shell=self.shell, entry_type=entry_type, icon=self.display_icon,
                             plugin=self, settings=self.settings.get_child("source"), name='Search', toolbar_menu=self.toolbar)
        source.setup(self)
        entry_type.setup(source)
        self.shell.register_entry_type_for_source(source, entry_type)
        self.shell.append_display_page(source, group)
        self.sources['search'] = (source,)
        self.search_source = source

    def add_page(self, chat_id, name, group):
        """
        Adds a new display page for a Telegram chat.
        The page is added to the specified group and is displayed in the Rhythmbox UI.
        """
        av = self.settings[KEY_AUDIO_VISIBILITY]
        sources = []

        if av == VAL_AV_ALL:
            source = self.register_source(chat_id, name, VISIBILITY_ALL)
            self.shell.append_display_page(source, group)
            self.sources[chat_id] = (source,)
            return

        if av in (VAL_AV_VISIBLE, VAL_AV_DUAL):
            source = self.register_source(chat_id, name, VISIBILITY_VISIBLE)
            self.shell.append_display_page(source, group)
            sources.append(source)

        if av in (VAL_AV_HIDDEN, VAL_AV_DUAL):
            hidden_name = "%s [%s]" % (name, _('Hidden'))
            source = self.register_source(chat_id, hidden_name, VISIBILITY_HIDDEN)
            self.shell.append_display_page(source, group)
            sources.append(source)

        self.sources[chat_id] = tuple(sources)

    def register_source(self, chat_id, name, visibility):
        """
        Registers a new source for a Telegram chat.
        The source is used to display the chat's audio entries in the Rhythmbox UI.
        """
        entry_type = TelegramEntryType(self)
        source = GObject.new(TelegramSource, shell=self.shell, entry_type=entry_type, icon=self.display_icon,
            plugin=self, settings=self.settings.get_child("source"), name=name, toolbar_menu=self.toolbar)
        source.setup(self, chat_id, name, visibility)
        entry_type.setup(source)
        self.shell.register_entry_type_for_source(source, entry_type)
        return source

    def playing_entry_changed(self, sp, entry):
        """
        Handles changes to the currently playing entry.
        This method is called when the playing entry changes in Rhythmbox.
        """
        self.source.playing_entry_changed(entry)

    def file_manager_action_cb(self, *_):
        """
        Callback for the "View in File Manager" action.
        Opens the selected entry in the file manager.
        """
        shell = self.object
        shell.props.selected_page.file_manager_action()

    def browse_action_cb(self, *_):
        """
        Callback for the "View in Telegram" action.
        Opens the selected entry in Telegram.
        """
        shell = self.object
        shell.props.selected_page.browse_action()

    def download_action_cb(self, *_):
        """
        Callback for the "Download to Library" action.
        Downloads the selected entry to the local library.
        """
        shell = self.object
        shell.props.selected_page.download_action()

    def hide_action_cb(self, *_):
        """
        Callback for the "Hide selected" action.
        Hides the selected entries from the Telegram source.
        """
        shell = self.object
        shell.props.selected_page.hide_action()

    def unhide_action_cb(self, *_):
        """
        Callback for the "Unhide selected" action.
        Unhides the selected entries in the Telegram source.
        """
        shell = self.object
        shell.props.selected_page.unhide_action()

    def show_settings_action_cb(self, *_):
        """
        Callback for the "Telegram Settings" action.
        Opens the settings dialog for the Telegram plugin.
        """
        dialog = Gtk.Dialog(title="Telegram Settings", parent=self.shell.props.window, flags=0)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        prefs = TelegramPrefs()
        config_widget = prefs.do_create_configure_widget()
        dialog.get_content_area().add(config_widget)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def search_artist_action_cb(self, *_):
        display_page = self.shell.get_property("selected-page")
        entries = display_page.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        artist = entries[0].get_string(RB.RhythmDBPropType.ARTIST)
        self.shell.activate_source(self.search_source, 0)  # RB_SHELL_ACTIVATION_SELECT
        self.search_source.emit('tg_search', artist, 'artist')
        self.search_source.search_bar.set_search_text(artist)
