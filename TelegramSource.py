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
from gi.repository import GObject, Gtk, Gio, Gdk, GLib
from common import to_location, get_location_data, empty_cb, SingletonMeta, get_first_artist, get_entry_location
from common import get_location_audio_id, pretty_file_size
from common import file_uri, get_entry_state, set_entry_state
from TelegramLoader import PlaylistLoader
from TelegramStorage import TgAudio
from TelegramAccount import KEY_RATING_COLUMN, KEY_DATE_ADDED_COLUMN, KEY_FILE_SIZE_COLUMN, KEY_AUDIO_FORMAT_COLUMN

import gettext
gettext.install('rhythmbox', RB.locale_dir())


class TgFormatColumn:
    def __init__(self, source):
        self.source = source

        entry_view = source.get_entry_view()

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


class TgSizeColumn:
    def __init__(self, source):
        self.source = source

        entry_view = source.get_entry_view()

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


state_icons = {
    TgAudio.STATE_DEFAULT : 'tg-state-download-symbolic',
    TgAudio.STATE_ERROR : 'tg-state-error',
    TgAudio.STATE_IN_LIBRARY : 'tg-state-library-symbolic',
    TgAudio.STATE_HIDDEN : 'tg-state-visibility-off-symbolic',
    TgAudio.STATE_DOWNLOADED : None,
}


class TgStateColumn:
    _icon_cache = {}

    def __init__(self, source):
        self._pulse = 0
        self._models = {}
        self.timeout_id = None

        column = Gtk.TreeViewColumn()
        pixbuf_renderer = Gtk.CellRendererPixbuf()
        spinner_renderer = Gtk.CellRendererSpinner()

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

    def model_data_func(self, column, cell, model, iter, cell_type): # noqa
        entry = model.get_value(iter, 0)
        idx = model.get_value(iter, 1)
        state = get_entry_state(entry)
        is_spinner = cell_type == 'spinner'

        if state == TgAudio.STATE_LOADING:
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
                if state in TgStateColumn._icon_cache:
                    gicon = TgStateColumn._icon_cache[state]
                else:
                    icon_name = state_icons[state] if state in state_icons else state_icons[TgAudio.STATE_DEFAULT]
                    gicon = Gio.ThemedIcon.new(icon_name) if icon_name is not None else None
                    TgStateColumn._icon_cache[state] = gicon
                cell.props.gicon = gicon


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
        self.activated = False
        self.shell = None
        self.db = None
        self.entry_type = None
        self.loader = None
        self.plugin = None
        self.chat_id = None
        self.chat_title = None
        self.visibility = None
        self.bar = None
        self.bar_ui = None
        self.entry_updated_id = None
        self.loaded_entries = []
        self.custom_model = {}

    def setup(self, plugin, chat_id, chat_title, visibility):
        self.initialised = False
        shell = self.props.shell
        self.shell = shell
        self.db = shell.props.db
        self.set_property("query-model", RB.RhythmDBQueryModel.new_empty(self.db))
        self.entry_type = self.props.entry_type
        self.plugin = plugin
        self.chat_id = chat_id
        self.chat_title = chat_title
        self.visibility = visibility
        self.loader = None
        self.init_columns()
        self.activate()
        # add shared menu (add to playlist)
        self.set_property("playlist-menu", self.shell.props.application.get_shared_menu("playlist-page-menu"))

    def init_columns(self):
        if self.plugin.account.settings[KEY_RATING_COLUMN]:
            self.get_entry_view().append_column(rb.RB.EntryViewColumn.RATING, True)
        if self.plugin.account.settings[KEY_FILE_SIZE_COLUMN]:
            TgSizeColumn(self)
        if self.plugin.account.settings[KEY_AUDIO_FORMAT_COLUMN]:
            TgFormatColumn(self)
        if self.plugin.account.settings[KEY_DATE_ADDED_COLUMN]:
            self.get_entry_view().append_column(rb.RB.EntryViewColumn.FIRST_SEEN, True)
        self.state_column = TgStateColumn(self) # noqa

    def activate(self):
        self.activated = True
        self.entry_updated_id = self.db.connect('entry-changed', self.on_entry_changed)
        self.props.entry_type.activate()

    def deactivate(self):
        if self.activated:
            self.activated = False
            self.db.disconnect(self.entry_updated_id)
            self.props.entry_type.deactivate()

    def on_entry_changed(self, db, entry, changes):
        if self.entry_type != entry.get_entry_type():
            return

        for change in changes:
            if change.prop == RB.RhythmDBPropType.PLAY_COUNT:
                play_count = entry.get_ulong(RB.RhythmDBPropType.PLAY_COUNT)
                audio = self.plugin.storage.get_entry_audio(entry)
                audio.save({"play_count": play_count})
            elif change.prop == RB.RhythmDBPropType.RATING:
                rating = entry.get_double(RB.RhythmDBPropType.RATING)
                audio = self.plugin.storage.get_entry_audio(entry)
                audio.save({"rating": round(rating)})

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
        self.plugin.remove_plugin_menu()

    def do_selected(self):
        self.plugin.source = self
        self.state_column.activate()
        self.get_entry_view().set_sorting_order("Date Added", Gtk.SortType.DESCENDING)
        self.bar = DownloadBar(self.plugin)
        self.bar.activate(self)

        if not self.initialised:
            self.initialised = True
            GLib.idle_add(self.add_entries)

        self.plugin.add_plugin_menu()

        if self.visibility in (1, None):
            self.loader = PlaylistLoader(self.chat_id, self.add_entry)
            self.loader.start()

    def add_entries(self):
        self.plugin.storage.load_entries(self.chat_id, self.add_entry, self.visibility)

    def add_entry(self, audio):
        if audio.id not in self.loaded_entries:
            self.loaded_entries.append(audio.id)
            location = to_location(self.plugin.api.hash, self.chat_id, audio.message_id, audio.id)
            self.custom_model["%s" % audio.id] = [pretty_file_size(audio.size, 1), audio.get_file_ext()]
            entry = self.db.entry_lookup_by_location(location)
            if not entry:
                entry = RB.RhythmDBEntry.new(self.db, self.entry_type, location)
                audio.update_entry(entry, self.db)

    def get_custom_model(self, idx):
        return self.custom_model[idx]

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
                album = f'{get_first_artist(audio.artist)}|{audio.album}|{audio.get_year()}'
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
                # self.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, f'Downloaded from {self.chat_title}')
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
        for entry in entries:
            audio = self.plugin.storage.get_entry_audio(entry)
            if not audio.is_hidden:
                audio.save({"is_hidden": True})
            set_entry_state(self.db, entry, audio.get_state())
        self.db.commit()

    def unhide_action(self):
        entries = self.get_entry_view().get_selected_entries()
        if len(entries) == 0:
            return
        for entry in entries:
            audio = self.plugin.storage.get_entry_audio(entry)
            if audio.is_hidden:
                audio.save({"is_hidden": False})
            set_entry_state(self.db, entry, audio.get_state())
        self.db.commit()


GObject.type_register(TelegramSource)
