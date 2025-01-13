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
from gi.repository import Gtk, GLib


class AuthDialog:
    def __init__(self, config, on_ok, on_cancel):
        self.ok_received = False
        self.code = None
        self.is_done = False
        self._on_ok = on_ok
        self._on_cancel = on_cancel

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(config.plugin, "ui/dialog-code.ui"))

        self.window = builder.get_object('window')
        self.code_entry = builder.get_object('code_entry')
        self.code_entry.connect("focus-out-event", self._entry_changed)

        cb = {
            "ok_btn_clicked_cb" : self._ok_clicked,
            "cancel_btn_clicked_cb" : self._cancel_clicked,
            "on_window_destroy": self._cancel_clicked,
            "destroy": self._cancel_clicked,
            "delete-event": self._cancel_clicked
        }
        builder.connect_signals(cb)
        self.window.set_title(_('Telegram Authorization'))
        self.window.show_all()
        center = config.get_center()
        self.window.move(center["x"] - 180, center["y"] - 130)
        self.window.present()

    def _entry_changed(self, entry, event):
        self.code = self.code_entry.get_text().strip()
        print(self.code)

    def _done(self):
        print(self.code)
        self._on_ok(self.code)

    def _ok_clicked(self, event):
        self.ok_received = True
        self.window.close()
        GLib.timeout_add(100, self._done)

    def _cancel_clicked(self, event):
        self.window.close()
        if not self.ok_received and not self.is_done:
            self.code = None
            self.is_done = True
            GLib.timeout_add(100, self._on_cancel)
