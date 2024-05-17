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
from gi.repository import GObject, Gtk, Gio


def set_combo_text_column(combo, col):
    if combo.get_has_entry():
        combo.set_entry_text_column(col)
    else:
        text = Gtk.CellRendererText()
        combo.pack_start(text, True)
        combo.add_attribute(text, 'text', col)


class PrefsPage(GObject.GObject):
    def __init__(self, prefs, name=None, ui_file=None, main_box=None):
        self.box = Gtk.Box(hexpand=True)
        # init vars
        self._changes = {}
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
        self.box.set_border_width(5)
        self.ui = Gtk.Builder()
        self.ui.add_from_file(prefs.find_plugin_file(self.ui_file))
        self._init_widget()
        self.register_signals()

    def register_signals(self):
        pass

    def create_widget(self):
        self._create_widget()
        self.box.add(self.get_main_object())
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

    def show_error(self, title, description=None):
        err_dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, title)
        if description is not None:
            err_dialog.format_secondary_text(str(description))
        err_dialog.set_application(Gio.Application.get_default())
        err_dialog.run()
        err_dialog.destroy()

    def on_change(self, name, value):
        print('==ON_CHANGE %s %s' % (name, value))
        txt = json.dumps(value)
        reload = False
        if name not in self._changes or self._changes[name] != txt:
            self._changes[name] = txt
            if name in ['connected', 'channels', 'page-group']:
                reload = True
        if reload:
            print('===EMIT1.reload_sources')
            self.prefs.plugin.emit('reload_sources')

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
