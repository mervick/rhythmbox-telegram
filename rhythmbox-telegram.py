# rhythmbox-telegram
# Copyright (C) 2023-2024 Andrey Izman <izmanw@gmail.com>
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
from gi.overrides import GLib # noqa
from gi.repository import RB
from gi.repository import GObject, Gtk, Gio
from gi.repository import Peas, PeasGtk # noqa
from TelegramLoader import AudioDownloader, AudioLoader
from TelegramSource import TelegramSource
from TelegramApi import TelegramApi, TelegramAuthError
from TelegramConfig import TelegramConfig  # TelegramConfig is REQUIRED for showing config page
from TelegramAccount import TelegramAccount
from TelegramEntry import TelegramEntryType
from common import get_location_data, show_error


class Telegram(GObject.GObject, Peas.Activatable):
    __gtype_name__ = 'Telegram'
    object = GObject.property(type=GObject.GObject)

    __gsignals__ = {
        'reload_sources': (GObject.SIGNAL_RUN_FIRST, None, ()),
        'update_download_info': (GObject.SIGNAL_RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
    }

    def __init__(self):
        super(Telegram, self).__init__()
        self.account = TelegramAccount(self)
        self.shell = None
        self.db = None
        self.icon = None
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
        self.sources = {}
        self.deleted_sources = {}
        self._created_group = False

    def do_activate(self):
        print('Telegram plugin activating')
        self.require_restart_plugin = False
        self.shell = self.object
        self.db = self.shell.props.db
        self.account.init()
        self.settings = self.account.settings
        self.icon = Gio.FileIcon.new(Gio.File.new_for_path(self.plugin_info.get_data_dir() + '/images/telegram.svg'))
        self.rhythmdb_settings = Gio.Settings.new('org.gnome.rhythmbox.rhythmdb')
        self.downloader = AudioDownloader(self)
        self.loader = AudioLoader(self)
        self.group_id = None
        self.sources = {}
        self.deleted_sources = {}

        app = Gio.Application.get_default()
        self.db.connect('entry-deleted', self.on_entry_deleted)

        action = Gio.SimpleAction(name="tg-browse")
        action.connect("activate", self.browse_action_cb)
        app.add_action(action)

        action = Gio.SimpleAction(name="tg-file-manager")
        action.connect("activate", self.file_manager_action_cb)
        app.add_action(action)

        action = Gio.SimpleAction(name="tg-download")
        action.connect("activate", self.download_action_cb)
        app.add_action(action)

        action = Gio.SimpleAction(name="tg-hide")
        action.connect("activate", self.hide_action_cb)
        app.add_action(action)

        action = Gio.SimpleAction(name="tg-unhide")
        action.connect("activate", self.unhide_action_cb)
        app.add_action(action)

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(self, "ui/toolbar.ui"))
        self.toolbar = builder.get_object("telegram-toolbar")
        app.link_shared_menus(self.toolbar)

        rb.append_plugin_source_path(self, "icons")
        api_id, api_hash, phone_number, self.connected = self.account.get_secure()

        if self.connected:
            try:
                self.api = TelegramApi.api(api_id, api_hash, phone_number)
                self.api.login()
                self.storage = self.api.storage
                self.do_reload_sources()
            except TelegramAuthError as err:
                show_error(err.get_info())

    # def load_api(self):
    #     api_id, api_hash, phone_number, self.connected = self.account.get_secure()
    #     if self.connected:
    #         self.api = TelegramApi.api(api_id, api_hash, phone_number)
    #         self.api.login()
    #         self.storage = self.api.storage
    #         self.is_api_loaded = True

    def on_entry_deleted(self, db, entry):
        loc = entry.get_string(RB.RhythmDBPropType.LOCATION)
        print(f'on_entry_deleted({loc})')
        chat_id, message_id = get_location_data(loc)
        audio = self.storage.get_audio(chat_id, message_id)
        audio.save({"is_hidden": True})

    def do_reload_sources(self):
        print('do_reload_sources()')
        selected = json.loads(self.settings['channels']) if self.connected else []

        if self.connected and selected:
            group_id = self.settings['page-group']

            if group_id != self.group_id:
                for idx in self.sources:
                    self.deleted_sources[idx] = self.sources[idx]
                    self.sources[idx].delete_thyself()
                self.sources = {}

            for idx in list(self.sources.keys()):
                id_list = [chat['id'] for chat in selected]
                if idx not in id_list:
                    self.deleted_sources[idx] = self.sources[idx]
                    self.sources[idx].hide_thyself()
                    del self.sources[idx]

            if group_id == 'telegram' and not self._created_group:
                group = RB.DisplayPageGroup(shell=self.shell, id='telegram', name=_('Telegram'),
                                            category=RB.DisplayPageGroupType.TRANSIENT)
                self.shell.append_display_page(group, None)
                self._created_group = True
            else:
                group = RB.DisplayPageGroup.get_by_id(group_id)

            self.group_id = group_id
            icon = Gio.ThemedIcon.new("telegram-symbolic")

            for chat in selected:
                chat_id = chat['id']
                if chat_id not in self.sources:
                    if chat_id in self.deleted_sources:
                        source = self.deleted_sources[chat_id]
                        self.sources[chat_id] = source
                        del self.deleted_sources[chat_id]
                        source.show_thyself()
                        # self.shell.append_display_page(source, group)
                    else:
                        entry_type = TelegramEntryType(self)
                        source = GObject.new(TelegramSource, shell=self.shell, entry_type=entry_type, icon=icon,
                            plugin=self, settings=self.settings.get_child("source"), name=chat['title'], toolbar_menu=self.toolbar)
                        source.setup(self, chat_id, chat['title'])
                        entry_type.setup(source)
                        self.sources[chat_id] = source
                        self.shell.register_entry_type_for_source(source, entry_type)
                        self.shell.append_display_page(source, group)
        else:
            for idx in self.sources:
                self.sources[idx].delete_thyself()
            self.deleted_sources = {}
            self.sources = {}

    def do_deactivate(self):
        print('Telegram plugin deactivating')
        shell = self.object
        # shell.props.shell_player.disconnect(self.pec_id)
        # self.db.entry_delete_by_type(self.entry_type)
        # self.db.commit()
        self.db = None
        self.entry_type = None
        for idx in self.sources:
            self.sources[idx].delete_thyself()
        self.sources = {}

    def playing_entry_changed(self, sp, entry):
        print(entry)
        self.source.playing_entry_changed(entry)

    def file_manager_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.file_manager_action()

    def browse_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.browse_action()

    def download_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.download_action()

    def hide_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.hide_action()

    def unhide_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.unhide_action()

