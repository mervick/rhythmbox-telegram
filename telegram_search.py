# rhythmbox-telegram
# Copyright (C) 2023-2026 Andrey Izman <izmanw@gmail.com>
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
from gi.repository import RB
import base64, time
from gi.repository import GObject, Gtk, Gio
from common import to_location, pretty_file_size, idle_add_once
from storage import Audio, VISIBILITY_HIDDEN
from telegram_entry import TelegramEntryType
from telegram_source import TelegramSource

import gettext
gettext.install('rhythmbox', RB.locale_dir())


class TelegramSearchEntryType(TelegramEntryType):
    """ Custom entry type for Telegram search results in Rhythmbox. """

    def __str__(self) -> str:
        """ Return string representation of the entry type. """
        return 'TelegramSearchEntryType'

    def __init__(self, plugin):
        """ Initialize the Telegram search entry type. """
        RB.RhythmDBEntryType.__init__(self, name='TelegramSearchEntryType', save_to_disk=False)
        self.source = None
        self.plugin = plugin
        self.shell = plugin.shell
        self.db = plugin.db
        self.shell_player = self.shell.props.shell_player
        self._pending_playback = None
        self._entry_error_id = None
        self._entry_downloaded_id = None

GObject.type_register(TelegramSearchEntryType)


class SearchBar(GObject.GObject):
    """ Search bar widget for Telegram search functionality. """

    __gsignals__ = {
        'set_search_text': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_STRING,)),
    }

    def __init__(self, shell, plugin, source):
        """ Initialize the search bar. """
        self.shell = shell
        self.plugin = plugin
        self.source = source
        self.active = False
        self.ui = None
        self.action = None
        self.alt_search_btn = None
        self.search_box = None
        self.search_bar = None
        self.search_entry = None
        self.search_button = None
        self.prev_action = None

    def on_set_search_text_cb(self, widget, text):
        """ Callback for setting search text. """
        self.search_entry.set_text(text)

    def set_search_text(self, text):
        """ Set the search text in the entry field. """
        self.search_entry.set_text(text)

    def deactivate(self):
        """ Deactivate the search bar by disabling its action. """
        self.disable_action()
        self.active = False

    def activate(self):
        """ Activate the search bar and initialize UI if needed. """
        if not self.active:
            if not self.search_bar:
                self.init_ui()
            self.apply_action()
            idle_add_once(self.activate_search)
        self.active = True

    def disable_action(self):
        """ Disable the search action and restore previous action. """
        app = Gio.Application.get_default()
        app.remove_action("TelegramSearch")
        if self.prev_action:
            self.prev_action.set_enabled(True)

    def apply_action(self):
        """ Apply the search action by replacing the default Ctrl-F behavior. """
        # Disable alt-toolbar search action (Ctrl-F)
        self.prev_action = self.shell.props.application.lookup_action("Search")
        if self.prev_action:
            self.prev_action.set_enabled(False)

        # set Ctrl-F action for search
        accel = "<Ctrl>f"
        action_name = 'TelegramSearch'
        self.action = Gio.SimpleAction.new(action_name, None)
        app = Gio.Application.get_default()
        app.add_action(self.action)
        app.set_accels_for_action("app." + action_name, [accel])
        self.action.connect("activate", self.activate_search, [])

    @staticmethod
    def find_search_icon(widget):
        """ Find search icon in widget hierarchy. """
        for child in widget.get_children():
            if isinstance(child, Gtk.Image):
                icon_name = child.get_icon_name()
                icon_str = str(icon_name)
                if "preferences-system-search-symbolic" in icon_str:
                    return True
            elif isinstance(child, Gtk.Container):
                if SearchBar.find_search_icon(child):
                    return True
        return False

    @staticmethod
    def find_alt_search_button(widget):
        """ Find alternative search button in widget hierarchy. """
        if isinstance(widget, Gtk.Box):
            for child in widget.get_children():
                if isinstance(child, Gtk.Box):
                    res = SearchBar.find_alt_search_button(child)
                    if res:
                        return res
                if isinstance(child, Gtk.ToggleButton):
                    if SearchBar.find_search_icon(child):
                        return child
        return None

    def find_alt_header_search_btn(self):
        """ Find alternative search button in header bar. """
        header_bar = self.source.plugin.shell.props.window.get_titlebar()
        if isinstance(header_bar, Gtk.HeaderBar):
            for box in header_bar.get_children():
                self.alt_search_btn = self.find_alt_search_button(box)
        return None

    def disable_alt_search(self):
        """ Disable alternative search button if found. """
        self.find_alt_header_search_btn()
        if self.alt_search_btn:
            self.alt_search_btn.set_sensitive(False)
        return False

    def activate_search(self, *args):
        """ Activate search mode and focus the search entry. """
        self.search_bar.set_search_mode(True)

        def idle_focus_entry():
            self.search_entry.grab_focus()

        idle_add_once(idle_focus_entry)
        idle_add_once(self.disable_alt_search)

    def init_ui(self):
        """ Initialize the search bar UI components. """
        entry_view = self.source.get_entry_view()
        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(self.plugin, "ui/search.ui"))

        self.search_box = builder.get_object("search_box")
        self.search_bar = builder.get_object("search_bar")
        self.search_entry = builder.get_object("search_entry")
        self.search_button = builder.get_object("search_button")

        entry_view.pack_start(self.search_bar, False, False, 0)
        entry_view.reorder_child(self.search_bar, 0)
        self.search_bar.show_all()

        self.search_button.connect('clicked', self._find_clicked_cb)
        self.search_entry.connect("activate", self._find_clicked_cb)

    def _find_clicked_cb(self, *_):
        """ Callback for search button click or entry activation. """
        search_query = self.search_entry.get_text()
        self.source.emit("tg_search", search_query, 'any')

