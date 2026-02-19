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
from gi.repository import Gtk, GLib


class AuthDialog:
    code: str

    def __init__(self, config, on_ok, on_cancel):
        self._is_closed = False
        self._on_ok_cb = on_ok
        self._on_cancel_cb = on_cancel

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(config.plugin, "ui/auth-dialog.ui"))

        self.window = builder.get_object('window')
        self.code_entry = builder.get_object('code_entry')
        self.code_entry.connect("focus-out-event", self._entry_changed_cb)

        signals = {
            "ok_btn_clicked_cb" : self._ok_clicked_cb,
            "cancel_btn_clicked_cb" : self._cancel_clicked_cb,
            "on_window_destroy": self._cancel_clicked_cb,
            "destroy": self._cancel_clicked_cb,
            "delete-event": self._cancel_clicked_cb
        }
        builder.connect_signals(signals)
        self.window.set_title(_('Telegram Authorization'))
        self.window.show_all()
        center = config.get_center()
        self.window.move(center["x"] - 180, center["y"] - 130)
        self.window.present()

    def _entry_changed_cb(self, *arg):
        self.code = self.code_entry.get_text().strip()

    def _complete_ok(self):
        # print(self.code)
        self._on_ok_cb(self.code)

    def close(self):
        if not self._is_closed:
            self._is_closed = True
            self.window.close()
            return True
        return False

    def _ok_clicked_cb(self, *arg):
        self.close()
        GLib.timeout_add(100, self._complete_ok)

    def _cancel_clicked_cb(self, *arg):
        if self.close():
            GLib.timeout_add(100, self._on_cancel_cb)
