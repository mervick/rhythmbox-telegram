# rhythmbox-telegram
# Copyright (C) 2023 Andrey Izman <izmanw@gmail.com>
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
        self.chat_id = chat_id
        self.last_track = None

    def do_selected(self):
        print('================do_selected=====================')
        print('do_selected %s' % self.chat_id)
        if not self.initialised:
            self.initialised = True
            self.add_entries()

    def add_entries(self):
        all_audio = self.api.get_chat_audio(self.chat_id)
        print('================all_audio=====================')
        print(all_audio)
        print('================all_audio=====================')
        for audio in all_audio:
            self.add_entry(audio)
            print('======= add_entry %s' % audio.audio_id)
            # if self._is_downloading < 3:
            #     self._is_downloading = self._is_downloading + 1
            #     # self.api.download_file(audio.audio_id)
            #
            #     r = self.api.tg.get_message(audio.chat_id, audio.message_id)
            #     r.wait()
            #     print('================ get_message %s====================' % audio.message_id)
            #     print(r.update)
            #     # @TODO need to update audio.id and download audio by new ID
        # self.api.load_messages_idle(self.chat_id, self.add_entry)

    def add_entry(self, track):
        location = to_location(self.api.phone, self.chat_id, track.message_id)
        print('location %s' % location)
        entry = self.db.entry_lookup_by_location(location)

        if not entry:
            entry = RB.RhythmDBEntry.new(self.db, self.entry_type, location)
            self.db.entry_set(entry, RB.RhythmDBPropType.TITLE, track.title)
            self.db.entry_set(entry, RB.RhythmDBPropType.ARTIST, track.artist)
            self.db.entry_set(entry, RB.RhythmDBPropType.DURATION, track.duration)
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
        return False

    def do_can_copy(self):
        return False

    def do_can_pause(self):
        return True

    def do_can_add_to_queue(self):
        return True


GObject.type_register(TelegramSource)