GObject.type_register(SearchBar)


class TelegramSearchSource(TelegramSource):
    """
    TelegramSearchSource class represents a source for Telegram Search in Rhythmbox
    """
    __gsignals__ = {
        'tg_search': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_STRING, GObject.TYPE_STRING,)),
        'tg_clear': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __str__(self) -> str:
        """ Return string representation of the source. """
        return f'TelegramSearchSource'

    def __init__(self):
        """ Initialize the Telegram search source. """
        TelegramSource.__init__(self)
        self.refresh_btn = None
        self.alt_refresh_btn = None
        self.search_bar = None
        self.hash_append = None
        self.search_query = ''

    def setup(self, plugin, chat_id=None, chat_title=None, visibility=None):
        """ Set up the TelegramSource with the given parameters """
        TelegramSource.setup(self, plugin, 0, None, VISIBILITY_HIDDEN)

        self.search_bar = SearchBar(self.shell, plugin, self)
        self.connect("tg_search", self.search_cb)
        self.plugin.connect('audio-stats-changed', self.on_audio_stats_changed)

    def do_selected(self):
        """
        Handles actions when the source is selected, such as activating the download bar,
        search bar, and adding entries.
        """
        self.initialised = True
        TelegramSource.do_selected(self)
        self.search_bar.activate()

    def do_deselected(self):
        """
        Handles actions when the source is deselected, such as deactivating the download bar
        and stopping the loader.
        """
        self.search_bar.deactivate()
        self.bar.deactivate()
        self.state_column.deactivate()
        self.plugin.remove_plugin_menu()

    def clear_entries(self):
        """ Clear all search result entries from the database. """
        playing_entry = self.shell.props.shell_player.get_playing_entry()
        if playing_entry:
            if str(playing_entry.get_entry_type()).startswith('TelegramSearchEntryType'):
                idle_add_once(self.shell.props.shell_player.stop)

        def idle_clear_entries():
            self.custom_model = {}

            entries = []
            def each_entry(item):
                entries.append(item)

            self.db.entry_foreach_by_type(self.props.entry_type, each_entry)
            for entry in entries:
                if str(entry.get_entry_type()).startswith('TelegramSearchEntryType'):
                    self.db.entry_delete(entry)
            self.db.commit()

        idle_add_once(idle_clear_entries)

    def add_entries(self, search_column='any'):
        """ Loads and adds entries from the plugin's storage to the source """
        ms = int(time.time() * 1000)
        b = ms.to_bytes((ms.bit_length() + 7) // 8, byteorder='big')
        self.hash_append = base64.b64encode(b).decode('ascii')

        if self.plugin.storage and len(self.search_query) >= 3:
            cursor = self.plugin.storage.db.cursor()
            if search_column == 'artist':
                sql = 'SELECT * FROM `audio` WHERE artist LIKE ?'
                cursor.execute(sql, (f'%{self.search_query}%',))
            elif search_column == 'title':
                sql = 'SELECT * FROM `audio` WHERE title LIKE ?'
                cursor.execute(sql, (f'%{self.search_query}%',))
            else:
                sql = 'SELECT * FROM `audio` WHERE artist LIKE ? or title LIKE ?'
                cursor.execute(sql, (f'%{self.search_query}%',f'%{self.search_query}%',))

            for row in cursor:
                self.add_entry(Audio(row))
            cursor.close()

    def add_entry(self, audio: Audio):
        """ Adds a single audio entry to the source """
        if audio.id:
            location = to_location("%s.%s" % (self.plugin.api.hash, self.hash_append), audio.chat_id, audio.message_id, audio.id)
            self.custom_model["%s" % audio.id] = [pretty_file_size(audio.size, 1), audio.get_file_ext(), audio.date]
            entry = self.db.entry_lookup_by_location(location)
            if not entry:
                entry = RB.RhythmDBEntry.new(self.db, self.entry_type, location)
                audio.update_entry(entry, self.db)

    def on_audio_stats_changed(self, plugin, entry, audio, audio_changes):
        """ Sync changes in entry state (rating, play count) and updates corresponding entries. """
        if str(entry.get_entry_type()) == 'TelegramSearchEntryType':
            uri = to_location(self.plugin.api.hash, audio.chat_id, audio.message_id, audio.id)
        else:
            uri = to_location("%s.%s" % (self.plugin.api.hash, self.hash_append), audio.chat_id, audio.message_id, audio.id)
        tg_entry = self.db.entry_lookup_by_location(uri)
        self.set_entry_metadata(tg_entry, audio_changes)

    def search_cb(self, search_bar, search_query, search_column, *_):
        """ Callback for search signal. """
        self.search_query = search_query
        self.clear_entries()
        idle_add_once(self.add_entries, search_column)

    def do_can_delete(self):
        return False

GObject.type_register(TelegramSearchSource)
