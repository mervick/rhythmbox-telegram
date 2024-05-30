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

import gi
gi.require_version('Gtk', '3.0')
import json
from gi.repository import GObject, Gtk
from SearchList import SearchListBox
from PrefsPage import PrefsPage


class PrefsChannelsPage(PrefsPage):
    name = _('Music Channels')
    main_box = 'channels_vbox'
    ui_file = 'ui/prefs/channels.ui'

    def on_list_box_change(self, v):
        self.prefs.settings.set_string('channels', json.dumps(v))
        self.on_change("channels", [channel["id"] for channel in v])

    def on_channels_clear(self, obj=None):
        self.search_list_box.reset()
        self.prefs.account.settings.set_string('channels', '[]')

    def on_channels_reload(self, obj=None):
        selected = json.loads(self.prefs.account.settings['channels'])
        self.search_list_box.set_selected(selected)

    def on_channels_fetch(self, obj=None):
        def _set_chats(chats):
            self.search_list_box.clear_list()
            self.search_list_box.set_items(list(chats.values()))
            # @TODO add spinner?
#             self.loading = False
#             upd_spinner()
        self.prefs.api.get_chats_idle(_set_chats)

    def register_signals(self):
        self.prefs.connect('channels-clear', self.on_channels_clear)
        self.prefs.connect('channels-reload', self.on_channels_reload)
        self.prefs.connect('channels-fetch', self.on_channels_fetch)

    def _init_widget(self):
        popover = self.ui.get_object("channels_popover")
        placeholder = self.ui.get_object("list_box_placeholder")
        search_entry = self.ui.get_object("search_entry")

        list_frame = self.ui.get_object("list_frame")
        empty_label = self.ui.get_object("empty_label")
        channels_list_box = self.ui.get_object("channels_list_box")
        channels_flow_box = self.ui.get_object("channels_flow_box")

#         channel_box = self.ui.get_object("channel_box")
#         channel_wrap = self.ui.get_object('channel_wrap_box')

        search_list_box = SearchListBox(search_entry, placeholder, channels_flow_box, channels_list_box, list_frame, empty_label)
        search_list_box.connect_on_change(self.on_list_box_change)
        self.search_list_box = search_list_box

        add_chat_btn = self.ui.get_object("add_chat_btn")
        add_chat_btn.set_popover(popover)
