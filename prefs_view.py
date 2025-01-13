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
from gi.repository import RB
from gi.repository import Gtk, GLib
from prefs_base import PrefsPageBase, set_combo_text_column
from account import KEY_RATING_COLUMN, KEY_DATE_ADDED_COLUMN, KEY_FILE_SIZE_COLUMN, KEY_AUDIO_FORMAT_COLUMN
from account import KEY_PAGE_GROUP, KEY_AUDIO_VISIBILITY
from account import VAL_AV_VISIBLE, VAL_AV_HIDDEN, VAL_AV_ALL, VAL_AV_DUAL

import gettext
gettext.install('rhythmbox', RB.locale_dir())

page_groups = [
    [_('Telegram'), 'telegram'],
    [_('Library'), 'library'],
    [_('Shared'), 'shared'],
    [_('Stores'), 'stores'],
    [_('Devices'), 'devices'],
    [_('Playlists'), 'playlists'],
]

audio_visibility_variants = [
    [_('Show Visible Only'), VAL_AV_VISIBLE],
    [_('Show Hidden Only'), VAL_AV_HIDDEN],
    [_('Show All Tracks'), VAL_AV_ALL],
    [_('Split Playlists by Visibility'), VAL_AV_DUAL],
]

class PrefsViewPage(PrefsPageBase):
    name = _('View')
    main_box = 'view_vbox'
    ui_file = 'ui/prefs/view.ui'

    def _create_widget(self):
        self._combos_require_restart = [KEY_PAGE_GROUP, KEY_AUDIO_VISIBILITY]

        self.page_group_combo = self.ui.get_object('page_group_combo')
        self.audio_visibility_combo = self.ui.get_object('audio_visibility_combo')

        self.restart_warning_box = self.ui.get_object('restart_warning_box')

        self.rating_check = self.ui.get_object('rating_check')
        self.date_added_check = self.ui.get_object('date_added_check')
        self.size_check = self.ui.get_object('size_check')
        self.format_check = self.ui.get_object('format_check')

        self._init_check(self.rating_check, KEY_RATING_COLUMN)
        self._init_check(self.date_added_check, KEY_DATE_ADDED_COLUMN)
        self._init_check(self.size_check, KEY_FILE_SIZE_COLUMN)
        self._init_check(self.format_check, KEY_AUDIO_FORMAT_COLUMN)

        self._init_combo(self.page_group_combo, page_groups, KEY_PAGE_GROUP)
        self._init_combo(self.audio_visibility_combo, audio_visibility_variants, KEY_AUDIO_VISIBILITY)

        GLib.timeout_add(600, self._update_box)

    def _update_box(self):
        self.restart_warning_box.set_visible(self.plugin.require_restart_plugin)

    def _init_check(self, checkbox, name):
        value = self.settings[name]
        checkbox.set_active(bool(value))
        checkbox.connect('toggled', self._on_check_toggled, name)

    def _on_check_toggled(self, checkbox, name):
        is_checked = checkbox.get_active()
        self.settings.set_boolean(name, is_checked)
        self.plugin.require_restart_plugin = True
        self.restart_warning_box.set_visible(True)

    def _init_combo(self, combo, variants, name):
        idx = 0
        value = self.settings[name]
        store = Gtk.ListStore(str, str) # noqa
        for i, o in enumerate(variants):
            if value == o[1]:
                idx = i
            store.append([o[1], o[0]])
        combo.set_model(store)
        combo.set_active(idx)
        set_combo_text_column(combo, 1)
        combo.connect('changed', self._on_combo_changed, name)

    def _on_combo_changed(self, combo, name):
        tree_iter = combo.get_active_iter()
        if tree_iter is not None:
            model = combo.get_model()
            value = model[tree_iter][0]
            if name in self._combos_require_restart:
                self.plugin.require_restart_plugin = True
                self.restart_warning_box.set_visible(True)
            self.settings.set_string(name, value)
            self.on_change(name, value)
