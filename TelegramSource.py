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

#         self.songs = RB.EntryView(db=shell.props.db,
#                 shell_player=shell.props.shell_player,
#                 is_drag_source=False,
#                 is_drag_dest=False)
#         self.songs.append_column(RB.EntryViewColumn.TITLE, True)
#         self.songs.append_column(RB.EntryViewColumn.ARTIST, True)
#         self.songs.append_column(RB.EntryViewColumn.DURATION, True)
#         self.songs.append_column(RB.EntryViewColumn.YEAR, True)
#         self.songs.append_column(RB.EntryViewColumn.GENRE, False)
#         self.songs.append_column(RB.EntryViewColumn.BPM, False)
#         self.songs.append_column(RB.EntryViewColumn.FIRST_SEEN, True)
#         self.songs.append_column(RB.EntryViewColumn.RATING, True)
#         self.songs.set_model(self.props.query_model)

#         self.songs.connect("notify::sort-order", self.sort_order_changed_cb)
#         self.songs.connect("selection-changed", self.songs_selection_changed_cb)
#         paned = builder.get_object("paned")
#         paned.pack2(self.songs)

#         print('================get_sorting_order=====================')
#         print(self.songs.get_sorting_order())

#     def do_get_entry_view(self):
#       return self.songs

    def do_deselected(self):
        print('do_deselected %s' % self.chat_id)
        if self.loader is not None:
            self.loader.stop()

    def do_selected(self):
        #TypeError: RB.RhythmDBQueryModel.set_sort_order() takes exactly 4 arguments (3 given)
        # ascending
#         rb_entry_view_set_sorting_order (source->priv->entry_view, "Track", GTK_SORT_ASCENDING);

        # GTK_SORT_ASCENDING = 0, GTK_SORT_DESCENDING = 1
        self.get_entry_view().set_sorting_order("Location", 1)
#         self.get_entry_view().set_sorting_order("Date Added", 1)
#         self.get_entry_view().set_sorting_order(RB.RhythmDBPropType.FIRST_SEEN, 1)
#         self.get_entry_view().set_sorting_order('FIRST SEEN', 1)
#         self.get_entry_view().set_sorting_order("Location", 0)

#         self.props.query_model.set_sort_order('location', 'descending')
#         print('================do_selected=====================')
        print('do_selected %s' % self.chat_id)
        if not self.initialised:
            self.initialised = True
            self.add_entries()
#             self.shell
#             rb_entry_view_set_sorting_type ()

        self.loader = TgLoader(self.chat_id, self.add_entry)
        self.loader.start()

#         def _update(d):
# #             print('update')
# #             print(d)
#             pass
#
#         def _next2(d, cmd):
#             print('NEXT2')
# #             print(d)
#             print(d['result'].update['total_count'])
#             print(d['result'].update)
#             print(d.get('last_msg_id'))
#             print(cmd)
#
#         def _next(d, cmd):
#             print('NEXT')
# #             print(d)
#             print(d['result'].update['total_count'])
#             print(d['result'].update)
#             print(d.get('last_msg_id'))
#             print(cmd)
#             self.api.load_messages_idle(self.chat_id, update=_update, done=_next2,
#                 blob={"offset_msg_id": d.get('last_msg_id')}, limit=50, offset=0)
#
#         self.api.load_messages_idle(self.chat_id, update=_update, done=_next,
#             blob={"offset_msg_id": 0}, limit=1, offset=0)


    def add_entries(self):
        print('================add_entries=====================')
        all_audio = self.storage.get_chat_audio(self.chat_id)
        print('================all_audio=====================')
        print(len(all_audio))
        # print('================all_audio=====================')
        i = 0
        # for i in range(0, 550):
        for audio in all_audio:
            self.add_entry(audio, pref='' if i == 0 else '/%s' % i)
            # print('======= add_entry %s' % audio.audio_id)
            # if self._is_downloading < 3:
            #     self._is_downloading = self._is_downloading + 1
            #     # self.api.download_file(audio.audio_id)
            #
            #     r = self.api.tg.get_message(audio.chat_id, audio.message_id)
            #     r.wait()
            #     print('================ get_message %s====================' % audio.message_id)
            #     print(r.update)
            #     # @TODO need to update audio.id and download audio by new ID

#         class Ptr:
#             value = 0
#
#             def inc(self):
#                 self.value += 1
#
#         idx = Ptr()
#
#         def _load(blob={}):
#             idx.inc()
#             if idx.value > 10:
#                 return
#
#             print('===============================================')
#             print(f'LOADING MESSAGES  ${idx.value}')
#             print(blob)
#             self.api.load_messages_idle(self.chat_id, self.add_entry, done=_load, blob={"offset_msg_id": blob.get("offset_msg_id")})

        # _load()

#     def _load_audio(self):
#         pass

    def add_entry(self, track, pref=''):
        location = '%s%s' % (to_location(self.api.hash, track.date, self.chat_id, track.message_id), pref)
        # print('location %s' % location)
        entry = self.db.entry_lookup_by_location(location)
#         print('DATE')
#         print('%s' % track.date)

#         if entry:
#           self.db.entry_delete(entry)
#           entry = None

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

#             print('DATE')
#             print('%s' % track.date)
#             dt = datetime.strptime(item['created_at'], '%Y/%m/%d %H:%M:%S %z')
#             db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(dt.timestamp()))

            self.db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(track.date))
            dt = GLib.DateTime.new_from_unix_local(int(track.date))
            date = GLib.Date.new_dmy(dt.get_day_of_month(), GLib.DateMonth(dt.get_month()), dt.get_year())

#             print("%s:%s:%s)
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
