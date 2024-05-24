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

import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import RB
from gi.repository import Gtk
from PrefsPage import PrefsPage, set_combo_text_column
from common import filepath_parse_pattern, show_error

import gettext
gettext.install('rhythmbox', RB.locale_dir())


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

page_groups = [
    [_('Telegram'), 'telegram'],
    [_('Library'), 'library'],
    [_('Shared'), 'shared'],
    [_('Stores'), 'stores'],
    [_('Devices'), 'devices'],
    [_('Playlists'), 'playlists'],
]

color_schemas = [
    [_('Auto'), 'auto'],
    [_('Dark'), 'dark'],
    [_('Light'), 'light'],
]

conflict_resolve_variants = [
    [_('Rename'), 'rename'],
    [_('Overwrite'), 'overwrite'],
    [_('Skip'), 'skip'],
]

example_tags = {
    "artist": "Korn",
    "album": "Issues",
    "title": "Hey Daddy",
    "track_number": 10,
    "date": "",
    "year": 1999,
    "genre": "Nu-Metal",
}

class PrefsSettingsPage(PrefsPage):
    name = _('Settings')
    main_box = 'settings_vbox'
    ui_file = 'ui/prefs/settings.ui'
    _values = {}

    def _create_widget(self):
        self.library_location_entry = self.ui.get_object('library_location_entry')
        self.library_location_btn = self.ui.get_object('library_location_btn')
        self.conflict_resolve_combo = self.ui.get_object('conflict_resolve_combo')
        self.dir_hierarchy_combo = self.ui.get_object('dir_hierarchy_combo')
        self.name_template_combo = self.ui.get_object('name_template_combo')
        self.template_example_label = self.ui.get_object('template_example_label')
        self.page_group_combo = self.ui.get_object('page_group_combo')
        self.color_scheme_combo = self.ui.get_object('color_scheme_combo')

        self.library_location_entry.set_text(self.account.get_library_path())
        self.library_location_btn.connect('clicked', self._browse_libpath_cb)
        self.library_location_entry.connect("focus-out-event", self._libpath_entry_cb)

        self._init_combo(self.conflict_resolve_combo, conflict_resolve_variants, 'conflict-resolve')
        self._init_combo(self.color_scheme_combo, color_schemas, 'color-scheme')
        self._init_combo(self.page_group_combo, page_groups, 'page-group')
        self._init_combo(self.dir_hierarchy_combo, library_layout_paths, 'folder-hierarchy')
        self._init_combo(self.name_template_combo, library_layout_filenames, 'filename-template')

        self._update('filename-template', self.settings['filename-template'])

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
            self.settings.set_string(name, value)
            self._update(name, value)
            self.on_change(name, value)

    def _update(self, name, value):
        # avoid re-execution for identical values
        if self._values.get(name) == value:
            return
        self._values[name] = value

        if name == 'library-path':
            if os.path.isdir(value):
                self.library_location_entry.set_text(value)
                self.account.settings.set_string('library-path', value)
            else:
                show_error(_('Directory %s does not exists') % value,
                           _('The selected directory path for downloading music does not exist. Please choose an existing directory or create a new one to proceed.'))
        elif name in ['folder-hierarchy', 'filename-template']:
            example = filepath_parse_pattern(
                "%s/%s.mp3" % (self.settings['folder-hierarchy'], self.settings['filename-template']), example_tags)
            self.template_example_label.set_markup('<small><i><b>%s</b> %s</i></small>' % (_("Example Path:"), example))

    def _libpath_entry_cb(self, entry, event):
        self._update('library-path', entry.get_text())

    def _browse_libpath_cb(self, *obj):
        f = Gtk.FileChooserDialog(
            title=_("Select download music directory"),
            parent=self.get_window(), # noqa
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=( # noqa
                _("_Cancel"),
                Gtk.ResponseType.CANCEL,
                _("_Open"),
                Gtk.ResponseType.OK,
            ),
        )

        f.set_current_folder(self.account.get_library_path())

        status = f.run() # noqa
        if status == Gtk.ResponseType.OK:
            val = f.get_filename() # noqa
            if val:
                self._update('library-path', val)
        f.destroy()
