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

from gi.repository import RB
from gi.repository import GdkPixbuf
from gi.repository import GObject, Gtk, Gio, Gdk, GLib
from common import to_location, get_location_data, empty_cb, detect_theme_scheme
from TelegramLoader import PlaylistLoader, AudioDownloader

import gettext

from TelegramStorage import TgAudio

gettext.install('rhythmbox', RB.locale_dir())


state_dark_icons = {
    'DEFAULT' : '/icons/hicolor/scalable/state/download-dark.svg',
    'STATE_ERROR' : '/icons/hicolor/scalable/state/error.svg',
    'STATE_IN_LIBRARY' : '/icons/hicolor/scalable/state/library-dark.svg',
    'STATE_DOWNLOADED' : '/icons/hicolor/scalable/state/empty.svg',
}

state_light_icons = {
    'DEFAULT' : '/icons/hicolor/scalable/state/download-light.svg',
    'STATE_ERROR' : '/icons/hicolor/scalable/state/error.svg',
    'STATE_IN_LIBRARY' : '/icons/hicolor/scalable/state/library-light.svg',
    'STATE_DOWNLOADED' : '/icons/hicolor/scalable/state/empty.svg',
}


class StateColumn:
    _icon_cache = {}

    def __init__(self, source):
        scheme = source.plugin.settings['color-scheme']
        if scheme == 'auto':
            scheme = detect_theme_scheme()
        self.icons = state_dark_icons if scheme == 'dark' else state_light_icons
        # reset icon cache after change scheme
        if StateColumn._icon_cache.get('scheme') != scheme:
            StateColumn._icon_cache = {'scheme': scheme}

        self._pulse = 0
        self._models = {}
        self.timeout_id = None
        self.plugin_dir = source.plugin.plugin_info.get_data_dir()

        column = Gtk.TreeViewColumn()
        pixbuf_renderer = Gtk.CellRendererPixbuf()
        spinner_renderer = Gtk.CellRendererSpinner()

        column.add_attribute(spinner_renderer, "active", 1)
        column.add_attribute(spinner_renderer, "pulse", 1)

        column.set_title(" ")
        column.set_cell_data_func(pixbuf_renderer, self.model_data_func, "pixbuf") # noqa
        column.set_cell_data_func(spinner_renderer, self.model_data_func, "spinner") # noqa

        column.pack_start(spinner_renderer, expand=True)
        column.pack_start(pixbuf_renderer, expand=True)

        column.set_expand(False)
        column.set_resizable(False)

        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(36)

        entry_view = source.get_entry_view()
        self.entry_view = entry_view
        entry_view.append_column_custom(column, ' ', "tg-state", empty_cb, None, None)
        visible_columns = entry_view.get_property("visible-columns")
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

    def model_data_func(self, column, cell, model, iter, cell_type): # noqa
        entry = model.get_value(iter, 0)
        idx = model.get_value(iter, 1)
        state = entry.get_string(RB.RhythmDBPropType.COMMENT)
        is_spinner = cell_type == 'spinner'

        if state == 'STATE_LOADING':
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
                    icon = StateColumn._icon_cache[state]
                else:
                    filename = self.icons[state] if state in self.icons else self.icons['DEFAULT']
                    filepath = self.plugin_dir + filename
                    icon = GdkPixbuf.Pixbuf.new_from_file(filepath)
                    StateColumn._icon_cache[state] = icon
                cell.props.pixbuf = icon


class TelegramSource(RB.BrowserSource):
    def __init__(self):
        self.is_activated = False
        RB.BrowserSource.__init__(self)
        self.app = Gio.Application.get_default()
        self.initialised = False
        self.shell = None
        self.db = None
        self.entry_type = None
        self.loader = None
        self.plugin = None
        self.chat_id = None
        self.loaded_entries = []

    def setup(self, plugin, chat_id):
        self.initialised = False
        shell = self.props.shell
        self.shell = shell
        self.db = shell.props.db
        self.entry_type = self.props.entry_type
        self.plugin = plugin
        self.chat_id = chat_id
        self.loader = None
        self.state_column = StateColumn(self) # noqa
        self.loaded_entries = []

    def do_deselected(self):
        self.state_column.deactivate()
        if self.loader is not None:
            self.loader.stop()

    def do_selected(self):
        self.state_column.activate()
        self.get_entry_view().set_sorting_order("Location", Gtk.SortType.DESCENDING)

        if not self.initialised:
            self.initialised = True
            self.add_entries()

        self.loader = PlaylistLoader(self.chat_id, self.add_entry)
        self.loader.start()

    def add_entries(self):
        all_audio = self.plugin.storage.get_chat_audio(self.chat_id)
        for audio in all_audio:
            self.add_entry(audio)

    def add_entry(self, audio):
        if audio.id not in self.loaded_entries:
            self.loaded_entries.append(audio.id)
            location = to_location(self.plugin.api.hash, audio.created_at, self.chat_id, audio.message_id)
            entry = self.db.entry_lookup_by_location(location)
            if not entry:
                entry = RB.RhythmDBEntry.new(self.db, self.entry_type, location)
                self.db.entry_set(entry, RB.RhythmDBPropType.TRACK_NUMBER, audio.track_number)
                self.db.entry_set(entry, RB.RhythmDBPropType.TITLE, audio.title)
                self.db.entry_set(entry, RB.RhythmDBPropType.ARTIST, audio.artist)
                self.db.entry_set(entry, RB.RhythmDBPropType.ALBUM, audio.album)
                self.db.entry_set(entry, RB.RhythmDBPropType.DURATION, audio.duration)
                self.db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(audio.created_at))
                self.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, audio.get_state())
                self.db.entry_set(entry, RB.RhythmDBPropType.DATE, int(audio.date))
                self.db.commit()

    def do_can_delete(self):
        return True

    def do_can_copy(self):
        return False

    def do_can_pause(self):
        return True

    def do_can_add_to_queue(self):
        return True

    def browse_action(self):
        screen = self.props.shell.props.window.get_screen()
        entries = self.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        entry = entries[0]
        location = entry.get_string(RB.RhythmDBPropType.LOCATION)
        chat_id, message_id = get_location_data(location)
        audio = TgAudio({"chat_id": chat_id,  "message_id": message_id})
        url = audio.get_link()
        Gtk.show_uri(screen, url, Gdk.CURRENT_TIME)

    def download_action(self):
        entries = self.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        AudioDownloader(self.plugin, entries).start()

    def hide_action(self):
        pass


GObject.type_register(TelegramSource)
