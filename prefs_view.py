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
from gi.repository import RB
from gi.repository import Gtk, GLib
from prefs_base import PrefsPageBase, set_combo_text_column
from account import KEY_RATING_COLUMN, KEY_DATE_ADDED_COLUMN, KEY_FILE_SIZE_COLUMN, KEY_AUDIO_FORMAT_COLUMN, KEY_TOP_PICKS_COLUMN
from account import KEY_PAGE_GROUP, KEY_AUDIO_VISIBILITY
from account import VAL_AV_VISIBLE, VAL_AV_HIDDEN, VAL_AV_ALL, VAL_AV_DUAL
from storage import Audio
from common import get_first_artist

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
        self.sync_hidden_btn = self.ui.get_object('sync_hidden_btn')
        self.sync_hidden_btn.connect('clicked', self._sync_hidden_chats_cb)

        self.restart_warning_box = self.ui.get_object('restart_warning_box')

        self.top_picks_check = self.ui.get_object('top_picks_check')
        self.rating_check = self.ui.get_object('rating_check')
        self.date_added_check = self.ui.get_object('date_added_check')
        self.size_check = self.ui.get_object('size_check')
        self.format_check = self.ui.get_object('format_check')

        self._init_check(self.top_picks_check, KEY_TOP_PICKS_COLUMN)
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

    def _sync_hidden_chats_cb(self, *args):
        db = self.plugin.storage.db
        blob = {}
        album = []
        titles = []
        data = []
        keys = set()
        max_upd_size = 50 * 3

        self.sync_hidden_btn.set_sensitive(False)

        def done():
            self.sync_hidden_btn.set_sensitive(True)

        def write(values):
            count = int(len(values) / 3)
            placeholders = ', '.join(['(?, ?, ?)'] * count)
            query = f"""
                UPDATE audio
                SET is_hidden = 1
                WHERE is_hidden = 0 AND (artist, title, duration) IN ({placeholders})
            """
            db_cur = db.cursor()
            db_cur.execute(query, values)
            db.commit()
            db_cur.close()

        def flash_idle(data_iter):
            values = []
            try:
                while True:
                    item = next(data_iter)
                    artist, title, duration = item
                    values.append(artist)
                    values.append(title)
                    values.append(duration)

                    if len(values) >= max_upd_size:
                        write(values.copy())
                        values = []
                        return True
            except StopIteration:
                if len(values) > 0:
                    write(values.copy())
            done()
            return False

        def update():
            if len(album) > 2:
                for audio in album:
                    key = (audio.artist, audio.title, audio.duration)
                    if key not in keys:
                        keys.add(key)
                        data.append(list(key))
                    key = (get_first_artist(audio.artist), audio.title, audio.duration)
                    if key not in keys:
                        keys.add(key)
                        data.append(list(key))
            titles.clear()
            album.clear()

        def each(row):
            audio = Audio(row)
            artist = get_first_artist(audio.artist)
            if artist and audio.title:
                if audio.title in titles:
                    return
                if blob.get('artist') == artist:
                    # if previous album was empty, then set album
                    if not blob.get('album') and audio.album:
                        blob['album'] = audio.album
                    # add to album if same album name or
                    if blob.get('album') == audio.album or (not audio.album and len(album)):
                        titles.append(audio.title)
                        album.append(audio)
                        return
            update()
            blob['artist'] = artist
            blob['album'] = audio.album
            album.append(audio)

        self.plugin.storage.each(table='audio', where={'is_hidden': 1}, order='date DESC', callback=each)
        update()
        GLib.idle_add(flash_idle, iter(data))
