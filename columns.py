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
import re
import gi
gi.require_version('Gio', '2.0')
from gi.repository import RB  # type: ignore
from gi.repository import GLib, Gio, Gtk
from common import empty_cb, get_entry_location, get_location_audio_id, get_entry_state, get_first_artist, is_telegram_source
from common import get_tree_view_from_entry_view
from storage import Audio
from loader import PinnedLoader, PinnedShortDict
from typing import Dict, Optional, List

import gettext
gettext.install('rhythmbox', RB.locale_dir())
_ = gettext.gettext


class FormatColumn:
    """
    A class for creating the "Format" column in the entry view.
    Displays the audio file format (e.g., mp3, flac) for each entry.
    """
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
        """
        Callback function to set the text for the "Format" column.
        Retrieves the format of the audio file from the source's custom model.
        """
        entry = model.get_value(iter, 0)
        idx = get_location_audio_id(get_entry_location(entry))
        cell.set_property("text", "%s" % self.source.get_custom_model(idx)[1])


class SizeColumn:
    """
    A class for creating the "Size" column in the entry view.
    Displays the size of the audio file for each entry.
    """
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
        """
        Callback function to set the text for the "Size" column.
        Retrieves the size of the audio file from the source's custom model.
        """
        entry = model.get_value(iter, 0)
        idx = get_location_audio_id(get_entry_location(entry))
        cell.set_property("text", "%s" % self.source.get_custom_model(idx)[0])


# A dictionary mapping audio states to their corresponding icon names.
# These icons are used to visually represent the state of an audio file in the UI.
STATE_ICONS = {
    Audio.STATE_DEFAULT : 'tg-state-download-symbolic',
    Audio.STATE_ERROR : 'tg-state-error',
    Audio.STATE_IN_LIBRARY : 'tg-state-library-symbolic',
    Audio.STATE_HIDDEN : 'tg-state-visibility-off-symbolic',
    Audio.STATE_DOWNLOADED : None,
}


class StateColumn:
    """
    A class for creating the "State" column in the entry view.
    Displays the state of the audio file (e.g., downloading, downloaded, hidden) using icons or a spinner.
    """
    _icon_cache = {}

    def __init__(self, source):
        self.plugin = source.plugin
        self._pulse = 0
        self._models = {}
        self.timeout_id = None
        self.connect_id = None

        column = Gtk.TreeViewColumn()
        self.column = column
        column.set_name("state_column")
        pixbuf_renderer = Gtk.CellRendererPixbuf()
        pixbuf_renderer.set_property("mode", Gtk.CellRendererMode.ACTIVATABLE)
        spinner_renderer = Gtk.CellRendererSpinner()

        column.set_title(" ")
        # icon = Gio.ThemedIcon.new("tg-state-download-symbolic")
        # image = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.MENU)
        # column.set_widget(image)
        # image.show()

        column.set_cell_data_func(pixbuf_renderer, self.data_func, "pixbuf") # noqa
        column.set_cell_data_func(spinner_renderer, self.data_func, "spinner") # noqa

        column.pack_start(spinner_renderer, expand=True)
        column.pack_start(pixbuf_renderer, expand=True)

        column.set_expand(False)
        column.set_resizable(False)

        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(36)

        entry_view = source.get_entry_view() # noqa
        self.tree_view = get_tree_view_from_entry_view(entry_view)
        self.entry_view = entry_view

        entry_view.append_column_custom(column, ' ', "tg-state", empty_cb, None, None)
        visible_columns = entry_view.get_property("visible-columns")

        if 'tg-state' not in visible_columns:
            visible_columns.append('tg-state')
            entry_view.set_property("visible-columns", visible_columns)

    def on_click_pressed(self, treeview, event):
        """ Handles the click event on a state column. Checks the state and triggers the loading process """
        if event.button == 1:
            path_info = treeview.get_path_at_pos(int(event.x), int(event.y))
            if path_info is not None:
                path, column, cell_x, cell_y = path_info
                if column == self.column:
                    model = treeview.get_model()
                    iter = model.get_iter(path)
                    if iter is not None:
                        entry = model.get_value(iter, 0)
                        state = get_entry_state(entry)
                        if state == Audio.STATE_DEFAULT:
                            self.plugin.loader.add_entry(entry).start()
        return False

    def activate(self):
        """ Activates the spinner animation and connects the button-release event. """
        if not self.timeout_id:
            self.timeout_id = GLib.timeout_add(100, self.spinner_pulse)
        if not self.connect_id:
            self.connect_id = self.tree_view.connect("button-release-event", self.on_click_pressed)

    def deactivate(self):
        """ Deactivates the spinner animation and disconnects the button-release event. """
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None
        if self.connect_id:
            self.tree_view.disconnect(self.connect_id)
            self.connect_id = None

    def spinner_pulse(self):
        """ Updates the spinner animation for entries in the loading state. """
        self._pulse = 0 if self._pulse == 999999 else self._pulse + 1

        for idx in list(self._models.keys()):
            model, iter = self._models.get(idx, (None, None))
            if model and iter:
                model.emit("row_changed", model.get_path(iter), iter)
            else:
                del self._models[idx]
        return True

    def data_func(self, column, cell, model, iter, cell_type): # noqa
        """
        Callback function to set the icon or spinner for the "State" column.
        Displays an icon or spinner based on the state of the audio file.
        """
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


