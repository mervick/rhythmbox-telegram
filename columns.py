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
gi.require_version('Gio', '2.0')
from gi.repository import GObject, RB, GLib, Gio, Gtk
from common import empty_cb, get_entry_location, get_location_audio_id, get_entry_state, get_first_artist
from storage import Audio
from typing import Dict


class FormatColumn:
    def __init__(self, source):
        self.source = source

        entry_view = source.get_entry_view() # noqa

        column = Gtk.TreeViewColumn()
        renderer = Gtk.CellRendererText()

        column.set_title(_("Format"))
        column.set_cell_data_func(renderer, self.data_func, None) # noqa

        column.pack_start(renderer, expand=False)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        entry_view.set_fixed_column_width(column, renderer, ["mp3", "flac"])

        column.set_expand(False)
        column.set_resizable(True)

        entry_view.append_column_custom(column, _("Format"), "tg-format", empty_cb, None, None)
        visible_columns = entry_view.get_property("visible-columns")

        if 'tg-format' not in visible_columns:
            visible_columns.append('tg-format')
            entry_view.set_property("visible-columns", visible_columns)

    def data_func(self, column, cell, model, iter, *data): # noqa
        entry = model.get_value(iter, 0)
        idx = get_location_audio_id(get_entry_location(entry))
        cell.set_property("text", "%s" % self.source.get_custom_model(idx)[1])


class SizeColumn:
    def __init__(self, source):
        self.source = source

        entry_view = source.get_entry_view() # noqa

        column = Gtk.TreeViewColumn()
        renderer = Gtk.CellRendererText()

        column.set_title(_("Size"))
        column.set_cell_data_func(renderer, self.data_func, None) # noqa

        column.pack_start(renderer, expand=False)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        entry_view.set_fixed_column_width(column, renderer, ["4kb", "121.1MB"])

        column.set_expand(False)
        column.set_resizable(True)

        entry_view.append_column_custom(column, _("Size"), "tg-size", empty_cb, None, None)
        visible_columns = entry_view.get_property("visible-columns")

        if 'tg-size' not in visible_columns:
            visible_columns.append('tg-size')
            entry_view.set_property("visible-columns", visible_columns)

    def data_func(self, column, cell, model, iter, *data): # noqa
        entry = model.get_value(iter, 0)
        idx = get_location_audio_id(get_entry_location(entry))
        cell.set_property("text", "%s" % self.source.get_custom_model(idx)[0])


STATE_ICONS = {
    Audio.STATE_DEFAULT : 'tg-state-download-symbolic',
    Audio.STATE_ERROR : 'tg-state-error',
    Audio.STATE_IN_LIBRARY : 'tg-state-library-symbolic',
    Audio.STATE_HIDDEN : 'tg-state-visibility-off-symbolic',
    Audio.STATE_DOWNLOADED : None,
}


class StateColumn:
    _icon_cache = {}

    def __init__(self, source):
        self._pulse = 0
        self._models = {}
        self.timeout_id = None

        column = Gtk.TreeViewColumn()
        pixbuf_renderer = Gtk.CellRendererPixbuf()
        spinner_renderer = Gtk.CellRendererSpinner()

        column.set_title(" ")
        column.set_cell_data_func(pixbuf_renderer, self.data_func, "pixbuf") # noqa
        column.set_cell_data_func(spinner_renderer, self.data_func, "spinner") # noqa

        column.pack_start(spinner_renderer, expand=True)
        column.pack_start(pixbuf_renderer, expand=True)

        column.set_expand(False)
        column.set_resizable(False)

        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(36)

        entry_view = source.get_entry_view() # noqa
        self.entry_view = entry_view

        entry_view.append_column_custom(column, ' ', "tg-state", empty_cb, None, None)
        visible_columns = entry_view.get_property("visible-columns")

        if 'tg-state' not in visible_columns:
            visible_columns.append('tg-state')
            entry_view.set_property("visible-columns", visible_columns)

    def activate(self):
        if not self.timeout_id:
            self.timeout_id = GLib.timeout_add(100, self.spinner_pulse)

    def deactivate(self):
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

    def spinner_pulse(self):
        self._pulse = 0 if self._pulse == 999999 else self._pulse + 1

        for idx in self._models.keys():
            model, iter = self._models[idx]
            if model and iter:
                model.emit("row_changed", model.get_path(iter), iter)
            else:
                del self._models[idx]
        return True

    def data_func(self, column, cell, model, iter, cell_type): # noqa
        entry = model.get_value(iter, 0)
        idx = model.get_value(iter, 1)
        state = get_entry_state(entry)
        is_spinner = cell_type == 'spinner'

        if state == Audio.STATE_LOADING:
            cell.props.visible = is_spinner
            if is_spinner:
                self._models[idx] = [model, iter]
                cell.props.active = True
                cell.props.pulse = self._pulse
        else:
            cell.props.visible = not is_spinner
            if is_spinner:
                if idx in self._models:
                    del self._models[idx]
                cell.props.active = False
            else:
                if state in StateColumn._icon_cache:
                    gicon = StateColumn._icon_cache[state]
                else:
                    icon_name = STATE_ICONS[state] if state in STATE_ICONS else STATE_ICONS[Audio.STATE_DEFAULT]
                    gicon = Gio.ThemedIcon.new(icon_name) if icon_name is not None else None
                    StateColumn._icon_cache[state] = gicon
                cell.props.gicon = gicon


