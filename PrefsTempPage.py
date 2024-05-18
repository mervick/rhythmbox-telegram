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
from gi.repository import Gtk, Gio
from PrefsPage import PrefsPage


class PrefsTempPage(PrefsPage):
    name = _('Temporary Files')
    main_box = 'temp_vbox'
    ui_file = 'ui/prefs/temp.ui'

    def _create_widget(self):
        self.temp_usage_label = self.ui.get_object('temp_usage_label')
        self.temp_path_entry = self.ui.get_object('temp_path_entry')
        self.usage_refresh_btn = self.ui.get_object('usage_refresh_btn')
        self.clear_tmp_btn = self.ui.get_object('clear_tmp_btn')
        self.view_dir_btn = self.ui.get_object('view_dir_btn')

        self.usage_refresh_btn.connect('clicked', self._refresh_btn_clicked)
        self.clear_tmp_btn.connect('clicked', self._clear_tmp_btn_clicked)
        self.view_dir_btn.connect('clicked', self._view_dir_btn_clicked)

    def _refresh_btn_clicked(self, widget, data):
        pass

    def _clear_tmp_btn_clicked(self, widget, data):
        pass

    def _view_dir_btn_clicked(self, widget, data):
        pass