class InLibraryColumn:
    """
    A class that provides visual markers for entries in the library view with icons
    to indicate their presence in the library.
    """
    _initialized = False
    library_map = set()
    hidden_map = set()

    @staticmethod
    def init_once(plugin):
        """
        Sets up the library map by loading existing entries and connects to the
        'entry_added_to_library' signal to keep the map updated.
        """
        if not InLibraryColumn._initialized:
            InLibraryColumn._initialized = True

        plugin.connect('entry_added_to_library', InLibraryColumn.on_entry_added_to_library)
        shell = plugin.shell
        db = shell.props.db
        entry_type = db.entry_type_get_by_name('song')
        source = shell.get_source_by_entry_type(entry_type)
        model = source.get_property('query-model')
        iter = model.get_iter_first()

        while iter:
            entry = model.get_value(iter, 0)
            InLibraryColumn.library_map.add(InLibraryColumn.entry_to_data(entry))
            iter = model.iter_next(iter)

        def callback(row):
            audio = Audio(row)
            artist = InLibraryColumn.normalize(get_first_artist(audio.artist))
            title = InLibraryColumn.normalize(audio.title)
            item = (artist, title)

            if item not in InLibraryColumn.library_map:
                InLibraryColumn.hidden_map.add(item)

        plugin.storage.each(callback, 'audio', {'is_moved': 0, 'is_hidden': 1})

    def __init__(self, source):
        """
        Creates and configures a column in the entry view to display visual markers
        indicating whether entries are in the library.
        """
        self.shell = source.plugin.shell

        self.icon_in_library = Gio.ThemedIcon.new('audio-x-generic-symbolic')
        self.icon_hidden = Gio.ThemedIcon.new('tg-state-visibility-off-symbolic')

        column = Gtk.TreeViewColumn()
        renderer = Gtk.CellRendererPixbuf()

        column.set_title(" ")
        # image = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic", Gtk.IconSize.MENU)
        # column.set_widget(image)
        # image.show()

        column.set_reorderable(False)
        column.set_cell_data_func(renderer, self.data_func, None)  # noqa
        column.pack_start(renderer, expand=True)

        column.set_expand(False)
        column.set_resizable(False)

        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(28)

        entry_view = source.get_entry_view()
        entry_view.append_column_custom(column, ' ', 'tg-in-library', empty_cb, None, None)
        visible_columns = entry_view.get_property('visible-columns')

        if 'tg-in-library' not in visible_columns:
            visible_columns.append('tg-in-library')
            entry_view.set_property('visible-columns', visible_columns)

        tree_view: Gtk.TreeView = column.get_tree_view()
        columns: list[Gtk.TreeViewColumn] = tree_view.get_columns()
        if column in columns:
            tree_view.remove_column(column)
            tree_view.insert_column(column, -2)

    def data_func(self, column, cell, model, iter, *_):
        """ Cell data function for the visual marker column. """
        gicon = None
        entry = model.get_value(iter, 0)
        if InLibraryColumn.entry_to_data(entry) in InLibraryColumn.library_map:
            gicon = self.icon_in_library
        elif InLibraryColumn.entry_to_data(entry) in InLibraryColumn.hidden_map:
            gicon = self.icon_hidden
        cell.props.gicon = gicon

    @staticmethod
    def entry_to_data(entry):
        """ Convert an entry to normalized artist/title data. """
        artist = InLibraryColumn.normalize(get_first_artist(entry.get_string(RB.RhythmDBPropType.ARTIST)))
        title = InLibraryColumn.normalize(entry.get_string(RB.RhythmDBPropType.TITLE))
        return artist, title

    @staticmethod
    def normalize(s):
        """ Normalize a string by stripping whitespace and converting to lowercase. """
        return s.strip().casefold()

    @staticmethod
    def on_entry_added_to_library(plugin, entry):
        """ Callback for when an entry is added to the library. Adds the entry's normalized data to the library map. """
        InLibraryColumn.library_map.add(InLibraryColumn.entry_to_data(entry))


