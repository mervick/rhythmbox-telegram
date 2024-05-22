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
from gi.repository import GObject, Gtk, Gio, GLib
from TelegramEntry import to_location
from TelegramLoader import PlaylistLoader

import gettext
gettext.install('rhythmbox', RB.locale_dir())


def empty_cb(*a, **b):
    pass

state_dark_icons = {
    'DEFAULT' : '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/download-dark.svg',
    'STATE_ERROR' : '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/error.svg',
    'STATE_IN_LIBRARY' : '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/library-dark.svg',
    'STATE_DOWNLOADED' : '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/empty.svg',
}

state_light_icons = {
    'DEFAULT' : '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/download-light.svg',
    'STATE_ERROR' : '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/error.svg',
    'STATE_IN_LIBRARY' : '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/library-light.svg',
    'STATE_DOWNLOADED' : '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/empty.svg',
}


class StateColumn:
    def __init__(self, source):
        column_title = Gtk.TreeViewColumn()  # "Title",Gtk.CellRendererText(),text=0)
        renderer = Gtk.CellRendererPixbuf()
        column_title.set_title(" ")
        column_title.set_cell_data_func(renderer, self.model_data_func, "image")

        # image_widget = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic", Gtk.IconSize.MENU)
        # column_title.set_widget(image_widget)
        # Gtk.Widget.show_all(image_widget)

        column_title.set_expand(False)
        column_title.set_resizable(False)

        column_title.pack_start(renderer, expand=False)
        # column_title.pack_start(renderer, expand=True)
        column_title.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column_title.set_fixed_width(36)

        entry_view = source.get_entry_view()
        entry_view.append_column_custom(column_title, ' ', "tg-state", empty_cb, None, None)
        visible_columns = entry_view.get_property("visible-columns")
        visible_columns.append('tg-state')
        entry_view.set_property("visible-columns", visible_columns)
        # entry_view.set_property("has-tooltip", True)

    def model_data_func(self, column, cell, model, iter, infostr):
        entry = model.get_value(iter, 0)
        state = entry.get_string(RB.RhythmDBPropType.COMMENT)
        # obj = model.get_value(iter,1)
        filepath = state_dark_icons[state] if state in state_dark_icons else state_dark_icons['DEFAULT']
        icon = GdkPixbuf.Pixbuf.new_from_file(filepath)
        cell.set_property("pixbuf", icon)


class TelegramSource(RB.BrowserSource):
    def __init__(self):
        self.is_activated = False
        RB.BrowserSource.__init__(self)
        self.app = Gio.Application.get_default()
        self.initialised = False
        self.shell = None
        self.db = None
        self.player = None
        self.entry_type = None
        self.api = None
        self.loader = None
        self.storage = None
        self.chat_id = None
        self.last_track = None
        self._is_downloading = 0

    def setup(self, api, chat_id):
        self.initialised = False
        shell = self.props.shell
        self.shell = shell
        self.db = shell.props.db
        self.player = shell.props.shell_player
        self.entry_type = self.props.entry_type
        self.api = api
        self.storage = api.storage
        self.chat_id = chat_id
        self.last_track = None
        self.loader = None
        StateColumn(self)

    def do_deselected(self):
        print('do_deselected %s' % self.chat_id)
        if self.loader is not None:
            self.loader.stop()

    def do_selected(self):
        # GTK_SORT_ASCENDING = 0, GTK_SORT_DESCENDING = 1
        self.get_entry_view().set_sorting_order("Location", 1)
        print('do_selected %s' % self.chat_id)

        if not self.initialised:
            self.initialised = True
            self.add_entries()

        self.loader = PlaylistLoader(self.chat_id, self.add_entry)
        self.loader.start()

    def add_entries(self):
        all_audio = self.storage.get_chat_audio(self.chat_id)
        for audio in all_audio:
            self.add_entry(audio)

    def add_entry(self, track, pref=''):
        location = '%s%s' % (to_location(self.api.hash, track.created_at, self.chat_id, track.message_id), pref)
        entry = self.db.entry_lookup_by_location(location)
        if not entry:
            entry = RB.RhythmDBEntry.new(self.db, self.entry_type, location)
            self.db.entry_set(entry, RB.RhythmDBPropType.TITLE, track.title)
            self.db.entry_set(entry, RB.RhythmDBPropType.ARTIST, track.artist)
            self.db.entry_set(entry, RB.RhythmDBPropType.DURATION, track.duration)
            self.db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(track.created_at))
            self.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, track.get_state())
            # dt = GLib.DateTime.new_from_unix_local(int(track.date))
            # date = GLib.Date.new_dmy(dt.get_day_of_month(), GLib.DateMonth(dt.get_month()), dt.get_year())
            self.db.entry_set(entry, RB.RhythmDBPropType.DATE, int(track.date))
            self.db.commit()

    # def playing_entry_changed_cb(self, player, entry):
    #     '''
    #     playing_entry_changed_cb changes the album artwork on every
    #     track change.
    #     '''
    #     if not entry:
    #         return
    #     if entry.get_entry_type() != self.props.entry_type:
    #         return
    #
    #     au = entry.get_string(RB.RhythmDBPropType.MB_ALBUMID)
    #     if au:
    #         key = RB.ExtDBKey.create_storage(
    #             "title", entry.get_string(RB.RhythmDBPropType.TITLE))
    #         key.add_field("artist", entry.get_string(
    #             RB.RhythmDBPropType.ARTIST))
    #         key.add_field("album", entry.get_string(
    #             RB.RhythmDBPropType.ALBUM))
    #         self.art_store.store_uri(key, RB.ExtDBSourceType.EMBEDDED, au)

    def do_can_delete(self):
        return True

    def do_can_copy(self):
        return False

    def do_can_pause(self):
        return True

    def do_can_add_to_queue(self):
        return True

    def browse_action(self):
        pass

    def download_action(self):
        pass

    def hide_action(self):
        pass


GObject.type_register(TelegramSource)
