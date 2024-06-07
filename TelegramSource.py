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

import rb
from gi.repository import RB
from gi.repository import GdkPixbuf
from gi.repository import GObject, Gtk, Gio, Gdk, GLib
from common import to_location, get_location_data, empty_cb, detect_theme_scheme, SingletonMeta, file_uri, TG_RhythmDBPropType
from TelegramLoader import PlaylistLoader
from TelegramStorage import TgAudio

import gettext
gettext.install('rhythmbox', RB.locale_dir())


state_dark_icons = {
    'DEFAULT' : '/icons/hicolor/scalable/state/download-dark.svg',
    'STATE_ERROR' : '/icons/hicolor/scalable/state/error.svg',
    'STATE_IN_LIBRARY' : '/icons/hicolor/scalable/state/library-dark.svg',
    'STATE_DOWNLOADED' : '/icons/hicolor/scalable/state/empty.svg',
    'STATE_HIDDEN' : '/icons/hicolor/scalable/state/visibility-off-dark.svg',
}

state_light_icons = {
    'DEFAULT' : '/icons/hicolor/scalable/state/download-light.svg',
    'STATE_ERROR' : '/icons/hicolor/scalable/state/error.svg',
    'STATE_IN_LIBRARY' : '/icons/hicolor/scalable/state/library-light.svg',
    'STATE_DOWNLOADED' : '/icons/hicolor/scalable/state/empty.svg',
    'STATE_HIDDEN' : '/icons/hicolor/scalable/state/visibility-off-light.svg',
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
        state = entry.get_string(TG_RhythmDBPropType.STATE)
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


class DownloadBar(metaclass=SingletonMeta):
    def __init__(self, plugin):
        self.plugin = plugin
        self.source = None
        self.active = False
        self.info = {}
        plugin.connect('update_download_info', self.update_download_info)

    def deactivate(self, source):
        self.active = False

    def activate(self, source):
        self.source = source
        if source.bar_ui is None:
            entry_view = source.get_entry_view()
            builder = Gtk.Builder()
            builder.add_from_file(rb.find_plugin_file(source.plugin, "ui/status.ui"))
            status_box = builder.get_object('status_box')
            source.bar_ui = {
                "box": status_box,
                "counter": builder.get_object('counter_label'),
                "filename": builder.get_object('filename_label'),
                "progress": builder.get_object('progress_bar'),
            }
            entry_view.pack_end(status_box, False, False, 0)
            status_box.show_all()
            status_box.props.visible = False

        self.active = True
        self._update_ui()

    def _update_ui(self):
        if not self.active:
            return

        if self.source:
            is_visible = self.info.get('active', False)
            self.source.bar_ui["box"].props.visible = is_visible
            if is_visible:
                self.source.bar_ui["counter"].set_text(_('File %s of %s') % (self.info.get('index', 1), self.info.get('total', 1)))
                self.source.bar_ui["filename"].set_text(self.info.get('filename', ''))
                self.source.bar_ui["progress"].set_fraction(self.info.get('fraction', 0.0))

    def update_download_info(self, plugin,  info):
        self.info = info
        self._update_ui()


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
        self.chat_title = None
        self.bar = None
        self.bar_ui = None
        self.entry_updated_id = None
        self.loaded_entries = []

    def setup(self, plugin, chat_id, chat_title):
        self.initialised = False
        shell = self.props.shell
        self.shell = shell
        self.db = shell.props.db
        self.set_property("query-model", RB.RhythmDBQueryModel.new_empty(self.db))
        self.entry_type = self.props.entry_type
        self.plugin = plugin
        self.chat_id = chat_id
        self.chat_title = chat_title
        self.loader = None
        self.state_column = StateColumn(self) # noqa
        self.loaded_entries = []
        self.activate()

        app = self.shell.props.application
        self.set_property("playlist-menu", app.get_shared_menu("playlist-page-menu"))

    def activate(self):
        self.entry_updated_id = self.db.connect('entry-changed', self.on_entry_changed)
        self.props.entry_type.activate()

    def deactivate(self):
        self.db.disconnect(self.entry_updated_id)
        self.props.entry_type.deactivate()

    def on_entry_changed(self, db, entry, changes):
        if self.entry_type != entry.get_entry_type():
            return
        for change in changes:
            if change.prop == RB.RhythmDBPropType.PLAY_COUNT:
                play_count = entry.get_ulong(RB.RhythmDBPropType.PLAY_COUNT)
                loc = entry.get_string(RB.RhythmDBPropType.LOCATION)
                chat_id, message_id = get_location_data(loc)
                audio = self.plugin.storage.get_audio(chat_id, message_id)
                audio.save({"play_count": play_count})

    def hide_thyself(self):
        self.deactivate()
        self.set_property('visibility', False)

    def show_thyself(self):
        self.activate()
        self.set_property('visibility', True)

    def do_deselected(self):
        self.bar.deactivate(self)
        self.state_column.deactivate()
        if self.loader is not None:
            self.loader.stop()

    def do_selected(self):
        self.plugin.source = self
        self.state_column.activate()
        self.get_entry_view().set_sorting_order("Location", Gtk.SortType.DESCENDING)
        self.bar = DownloadBar(self.plugin)
        self.bar.activate(self)

        if not self.initialised:
            self.initialised = True
            GLib.idle_add(self.add_entries)
            # self.add_entries()

        self.loader = PlaylistLoader(self.chat_id, self.add_entry)
        self.loader.start()

    def add_entries(self):
        self.plugin.storage.load_entries(self.chat_id, self.add_entry, self.plugin.settings['audio-visibility'])

    def add_entry(self, audio):
        if audio.id not in self.loaded_entries:
            self.loaded_entries.append(audio.id)
            location = to_location(self.plugin.api.hash, audio.created_at, self.chat_id, audio.message_id)
            entry = self.db.entry_lookup_by_location(location)
            if not entry:
                entry = RB.RhythmDBEntry.new(self.db, self.entry_type, location)
                audio.update_entry(entry, self.db)

    def do_copy(self):
        tg_entries = self.get_entry_view().get_selected_entries()
        if len(tg_entries) == 0:
            return None

        sort_audio = []
        albums = {}
        num_format = '%0' + str(len(str(len(tg_entries))) + 2) + 'i'
        key_format = '%s|%s|%s' % (num_format, num_format, num_format)

        for idx, tg_entry in enumerate(tg_entries):
            audio = self.plugin.storage.get_entry_audio(tg_entry)
            if audio.is_moved:
                album = f'{audio.artist}|{audio.album}|{audio.get_year()}'
                albums_keys = albums.keys()
                if album not in albums_keys:
                    albums[album] = len(albums_keys) + 1
                sort_key = key_format % (albums[album], audio.track_number, idx)
                sort_audio.append([sort_key, audio])

        if len(sort_audio) == 0:
            return None

        sort_audio.sort(key=lambda d: d[0])
        entry_type = self.db.entry_type_get_by_name("song")
        song_entries = []

        for data in sort_audio:
            audio = data[1]
            uri = file_uri(audio.local_path)
            entry = self.db.entry_lookup_by_location(uri)
            if not entry:
                entry = RB.RhythmDBEntry.new(self.db, entry_type, uri)
                audio.update_entry(entry, self.db, commit=False, state=False)
                self.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, f'Downloaded from {self.chat_title}')
                self.db.commit()
            song_entries.append(entry)
        return song_entries

    def do_can_delete(self):
        return True

    def do_can_copy(self):
        return False

    def do_can_paste(self):
        return False

    def do_can_pause(self):
        return True

    def do_can_add_to_queue(self):
        return True

    def do_can_move_to_trash(self):
        return False

    def browse_action(self):
        screen = self.props.shell.props.window.get_screen()
        entries = self.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        entry = entries[0]
        location = entry.get_string(RB.RhythmDBPropType.LOCATION)
        chat_id, message_id = get_location_data(location)
        audio = TgAudio({"chat_id": chat_id, "message_id": message_id})
        url = audio.get_link()
        Gtk.show_uri(screen, url, Gdk.CURRENT_TIME)

    def file_manager_action(self):
        entries = self.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        app_info = Gio.AppInfo.get_default_for_type('inode/directory', True)
        if not app_info:
            return
        for entry in entries:
            audio = self.plugin.storage.get_entry_audio(entry)
            if audio.is_file_exists():
                app_info.launch_uris([file_uri(audio.local_path)], None)
                return

    def download_action(self):
        entries = self.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        downloader = self.plugin.downloader
        downloader.setup()
        downloader.add_entries(entries)
        downloader.start()

    def hide_action(self):
        entries = self.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        commit = False
        for entry in entries:
            audio = self.plugin.storage.get_entry_audio(entry)
            if not audio.is_hidden:
                audio.save({"is_hidden": True})
                self.db.entry_set(entry, TG_RhythmDBPropType.STATE, audio.get_state())
                commit = True
        if commit:
            self.db.commit()

    def unhide_action(self):
        entries = self.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        commit = False
        for entry in entries:
            audio = self.plugin.storage.get_entry_audio(entry)
            if audio.is_hidden:
                audio.save({"is_hidden": False})
                self.db.entry_set(entry, TG_RhythmDBPropType.STATE, audio.get_state())
                commit = True
        if commit:
            self.db.commit()


GObject.type_register(TelegramSource)
