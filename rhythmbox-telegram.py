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
from gi.overrides import GLib
from gi.repository import RB
from gi.repository import GObject, Gtk, Gio, Peas, PeasGtk
from TelegramSource import TelegramSource
from TelegramApi import TelegramApi
from TelegramConfig import account, TelegramConfig
from TelegramEntry import TelegramEntryType
from common import get_location_data


# from gi.repository.Gdk import Color
# import gettext
# gettext.install('rhythmbox', RB.locale_dir())

# REQUIRED for show config page
# from TelegramConfig import TelegramConfig


class Telegram(GObject.GObject, Peas.Activatable):
    __gtype_name__ = 'Telegram'
    object = GObject.property(type=GObject.GObject)

    __gsignals__ = {
        'reload_sources': (GObject.SIGNAL_RUN_FIRST, None, ())
    }

    def __init__(self):
        super(Telegram, self).__init__()
        self.shell = None
        self.db = None
        self.icon = None
        self.settings = None
        self.account = None
        self.connected = False
        self.is_api_loaded = False
        self.is_downloading = False
        self.api = None
        self.storage = None
        self.page_group = None
        self.sources = []
        self._created_group = False

    def do_activate(self):
        print('Telegram plugin activating')
        self.shell = self.object
        self.db = self.shell.props.db
        self.icon = Gio.FileIcon.new(Gio.File.new_for_path(self.plugin_info.get_data_dir()+'/images/telegram.svg'))
        schema_source = Gio.SettingsSchemaSource.new_from_directory(
            self.plugin_info.get_data_dir(), Gio.SettingsSchemaSource.get_default(), False)
        schema = schema_source.lookup('org.gnome.rhythmbox.plugins.telegram', False)
        self.settings = Gio.Settings.new_full(schema, None, None)
        self.rhythmdb_settings = Gio.Settings.new('org.gnome.rhythmbox.rhythmdb')
        self.account = account(self)
        self.sources = []

        # Connect to the entry-deleted signal of the RhythmDB
        self.db.connect('entry-deleted', self.on_entry_deleted)

        app = Gio.Application.get_default()
        # self.parent = dialog.get_toplevel().get_parent_window()

        action = Gio.SimpleAction(name="tg-browse")
        action.connect("activate", self.browse_action_cb)
        app.add_action(action)

        action = Gio.SimpleAction(name="tg-download")
        action.connect("activate", self.download_action_cb)
        app.add_action(action)

        action = Gio.SimpleAction(name="tg-hide")
        action.connect("activate", self.hide_action_cb)
        app.add_action(action)

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(self, "ui/toolbar.ui"))
        self.toolbar = builder.get_object("telegram-toolbar")
        app.link_shared_menus(self.toolbar)

        rb.append_plugin_source_path(self, "icons")
        api_id, api_hash, phone_number, self.connected = self.account.get_secure()

        if self.connected:
            self.api = TelegramApi.api(api_id, api_hash, phone_number)
            self.api.login()
            self.storage = self.api.storage
            # if self.api.is_ready():

            self.do_reload_sources()

    # def load_api(self):
    #     api_id, api_hash, phone_number, self.connected = self.account.get_secure()
    #     if self.connected:
    #         self.api = TelegramApi.api(api_id, api_hash, phone_number)
    #         self.api.login()
    #         self.storage = self.api.storage
    #         self.is_api_loaded = True

    def on_entry_deleted(self, db, entry):
        loc = entry.get_string(RB.RhythmDBPropType.LOCATION)
        chat_id, message_id = get_location_data(loc)
        audio = self.storage.get_audio(chat_id, message_id)
        audio.save({"is_hidden": True})

    def do_reload_sources(self):
        print('do_reload_sources()')
        for source in self.sources:
            source.delete_thyself()
            self.sources = []

        selected = json.loads(self.settings['channels']) if self.connected else []

        print('== RELOAD.selected %s' % selected)

        if self.connected and selected:
            group_id = self.settings['page-group']
            print('group_id %s' % group_id)
            if group_id == 'telegram':
                if not self._created_group:
                    group = RB.DisplayPageGroup(shell=self.shell, id='telegram', name=_('Telegram'),
                                                category=RB.DisplayPageGroupType.TRANSIENT)
                    self.shell.append_display_page(group, None)
                    self._created_group = True
                else:
                    group = RB.DisplayPageGroup.get_by_id(group_id)
            else:
                group = RB.DisplayPageGroup.get_by_id(group_id)

            # if group is None:
            #   group = RB.DisplayPageGroup(shell=self.shell, id='telegram', name=_('Telegram'), category=RB.DisplayPageGroupType.TRANSIENT)
            #   self.shell.append_display_page(group, None)

            icon = Gio.ThemedIcon.new("telegram-symbolic")

            for chat in selected:
                entry_type = TelegramEntryType(self)
                source = GObject.new(TelegramSource, shell=self.shell, entry_type=entry_type, icon=icon,
                    plugin=self, settings=self.settings.get_child("source"), name=chat['title'], toolbar_menu=self.toolbar)
                source.setup(self, chat['id'])
                entry_type.setup(source)
                self.sources.append(source)
                self.shell.register_entry_type_for_source(source, entry_type)
                self.shell.append_display_page(source, group)

    def do_deactivate(self):
        print('Telegram plugin deactivating')
        shell = self.object
        # shell.props.shell_player.disconnect(self.pec_id)
        # self.db.entry_delete_by_type(self.entry_type)
        # self.db.commit()
        self.db = None
        self.entry_type = None
        for source in self.sources:
            source.delete_thyself()
        self.sources = []

    def playing_entry_changed(self, sp, entry):
        print(entry)
        self.source.playing_entry_changed(entry)

    def browse_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.browse_action()

    def download_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.download_action()

    def hide_action_cb(self, action, hide_action):
        shell = self.object
        shell.props.selected_page.display_artist_info()