class TopPicks:
    LEVEL_NONE = 0
    LEVEL_LOW = 1
    LEVEL_MEDIUM = 2
    LEVEL_HIGH = 3
    LEVEL_TOP = 4

    def __init__(self, shell):
        self.shell = shell
        self.artists: Dict[str, Dict[int | str, int] | int] = {}

    def collect(self):
        self.artists = {}
        db = self.shell.props.db
        entry_type = db.entry_type_get_by_name('song')
        source = self.shell.get_source_by_entry_type(entry_type)
        model = source.get_property('query-model')
        iter = model.get_iter_first()

        while iter:
            entry = model.get_value(iter, 0)
            rating = entry.get_double(RB.RhythmDBPropType.RATING)
            if rating >= 4:
                artist = get_first_artist(entry.get_string(RB.RhythmDBPropType.ARTIST)).lower()
                self._add_rating(artist, int(rating))
            iter = model.iter_next(iter)

        if len(self.artists):
            sorted_artists = sorted(self.artists.items(), key=lambda x: (x[1].get(5, 0), x[1].get(4, 0)), reverse=True)
            top_10_percent = int(len(sorted_artists) * 0.10)
            top_artists = sorted_artists[:top_10_percent]
            for artist in top_artists:
                self.artists[artist[0]]["top"] = 1

        for artist in self.artists:
            level = self._comp_rated_level(artist)
            self.artists[artist] = level

    def _add_rating(self, artist: str, rating: int):
        artist = artist.lower()
        if artist not in self.artists:
            self.artists[artist] = {
                5: 0,
                4: 0
            }
        self.artists[artist][rating] += 1

    def _comp_rated_level(self, artist: str):
        artist = get_first_artist(artist.lower())
        artist_level = self.artists.get(artist)

        if not artist_level:
            return TopPicks.LEVEL_NONE
        is_top = artist_level.get('top', 0)
        if is_top:
            return TopPicks.LEVEL_TOP
        star_5 = artist_level.get(5, 0)
        if star_5 >= 10:
            return TopPicks.LEVEL_HIGH
        if star_5 >= 2:
            return TopPicks.LEVEL_MEDIUM
        star_4 = artist_level.get(4, 0)
        if star_5 >= 1 or star_4 > 2:
            return TopPicks.LEVEL_LOW

        return TopPicks.LEVEL_NONE

    def get_level(self, artist: str):
        artist = get_first_artist(artist.lower())
        artist_level = self.artists.get(artist)

        if not artist_level and ',' in artist:
            artist = get_first_artist(artist, ',')
            artist_level = self.artists.get(artist)

        return artist_level if artist_level else TopPicks.LEVEL_NONE


TOP_PICKS_EMOJI = {
    TopPicks.LEVEL_NONE: '',
    TopPicks.LEVEL_LOW: '⭐',  # star
    TopPicks.LEVEL_MEDIUM: '❤️', # heart
    TopPicks.LEVEL_HIGH: '🔥', # fire
    TopPicks.LEVEL_TOP: '🔥', # fire
    # TopRated.LEVEL_TOP:     '🏆', # cup
}


class TopPicksColumn:
    def __init__(self, source):
        self.plugin = source.plugin

        column = Gtk.TreeViewColumn()
        renderer = Gtk.CellRendererText()

        column.set_title(" ")
        column.set_reorderable(False)
        column.set_cell_data_func(renderer, self.data_func, None)  # noqa
        column.pack_start(renderer, expand=True)

        column.set_expand(False)
        column.set_resizable(False)

        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(28)

        entry_view = source.get_entry_view()
        entry_view.append_column_custom(column, ' ', 'tg-match', empty_cb, None, None)
        visible_columns = entry_view.get_property('visible-columns')

        if 'tg-match' not in visible_columns:
            visible_columns.append('tg-match')
            entry_view.set_property('visible-columns', visible_columns)

        tree_view = column.get_tree_view()
        columns = tree_view.get_columns()
        if column in columns:
            tree_view.remove_column(column)
            tree_view.insert_column(column, 1)

    def data_func(self, column, cell, model, iter, *data):
        entry = model.get_value(iter, 0)
        artist = entry.get_string(RB.RhythmDBPropType.ARTIST)

        if self.plugin.top_picks:
            level = self.plugin.top_picks.get_level(artist)
            cell.set_property('text', TOP_PICKS_EMOJI[level])
        else:
            cell.set_property('text', '')
