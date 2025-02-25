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

import gi
gi.require_version('Gtk', '3.0')
import rb
from gi.repository import GObject, Gtk, Gdk, GLib
from gi.repository import Peas, PeasGtk # noqa
from account import Account
from prefs_connect import PrefsConnectPage
from prefs_channels import PrefsChannelsPage
from prefs_settings import PrefsSettingsPage
from prefs_view import PrefsViewPage
from prefs_temp import PrefsTempPage


class TelegramPrefs(GObject.GObject, PeasGtk.Configurable):
    __gtype_name__ = 'TelegramPrefs'
    object = GObject.Property(type=GObject.GObject)
    loading = None
    spinner = None
    parent = None
    api = None
    removed_help = False

    main_box: Gtk.Box
    page1: PrefsConnectPage
    page2: PrefsChannelsPage
    page3: PrefsSettingsPage
    page4: PrefsViewPage
    page5: PrefsTempPage

    __gsignals__ = {
        'api-connect' : (GObject.SignalFlags.RUN_FIRST, None, ()),
        'api-disconnect' : (GObject.SignalFlags.RUN_FIRST, None, ()),
        'channels-clear' : (GObject.SignalFlags.RUN_FIRST, None, ()),
        'channels-reload' : (GObject.SignalFlags.RUN_FIRST, None, ()),
        'channels-fetch' : (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.shell = self.object
        self.account = None
        self.plugin = None
        self.plugin_info = None
        self.settings = None

    def find_plugin_file(self, file):
        return rb.find_plugin_file(self, file)

    def do_create_configure_widget(self):
        self.account = Account()
        self.account.init()
        self.plugin = self.account.plugin
        self.settings = self.account.settings
        self.plugin_info = self.plugin.plugin_info

        main_box = Gtk.Box()
        self.main_box = main_box
        main_box.set_border_width(5)
        notebook = Gtk.Notebook(vexpand=True, hexpand=True)
        main_box.add(notebook)

        self.page1 = PrefsConnectPage(self)
        self.page2 = PrefsChannelsPage(self)
        self.page3 = PrefsSettingsPage(self)
        self.page4 = PrefsViewPage(self)
        self.page5 = PrefsTempPage(self)

        self.page1.create_widget().append_to(notebook)
        self.page2.create_widget().append_to(notebook)
        self.page3.create_widget().append_to(notebook)
        self.page4.create_widget().append_to(notebook)
        self.page5.create_widget().append_to(notebook)

        GLib.timeout_add(600, self.update_window)
        return main_box

    def get_center(self):
        self.parent = self.main_box.get_toplevel().get_property('window')
        position = self.parent.get_position()
        geometry = self.parent.get_geometry()
        left_center = round(position.x + (geometry.width - geometry.x) / 2)
        top_center = round(position.y + (geometry.height - geometry.y) / 2)
        return {"x": left_center, "y": top_center}

    def update_window(self):
        gtk_win = self.main_box.get_toplevel()
        gtk_win.set_default_size(500, 600)
        gtk_win.set_resizable(False)
        donate_btn = gtk_win.add_button("About", Gtk.ResponseType.HELP)
        donate_btn.connect("pressed", self.on_donate_clicked)
        style_context = donate_btn.get_style_context()
        style_context.add_class('suggested-action')
        gtk_win.set_border_width(5)
        box = gtk_win.get_content_area()
        box.set_spacing(2)

    def on_donate_clicked(self, button):
        screen = self.plugin.shell.props.window.get_screen()
        Gtk.show_uri(screen, 'https://github.com/mervick/rhythmbox-telegram', Gdk.CURRENT_TIME)
