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

import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import RB  # type: ignore
from gi.repository import Gtk
from prefs_base import PrefsPageBase, set_combo_text_column
from common import filepath_parse_pattern, show_error
from common import CONFLICT_ACTION_RENAME, CONFLICT_ACTION_REPLACE, CONFLICT_ACTION_SKIP, CONFLICT_ACTION_ASK
from account import KEY_CONFLICT_RESOLVE, KEY_LIBRARY_PATH, KEY_FOLDER_HIERARCHY, KEY_FILENAME_TEMPLATE
from account import KEY_PRELOAD_MAX_FILE_SIZE, KEY_PRELOAD_FILE_FORMATS, AUDIO_FORMAT_ALL
from account import KEY_PRELOAD_NEXT_TRACK, KEY_PRELOAD_PREV_TRACK, KEY_PRELOAD_HIDDEN_TRACK
from account import KEY_DETECT_DIRS_IGNORE_CASE, KEY_DETECT_FILES_IGNORE_CASE
from typing import cast, List


import gettext
gettext.install('rhythmbox', RB.locale_dir())
_ = gettext.gettext


library_layout_paths = [
    [_('Artist/Album'), '%aa/%at'],
    [_('Artist/Album (year)'), '%aa/%at (%ay)'],
    [_('Artist/Artist - Album'), '%aa/%aa - %at'],
    [_('Artist/Artist - Album (year)'), '%aa/%aa - %at (%ay)'],
    [_('Artist - Album'), '%aa - %at'],
    [_('Artist - Album (year)'), '%aa - %at (%ay)'],
    [_('Artist'), '%aa'],
    [_('Album'), '%at'],
    [_('Album (year)'), '%at (%ay)'],
]

library_layout_filenames = [
    [_('Number - Title'), '%tN - %tt'],
    [_('Artist - Title'), '%ta - %tt'],
    [_('Artist - Number - Title'), '%ta - %tN - %tt'],
    [_('Artist (Album) - Number - Title'), '%ta (%at) - %tN - %tt'],
    [_('Title'), '%tt'],
    [_('Number. Artist - Title'), '%tN. %ta - %tt'],
    [_('Number. Title'), '%tN. %tt'],
]

conflict_resolve_variants = [
    [_('Rename'), CONFLICT_ACTION_RENAME],
    [_('Replace'), CONFLICT_ACTION_REPLACE],
    [_('Skip'), CONFLICT_ACTION_SKIP],
    [_('Ask for Action'), CONFLICT_ACTION_ASK],
]

preload_max_size_variants = [
    [_('No size limit'), 0],
    [_('10 MB'), 10],
    [_('20 MB'), 20],
    [_('30 MB'), 30],
    [_('40 MB'), 40],
    [_('50 MB'), 50],
    [_('60 MB'), 60],
    [_('70 MB'), 70],
    [_('80 MB'), 80],
    [_('90 MB'), 90],
    [_('100 MB'), 100],
]

preload_file_formats_variants = [
    [_('All formats'), AUDIO_FORMAT_ALL],
    [_('mp3'), 'mp3'],
]

example_tags = {
    "artist": "Korn",
    "album_artist": "Korn",
    "album": "Issues",
    "title": "Hey Daddy",
    "track_number": 10,
    "date": "",
    "year": 1999,
    "genre": "Nu-Metal",
}

