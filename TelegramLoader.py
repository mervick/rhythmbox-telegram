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
from gi.repository import GObject, GLib
from TelegramStorage import TelegramStorage, TgPlaylist


filename_illegal = '<>:"/\\|?*'

def clear_filename(filename):
    for char in filename_illegal:
        filename = filename.replace(char, '')
    return filename


class AudioDownloader:
    def __str__(self) -> str:
        return f'AudioDownloader <{self.ids}>'

    def __init__(self, audio_ids):
        self.api = TelegramStorage.loaded().api
        self.ids = audio_ids
        self._terminated = False
        self._loaded = False

    def start(self):
        # get download settings
        pass


class PlaylistLoader:
    def __str__(self) -> str:
        return f'PlaylistLoader <{self.chat_id}>'

    def __init__(self, chat_id, add_entry):
        self.api = TelegramStorage.loaded().api
        self.playlist = TgPlaylist.read(chat_id)
        self.chat_id = chat_id
        self.add_entry = add_entry
        self.segment = [0,0]
        self.offset_msg_id = 0
        self.page = 0
        self._end_of_page = False
        self._terminated = False
        self._loaded = False

    def start(self):
        print(f'PlaylistLoader.start')
        self.playlist = TgPlaylist.read(self.chat_id )
        print(self.playlist.segments)
        self.playlist.segments.insert(0, [0,0])
        self.segment = self.playlist.segment(1)
        blob = {}
        self.load(blob, limit=1)
        return self

    def add_audio(self, audio):
        # update audio, add entries to playlist
        if audio.message_id == self.segment[0]:
            print('end of page')
            self._end_of_page = True
        if audio.message_id == self.segment[1]:
            print('end of page')
            self._end_of_page = True
        if not self._end_of_page:
            self.add_entry(audio)

    def next(self, blob, cmd):
        self.page = self.page + 1
        print('PlaylistLoader.next %s' % cmd)
        last_msg_id = blob.get('last_msg_id', 0)

        if last_msg_id == 0:
            print('tg.loader.BREAK')
            GLib.timeout_add(60 * 5000, self.start)
            return

        print("blob %s" % blob)

        if self.playlist.segments[0][0] == 0:
            self.playlist.segments[0][0] = last_msg_id
        self.playlist.segments[0][1] = last_msg_id
        offset_msg_id = last_msg_id

        if self._end_of_page:
            self.playlist.segments[0][1] = self.segment[1]
            offset_msg_id = self.segment[1]
            del self.playlist.segments[1]
            self.segment = self.playlist.segment(1)

        self._end_of_page = False

        if last_msg_id == self.offset_msg_id:
            print('BREAK INFINITY LOOP')
#             return

#         if cmd == 'DONE' or offset_msg_id == -1 or (last_msg_id == self.offset_msg_id and self._loaded):
        if cmd == 'DONE' or offset_msg_id == -1 or last_msg_id == self.offset_msg_id:
#             self.playlist.segments = [[ self.playlist.segments[0][0], -1]]
            self.playlist.segments = [[ self.playlist.segments[0][0], offset_msg_id]]
            self.playlist.save()
            self._loaded = True
            print('tg.loader.DONE')
            GLib.timeout_add(60 * 5000, self.start)
            return

        self.playlist.save()
        self.playlist.reload()
        self.segment = self.playlist.segment(1)

        self.offset_msg_id = offset_msg_id
        print('timeout_add')
        GLib.timeout_add(5000 if self.page > 10 else 1000, self.load, {"offset_msg_id": offset_msg_id})

    def stop(self):
        print(f'PlaylistLoader.stop')
        self._terminated = True

    def load(self, blob={}, limit=50):
        if not self._terminated:
            print(f'PlaylistLoader.load  {self.chat_id}')
            print(blob)
            self.api.load_messages_idle( self.chat_id, update=self.add_audio, done=self.next, blob={**blob}, limit=limit)

