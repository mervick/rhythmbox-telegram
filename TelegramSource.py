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
from gi.repository import GObject, Gtk, Gdk, Gio, GLib
from TelegramEntry import to_location
from TelegramStorage import TgLoader

import gettext
gettext.install('rhythmbox', RB.locale_dir())


class TelegramSource(RB.BrowserSource):
    def __init__(self):
        RB.BrowserSource.__init__(self)
        self.app = Gio.Application.get_default()
        self.initialised = False
        self.shell = None
        self.db = None
        self.player = None
        self.entry_type = None
        self.api = None
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

        self.loader = TgLoader(self.chat_id, self.add_entry)
        self.loader.start()

    def add_entries(self):
        all_audio = self.storage.get_chat_audio(self.chat_id)
        for audio in all_audio:
            self.add_entry(audio)

    def add_entry(self, track, pref=''):
        location = '%s%s' % (to_location(self.api.hash, track.date, self.chat_id, track.message_id), pref)
        entry = self.db.entry_lookup_by_location(location)

        #  * RBEntryViewColumn:
        #  * @RB_ENTRY_VIEW_COL_TRACK_NUMBER: the track number column
        #  * @RB_ENTRY_VIEW_COL_TITLE: the title column
        #  * @RB_ENTRY_VIEW_COL_ARTIST: the artist column
        #  * @RB_ENTRY_VIEW_COL_COMPOSER: the composer column
        #  * @RB_ENTRY_VIEW_COL_ALBUM: the album column
        #  * @RB_ENTRY_VIEW_COL_GENRE: the genre column
        #  * @RB_ENTRY_VIEW_COL_DURATION: the duration column
        #  * @RB_ENTRY_VIEW_COL_QUALITY: the quality (bitrate) column
        #  * @RB_ENTRY_VIEW_COL_RATING: the rating column
        #  * @RB_ENTRY_VIEW_COL_PLAY_COUNT: the play count column
        #  * @RB_ENTRY_VIEW_COL_YEAR: the year (release date) column
        #  * @RB_ENTRY_VIEW_COL_LAST_PLAYED: the last played time column
        #  * @RB_ENTRY_VIEW_COL_FIRST_SEEN: the first seen (imported) column
        #  * @RB_ENTRY_VIEW_COL_LAST_SEEN: the last seen column
        #  * @RB_ENTRY_VIEW_COL_LOCATION: the location column
        #  * @RB_ENTRY_VIEW_COL_BPM: the BPM column
        #  * @RB_ENTRY_VIEW_COL_COMMENT: the comment column

        if not entry:
            entry = RB.RhythmDBEntry.new(self.db, self.entry_type, location)
            self.db.entry_set(entry, RB.RhythmDBPropType.TITLE, track.title)
            self.db.entry_set(entry, RB.RhythmDBPropType.ARTIST, track.artist)
#             self.db.entry_set(entry, RB.RhythmDBPropType.ALBUM, track.artist)
            self.db.entry_set(entry, RB.RhythmDBPropType.DURATION, track.duration)
#             self.db.entry_set(entry, RB.RhythmDBPropType.RATING, 0)

#             if item['artwork_url'] is not None:
#               db.entry_set(entry, RB.RhythmDBPropType.MB_ALBUMID, item['artwork_url'])

#             dt = datetime.strptime(item['created_at'], '%Y/%m/%d %H:%M:%S %z')
#             db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(dt.timestamp()))

            self.db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(track.date))
            dt = GLib.DateTime.new_from_unix_local(int(track.date))
            date = GLib.Date.new_dmy(dt.get_day_of_month(), GLib.DateMonth(dt.get_month()), dt.get_year())

            self.db.entry_set(entry, RB.RhythmDBPropType.DATE, date.get_julian())
            self.db.commit()

    def playing_entry_changed_cb(self, player, entry):
        '''
        playing_entry_changed_cb changes the album artwork on every
        track change.
        '''
        if not entry:
            return
        if entry.get_entry_type() != self.props.entry_type:
            return

        au = entry.get_string(RB.RhythmDBPropType.MB_ALBUMID)
        if au:
            key = RB.ExtDBKey.create_storage(
                "title", entry.get_string(RB.RhythmDBPropType.TITLE))
            key.add_field("artist", entry.get_string(
                RB.RhythmDBPropType.ARTIST))
            key.add_field("album", entry.get_string(
                RB.RhythmDBPropType.ALBUM))
            self.art_store.store_uri(key, RB.ExtDBSourceType.EMBEDDED, au)

    def do_can_delete(self):
        return True

    def do_can_copy(self):
        return False

    def do_can_pause(self):
        return True

    def do_can_add_to_queue(self):
        return True


GObject.type_register(TelegramSource)