class TopPicks:
    """
    A class for tracking and ranking artists based on the ratings of their songs.
    Used to identify top-rated artists and assign them levels (e.g., low, medium, high, top).
    """
    LEVEL_NONE = 0
    LEVEL_LOW = 1
    LEVEL_MEDIUM = 2
    LEVEL_HIGH = 3
    LEVEL_TOP = 4
    LEVEL_FEATURED = 5
    LEVEL_PINNED = 6

    def __init__(self, plugin):
        self.plugin = plugin
        self.shell = plugin.shell
        self.stats: Dict[str, Dict[int | str, int]] = {}
        self.artists: Dict[str, int] = {}
        self.featured: Dict[str, List[str]] = {}
        self.pinned: Dict[str, List[int]] = {}
        self.pinned_loader: Dict[int, PinnedLoader] = {}
        self.select_handler = None
        self.source = None

    def activate(self):
        self.select_handler = self.shell.connect("notify::selected-page", self._on_source_changed)

    def deactivate(self):
        if self.shell and self.select_handler:
            self.shell.disconnect(self.select_handler)
            self.select_handler = None

    def _on_source_changed(self, *args):
        source = self.shell.props.selected_page
        self.source = None
        self.pinned = {}

        if is_telegram_source(source):
            self.source = source
            if source.chat_id not in self.pinned_loader:
                self.pinned_loader[source.chat_id] = PinnedLoader(source)
            self.pinned_loader[source.chat_id].start(self._set_pinned)
        else:
            self.source = None

    def _set_pinned(self, chat_id: int, messages: Dict[int, PinnedShortDict]):
        if self.source and chat_id == self.source.chat_id:
            for message in list(messages.values()):
                artist = message['artist']
                date = message['date']
                if artist not in self.pinned:
                    self.pinned[artist] = [date]
                elif date not in self.pinned[artist]:
                    self.pinned[artist].append(date)

    def _read_featured(self):
        plugin_dir = Gio.file_new_for_path(RB.user_data_dir()).resolve_relative_path('telegram').get_path()
        featured_file = os.path.join(str(plugin_dir), 'featured.txt')
        pattern_number = re.compile(r'^\d+[\.\)\s]+')

        if os.path.exists(featured_file):
            with open(featured_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = None
                    for separator in ['—', '-']:
                        if separator in line:
                            parts = line.split(separator, 1)
                            break

                    if parts and len(parts) == 2:
                        artist = pattern_number.sub('', parts[0]).strip().lower()
                        title = parts[1].strip().lower()
                        if artist not in self.featured:
                            self.featured[artist] = []
                        self.featured[artist].append(title)

    def collect(self):
        """
        Collects and ranks artists based on the ratings of their songs.
        Identifies the top 10% of artists and assigns them the "top" level.
        """
        self.stats = {}
        self.artists = {}
        db = self.shell.props.db
        entry_type = db.entry_type_get_by_name('song')
        source = self.shell.get_source_by_entry_type(entry_type)
        model = source.get_property('query-model')
        iter = model.get_iter_first()
        self._read_featured()

        while iter:
            entry = model.get_value(iter, 0)
            rating = entry.get_double(RB.RhythmDBPropType.RATING)
            if rating >= 4:
                artist = get_first_artist(entry.get_string(RB.RhythmDBPropType.ARTIST)).lower()
                self._add_rating(artist, int(rating))
            iter = model.iter_next(iter)

        if len(self.stats):
            sorted_artists = sorted(self.stats.items(), key=lambda x: (x[1].get(5, 0), x[1].get(4, 0)), reverse=True)
            top_10_percent = int(len(sorted_artists) * 0.10)
            top_artists = sorted_artists[:top_10_percent]
            for artist in top_artists:
                self.stats[artist[0]]["top"] = 1

        for artist in self.stats:
            level = self._comp_rated_level(artist)
            self.artists[artist] = level

        self.stats = {}

    def _add_rating(self, artist: str, rating: int):
        """ Adds a rating for an artist to the internal dictionary. """
        artist = artist.lower()
        if artist not in self.stats:
            self.stats[artist] = { 5: 0, 4: 0 }
        self.stats[artist][rating] += 1

    def _comp_rated_level(self, artist: str) -> int:
        """ Computes the level of an artist based on their ratings. """
        artist = get_first_artist(artist.lower())
        artist_level = self.stats.get(artist)

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

    def get_level(self, artist: str, entry) -> int:
        """ Retrieves the level of an artist based on their ratings. """
        artist = get_first_artist(artist.lower())
        artist_level = self.artists.get(artist)

        if not artist_level and ',' in artist:
            artist = get_first_artist(artist, ',')
            artist_level = self.artists.get(artist)

        if artist_level:
            return artist_level

        if artist in self.pinned:
            idx = get_location_audio_id(get_entry_location(entry))
            audio_date = self.source.get_custom_model(idx)[2]
            pinned_dates = self.pinned[artist]
            for pinned_date in pinned_dates:
                if abs(audio_date - pinned_date) < 86400:
                    return TopPicks.LEVEL_PINNED

        if artist in self.featured:
            title = entry.get_string(RB.RhythmDBPropType.TITLE).lower()
            if title in self.featured[artist]:
                return TopPicks.LEVEL_FEATURED
            album = entry.get_string(RB.RhythmDBPropType.ALBUM).lower()
            if album in self.featured[artist]:
                return TopPicks.LEVEL_FEATURED

        return TopPicks.LEVEL_NONE


# A dictionary mapping artist rating levels to their corresponding emojis.
# These emojis are used to visually represent the popularity or rating level of an artist in the UI.
TOP_PICKS_EMOJI = {
    TopPicks.LEVEL_NONE: '',
    TopPicks.LEVEL_LOW: '⭐',  # star
    TopPicks.LEVEL_MEDIUM: '❤️', # heart
    TopPicks.LEVEL_HIGH: '🔥', # fire
    TopPicks.LEVEL_TOP: '🔥', # fire
    TopPicks.LEVEL_FEATURED: '✨', # sparkes
    TopPicks.LEVEL_PINNED: '📌', # pin
    # TopRated.LEVEL_TOP:     '🏆', # cup
}


class TopPicksColumn:
    """
    A class for creating the "Top Picks" column in the entry view.
    Displays an emoji (e.g., star, heart, fire) based on the artist's level.
    """
    def __init__(self, source):
        self.plugin = source.plugin

        column = Gtk.TreeViewColumn()
        renderer = Gtk.CellRendererText()

        column.set_title(" ")
        # image = Gtk.Image.new_from_icon_name("emblem-favorite-symbolic", Gtk.IconSize.MENU)
        # column.set_widget(image)
        # image.show()

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

    def data_func(self, column, cell, model, iter, *_):
        """
        Callback function to set the emoji for the "Top Picks" column.
        Retrieves the artist's level and displays the corresponding emoji.
        """
        entry = model.get_value(iter, 0)
        artist = entry.get_string(RB.RhythmDBPropType.ARTIST)

        if self.plugin.top_picks:
            level = self.plugin.top_picks.get_level(artist, entry)
            cell.set_property('text', TOP_PICKS_EMOJI[level])
        else:
            cell.set_property('text', '')