class PrefsSettingsPage(PrefsPageBase):
    name = _('Settings')
    main_box = 'settings_vbox'
    ui_file = 'ui/prefs/settings.ui'
    _values = {}

    def _create_widget(self):
        self._values = {}

        self.library_location_entry = cast(Gtk.Entry, self.ui.get_object('library_location_entry'))
        self.library_location_btn = cast(Gtk.Button, self.ui.get_object('library_location_btn'))
        self.conflict_resolve_combo = cast(Gtk.ComboBox, self.ui.get_object('conflict_resolve_combo'))
        self.dir_hierarchy_combo = cast(Gtk.ComboBox, self.ui.get_object('dir_hierarchy_combo'))
        self.name_template_combo = cast(Gtk.ComboBox, self.ui.get_object('name_template_combo'))
        self.template_example_label = cast(Gtk.Label, self.ui.get_object('template_example_label'))

        self.detect_dirs_ignore_case_check = cast(Gtk.CheckButton, self.ui.get_object('detect_dirs_ignore_case'))
        self.detect_files_ignore_case_check = cast(Gtk.CheckButton, self.ui.get_object('detect_files_ignore_case'))

        self._init_check(self.detect_dirs_ignore_case_check, KEY_DETECT_DIRS_IGNORE_CASE)
        self._init_check(self.detect_files_ignore_case_check, KEY_DETECT_FILES_IGNORE_CASE)

        self.preload_prev_check = cast(Gtk.CheckButton, self.ui.get_object('preload_prev_check'))
        self.preload_next_check = cast(Gtk.CheckButton, self.ui.get_object('preload_next_check'))
        self.preload_hidden_check = cast(Gtk.CheckButton, self.ui.get_object('preload_hidden_check'))

        self.preload_max_file_size_combo = cast(Gtk.ComboBox, self.ui.get_object('preload_max_file_size_combo'))
        self.preload_file_formats_combo = cast(Gtk.ComboBox, self.ui.get_object('preload_file_formats_combo'))

        self._init_check(self.preload_prev_check, KEY_PRELOAD_PREV_TRACK)
        self._init_check(self.preload_next_check, KEY_PRELOAD_NEXT_TRACK)
        self._init_check(self.preload_hidden_check, KEY_PRELOAD_HIDDEN_TRACK)

        self.library_location_entry.set_text(self.account.get_library_path())
        self.library_location_btn.connect('clicked', self._browse_libpath_cb)
        self.library_location_entry.connect("focus-out-event", self._libpath_entry_cb)

        self._init_combo(self.conflict_resolve_combo, conflict_resolve_variants, KEY_CONFLICT_RESOLVE)
        self._init_combo(self.dir_hierarchy_combo, library_layout_paths, KEY_FOLDER_HIERARCHY)
        self._init_combo(self.name_template_combo, library_layout_filenames, KEY_FILENAME_TEMPLATE)

        self._init_combo(self.preload_max_file_size_combo, preload_max_size_variants, KEY_PRELOAD_MAX_FILE_SIZE, True)
        self._init_combo(self.preload_file_formats_combo, preload_file_formats_variants, KEY_PRELOAD_FILE_FORMATS)

        self._update(KEY_FILENAME_TEMPLATE, self.settings[KEY_FILENAME_TEMPLATE])
        self._update_check_sensitive()

    def _update_check_sensitive(self):
        sensitive = self.settings[KEY_PRELOAD_NEXT_TRACK] or self.settings[KEY_PRELOAD_PREV_TRACK]
        self.preload_hidden_check.set_sensitive(sensitive)

    def _init_check(self, checkbox: Gtk.CheckButton, name: str):
        value = self.settings[name]
        checkbox.set_active(bool(value))
        checkbox.connect('toggled', self._on_check_toggled, name)

    def _on_check_toggled(self, checkbox: Gtk.CheckButton, name: str):
        is_checked = checkbox.get_active()
        self.settings.set_boolean(name, is_checked)
        self.on_change(name, is_checked)
        self._update_check_sensitive()

    def _init_combo(self, combo: Gtk.ComboBox, variants: List[List[str]], name: str, variant_int=False):
        idx = 0
        value = self.settings[name]
        store = Gtk.ListStore(int if variant_int else str, str) # type: ignore
        for i, o in enumerate(variants):
            if value == o[1]:
                idx = i
            store.append([o[1], o[0]])
        combo.set_model(store)
        combo.set_active(idx)
        set_combo_text_column(combo, 1)
        combo.connect('changed', self._on_combo_changed, name, variant_int)

    def _on_combo_changed(self, combo: Gtk.ComboBox, name: str, variant_int=False):
        tree_iter = combo.get_active_iter()
        if tree_iter is not None:
            model = cast(Gtk.TreeModel, combo.get_model())
            if model:
                value = model[tree_iter][0]  # pyright: ignore[reportIndexIssue]
                if variant_int:
                    self.settings.set_int(name, value)
                else:
                    self.settings.set_string(name, value)
                self._update(name, value)
                self.on_change(name, value)

    def _update(self, name: str, value):
        # avoid re-execution for identical values
        if self._values.get(name) == value:
            return
        self._values[name] = value

        if name == KEY_LIBRARY_PATH:
            if os.path.isdir(value):
                self.library_location_entry.set_text(value)
                self.account.settings.set_string(KEY_LIBRARY_PATH, value)
            else:
                show_error(_('Directory %s does not exists') % value,
                           _('The selected directory path for downloading music does not exist. Please choose an existing directory or create a new one to proceed.'),
                           parent=self.box)
        elif name in [KEY_FOLDER_HIERARCHY, KEY_FILENAME_TEMPLATE]:
            example = filepath_parse_pattern(
                "%s/%s.mp3" % (self.settings[KEY_FOLDER_HIERARCHY], self.settings[KEY_FILENAME_TEMPLATE]), example_tags)
            self.template_example_label.set_markup('<small><i><b>%s</b> %s</i></small>' % (_("Example Path:"), example))

    def _libpath_entry_cb(self, entry: Gtk.Entry, event):
        self._update(KEY_LIBRARY_PATH, entry.get_text())

    def _browse_libpath_cb(self, *obj):
        f = Gtk.FileChooserDialog(
            title=_("Select download music directory"),
            parent=self.get_window(), # noqa # type: ignore
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=( # noqa # type: ignore
                _("_Cancel"),
                Gtk.ResponseType.CANCEL,
                _("_Open"),
                Gtk.ResponseType.OK,
            ),
        )

        f.set_current_folder(self.account.get_library_path())

        status = f.run() # noqa # type: ignore
        if status == Gtk.ResponseType.OK:
            val = f.get_filename() # noqa # type: ignore
            if val:
                self._update(KEY_LIBRARY_PATH, val)
        f.destroy()
