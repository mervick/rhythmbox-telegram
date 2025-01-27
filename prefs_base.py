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
import json
from gi.repository import GObject, Gtk, GLib
from account import KEY_CONNECTED, KEY_CHANNELS, KEY_PAGE_GROUP


def set_combo_text_column(combo, col):
    if combo.get_has_entry():
        combo.set_entry_text_column(col)
    else:
        text = Gtk.CellRendererText()
        combo.pack_start(text, True)
        combo.add_attribute(text, 'text', col)


class PrefsPageBase(GObject.GObject):
    def __init__(self, prefs, name=None, ui_file=None, main_box=None):
        self.box = Gtk.Box(hexpand=True)
        # init changes with current data
        self._changes = {KEY_CONNECTED: json.dumps(prefs.plugin.connected)}
        self.has_errors = []
        # set custom values
        self.prefs = prefs
        self.plugin = prefs.plugin
        self.account = prefs.account
        self.settings = prefs.account.settings
        if name is not None:
            self.name = name
        if ui_file is not None:
            self.ui_file = ui_file
        if main_box is not None:
            self.main_box = main_box
        # init UI
        self.box.set_border_width(5) # noqa
        self.ui = Gtk.Builder()
        self.ui.add_from_file(prefs.find_plugin_file(self.ui_file))
        self._init_widget()
        self.register_signals()

    def set_sensitive(self, sensitive):
        self.box.set_sensitive(sensitive)

    def register_signals(self):
        pass

    def create_widget(self):
        self._create_widget()
        self.box.add(self.get_main_object()) # noqa
        return self

    def set_error(self, widget, is_error=True):
        if is_error:
            self.has_errors.append(widget)
            widget.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, 'error')
        else:
            widget.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

    def clear_errors(self):
        if self.has_errors:
            for widget in self.has_errors:
                self.set_error(widget, False)
            self.has_errors.clear()

    def on_change(self, name, value):
        if name in [KEY_CONNECTED, KEY_CHANNELS, KEY_PAGE_GROUP]:
            dump = json.dumps(value)
            reload = False
            if name not in self._changes or self._changes[name] != dump:
                self._changes[name] = dump
                reload = True
            if reload:
                GLib.idle_add(self.prefs.plugin.emit, 'reload_display_pages')

    def get_window(self):
        return self.ui.get_object('window')

    def get_main_object(self):
        return self.ui.get_object(self.main_box)

    def _init_widget(self):
        pass

    def _create_widget(self):
        pass

    def append_to(self, notebook):
        notebook.append_page(self.box, Gtk.Label(self.name))
