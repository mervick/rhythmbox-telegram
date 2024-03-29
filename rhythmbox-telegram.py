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
# from TelegramConfig import TelegramConfig
from TelegramConfig import account
from TelegramEntry import TelegramEntryType

# from gi.repository.Gdk import Color
# import gettext
# gettext.install('rhythmbox', RB.locale_dir())

# REQUIRED for show config page
from TelegramConfig import TelegramConfig


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
        self.is_downloading = False
        self.api = None
        self.storage = None
        self.page_group = None
        self.sources = []

    def do_activate(self):
        print('Telegram plugin activating')
        self.shell = self.object
        self.db = self.shell.props.db
        self.icon = Gio.FileIcon.new(Gio.File.new_for_path(self.plugin_info.get_data_dir()+'/images/telegram.svg'))
        schema_source = Gio.SettingsSchemaSource.new_from_directory(
            self.plugin_info.get_data_dir(), Gio.SettingsSchemaSource.get_default(), False)
        schema = schema_source.lookup('org.gnome.rhythmbox.plugins.telegram', False)
        self.settings = Gio.Settings.new_full(schema, None, None)
        self.account = account(self)
        self.sources = []

        # self.entry_type = TelegramEntryType()
        # self.db.register_entry_type(self.entry_type)

        app = Gio.Application.get_default()
        # self.parent = dialog.get_toplevel().get_parent_window()

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(self, "ui/toolbar.ui"))
        self.toolbar = builder.get_object("telegram-toolbar")
        app.link_shared_menus(self.toolbar)

        rb.append_plugin_source_path(self, "icons")

        api_id, api_hash, phone_number, self.connected = self.account.get_secure()
        print('==========================================================================')
        print(self.connected)
        print('==========================================================================')

        # action = Gio.SimpleAction(name='tg-reload-sources')
        # action.connect('activate', self.load_sources)
        # app.add_action(action)
        # app.connect("tg_reload_sources", self.load_sources)
#         self.page_group = RB.DisplayPageGroup(shell=self.shell, id='telegram', name=_('Telegram'), category=RB.DisplayPageGroupType.TRANSIENT)
#         self.shell.append_display_page(self.page_group, None)

        if self.connected:
            self.api = TelegramApi.api(api_id, api_hash, phone_number)
            self.api.login()
            self.storage = self.api.storage
            # if self.api.is_ready():

            print(self.api.is_ready())

            # # if self.api.is_ready():
            # def mess_ready():
            #     print('==========================================================================')
            #     print(self.api.get_any_audio())
            #     print('==========================================================================')
            #
            # self.api.load_messages_idle(mess_ready)

            self.do_reload_sources()

    def do_reload_sources(self):
        for source in self.sources:
            source.delete_thyself()
            self.sources = []

        selected = json.loads(self.settings['channels']) if self.connected else []

        if self.connected and selected:
            # self.group = group = RB.DisplayPageGroup(shell=self.shell, id='telegram', name=_('Telegram'), category=RB.DisplayPageGroupType.TRANSIENT)
            # self.shell.append_display_page(self.group, None)
            # group = RB.DisplayPageGroup.get_by_id("stores")
            # group = RB.DisplayPageGroup.get_by_id("shared")
            group = RB.DisplayPageGroup.get_by_id("library")
#             group = RB.DisplayPageGroup.get_by_id("telegram")

            if group is None:
              group = RB.DisplayPageGroup(shell=self.shell, id='telegram', name=_('Telegram'), category=RB.DisplayPageGroupType.TRANSIENT)
              self.shell.append_display_page(group, None)

            icon = Gio.ThemedIcon.new("telegram-symbolic")

            for chat in selected:
                entry_type = TelegramEntryType(self)
                source = GObject.new(TelegramSource, shell=self.shell, entry_type=entry_type, icon=icon,
                    plugin=self, settings=self.settings.get_child("source"), name=chat['title'], toolbar_menu=self.toolbar)
                source.setup(self.api, chat['id'])
                entry_type.setup(source)
                self.sources.append(source)
                self.shell.register_entry_type_for_source(source, entry_type)
                self.shell.append_display_page(source, group)

        print('========================================================================== shell')
        print(self.shell)

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

    def download_album_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.download_album()

    def artist_info_action_cb(self, action, parameter):
        shell = self.object
        shell.props.selected_page.display_artist_info()

