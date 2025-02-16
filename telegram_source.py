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

import rb
from gi.repository import RB
from gi.repository import GObject, Gtk, Gio, Gdk, GLib
from common import to_location, get_location_data, SingletonMeta, get_first_artist, pretty_file_size
from common import file_uri, set_entry_state
from columns import StateColumn, SizeColumn, FormatColumn, TopPicksColumn
from loader import PlaylistLoader
from storage import Audio, VISIBILITY_ALL, VISIBILITY_VISIBLE
from account import KEY_RATING_COLUMN, KEY_DATE_ADDED_COLUMN, KEY_FILE_SIZE_COLUMN, KEY_AUDIO_FORMAT_COLUMN, KEY_TOP_PICKS_COLUMN

import gettext
gettext.install('rhythmbox', RB.locale_dir())


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
            status_box: Gtk.Box = builder.get_object('status_box')
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


class RefreshBtn:
    activated = False

    def __init__(self, source):
        self.source = source

    def activate(self):
        if self.activated:
            return

        entry_view = self.source.get_entry_view()
        paned = entry_view.get_parent()
        grid = paned.get_parent()
        toolbar = None

        for child in grid.get_children():
            if 'RB.SourceToolbar' in '%s' % type(child):
                toolbar = child
                break

        if toolbar:
            toolbar.set_column_homogeneous(False)

            button = Gtk.Button(label=_("Refresh"))
            button.get_style_context().add_class("flat")
            button.props.visible = True

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            box.props.visible = True
            toolbar.attach(box, 3, 0, 1, 1)

            box.pack_start(button, False, False, 0)

            spinner = Gtk.Spinner()
            spinner.props.visible = False
            # spinner.start()
            label = Gtk.Label(label="  %s" % _("Loading..."))
            label.props.visible = False

            box.pack_start(spinner, False, False, 0)
            box.pack_start(label, False, False, 0)

            self.button = button
            self.spinner = spinner
            self.label = label

            self.source.connect("playlist-fetch-started", self.fetch_started_cb)
            self.source.connect("playlist-fetch-end", self.fetch_end_cb)

            self.activated = True
            button.connect("clicked", self.clicked_cb)

    def clicked_cb(self, *obj):
        if self.source.loader:
            self.source.loader.fetch()

    def fetch_started_cb(self, *obj):
        self.button.props.visible = False
        self.spinner.props.visible = True
        self.label.props.visible = True
        self.spinner.start()

    def fetch_end_cb(self, *obj):
        self.spinner.stop()
        self.button.props.visible = True
        self.spinner.props.visible = False
        self.label.props.visible = False


class TelegramSource(RB.BrowserSource):
    __gsignals__ = {
        'playlist_fetch_started': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'playlist_fetch_end': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __str__(self) -> str:
        return f'TelegramSource <{self.chat_id}>'

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
        self.refresh_btn = RefreshBtn(self)
        self.bar = None
        self.bar_ui = None
        self.has_reached_end = False
        self.entry_updated_id = None
        self.loaded_entries = []
        self.custom_model = {}
        self.state_column = None

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
        entry_view = self.get_entry_view() # noqa

        if self.plugin.account.settings[KEY_RATING_COLUMN]:
            entry_view.append_column(rb.RB.EntryViewColumn.RATING, True)
        if self.plugin.account.settings[KEY_FILE_SIZE_COLUMN]:
            SizeColumn(self)
        if self.plugin.account.settings[KEY_AUDIO_FORMAT_COLUMN]:
            FormatColumn(self)
        if self.plugin.account.settings[KEY_DATE_ADDED_COLUMN]:
            entry_view.append_column(rb.RB.EntryViewColumn.FIRST_SEEN, True)
        if self.plugin.account.settings[KEY_TOP_PICKS_COLUMN]:
            TopPicksColumn(self)

        self.state_column = StateColumn(self)

    def activate(self):
        if self.activated:
            return
        if self.visibility in (VISIBILITY_VISIBLE, VISIBILITY_ALL):
            self.refresh_btn.activate()
        self.activated = True
        self.entry_updated_id = self.db.connect('entry-changed', self.on_entry_changed)
        self.props.entry_type.activate()

    def deactivate(self):
        if self.activated:
            self.activated = False
            if self.loader is not None:
                self.loader.stop()
            self.loader = None
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
        self.set_property('visibility', False)

    def show_thyself(self):
        self.activate()
        self.set_property('visibility', True)

    def do_deselected(self):
        self.bar.deactivate(self)
        self.state_column.deactivate()
        if self.loader is not None:
            self.loader.stop()
            self.loader = None
        self.plugin.remove_plugin_menu()

    def do_selected(self):
        self.plugin.source = self
        self.state_column.activate()
        self.get_entry_view().set_sorting_order("FirstSeen", Gtk.SortType.DESCENDING)
        self.bar = DownloadBar(self.plugin)
        self.bar.activate(self)

        if not self.initialised:
            self.initialised = True
            GLib.idle_add(self.add_entries)

        self.plugin.add_plugin_menu()

        if self.visibility in (VISIBILITY_VISIBLE, VISIBILITY_ALL):
            if self.loader is not None:
                self.loader.stop()
            self.loader = PlaylistLoader(self, self.chat_id, self.add_entry)
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
        audio = Audio({"chat_id": chat_id, "message_id": message_id})
        link = audio.get_link()
        direct_link = self.plugin.api.get_message_direct_link(link)
        if direct_link:
            try:
                Gtk.show_uri(screen, direct_link, Gdk.CURRENT_TIME)
            except GLib.Error:
                Gtk.show_uri(screen, link, Gdk.CURRENT_TIME)
        elif link:
            Gtk.show_uri(screen, link, Gdk.CURRENT_TIME)

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
