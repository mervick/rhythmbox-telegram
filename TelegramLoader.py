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

import os
import shutil
from gi.repository import RB
from gi.repository import GLib
from common import get_location_data, filepath_parse_pattern
from TelegramStorage import TgPlaylist
from TelegramApi import TelegramApi


class AudioDownloader:
    def __init__(self, plugin, entries):
        self.plugin = plugin
        self.entries = entries
        self.library_location = plugin.account.get_library_path()
        self.folder_hierarchy = plugin.settings['folder-hierarchy']
        self.conflict_resolve = plugin.settings['conflict-resolve']
        self.filename_template = plugin.settings['filename-template']
        self._terminated = False
        self._loaded = False
        self._idx = 0

    def start(self):
        entries = []
        for entry in self.entries:
            state = entry.get_string(RB.RhythmDBPropType.COMMENT)
            if state != 'STATE_IN_LIBRARY':
                entries.append(entry)
                self.plugin.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, 'STATE_LOADING')
                self.plugin.db.commit()
        self.entries = entries
        if len(entries) > 0:
            self._load()
        else:
            self.stop()
        return self

    def _move(self, audio):
        entry = self.entries[self._idx]
        audio.update_tags()
        tags = {
            'title': audio.title,
            'artist': audio.artist,
            'album': audio.album,
            'track_number': audio.track_number,
            'date': audio.date,
            'duration': audio.duration,
            'genre': audio.genre,
            'year': audio.get_year(),
        }
        file_ext = audio.get_file_ext()
        filename = filepath_parse_pattern(
            "%s/%s%s" % (self.folder_hierarchy, self.filename_template,
                         f'.{file_ext}' if len(file_ext) else ''), tags)
        filename = "%s/%s" % (self.library_location, filename)
        file_dir = os.path.dirname(filename)
        os.makedirs(file_dir, exist_ok=True)
        shutil.move(audio.local_path, filename)
        audio.save({"local_path": filename, "is_moved": True})

        self.plugin.db.entry_set(entry, RB.RhythmDBPropType.TRACK_NUMBER, audio.track_number)
        self.plugin.db.entry_set(entry, RB.RhythmDBPropType.TITLE, audio.title)
        self.plugin.db.entry_set(entry, RB.RhythmDBPropType.ARTIST, audio.artist)
        self.plugin.db.entry_set(entry, RB.RhythmDBPropType.ALBUM, audio.album)
        self.plugin.db.entry_set(entry, RB.RhythmDBPropType.DURATION, audio.duration)
        self.plugin.db.entry_set(entry, RB.RhythmDBPropType.DATE, int(audio.date))
        self.plugin.db.entry_set(entry, RB.RhythmDBPropType.GENRE, audio.genre)
        self.plugin.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, audio.get_state())
        self.plugin.db.commit()

        self._next()

    def _next(self):
        self._idx = self._idx + 1
        if self._idx >= len(self.entries):
            self._terminated = True
            return
        GLib.timeout_add(5, self._load)

    def stop(self):
        self._terminated = True

    def _load(self):
        if not self._terminated:
            entry = self.entries[self._idx]
            location = entry.get_string(RB.RhythmDBPropType.LOCATION)
            chat_id, message_id = get_location_data(location)
            audio = self.plugin.storage.get_audio(chat_id, message_id)
            if not audio:
                self._next()
                return
            if audio.is_moved:
                self.plugin.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, audio.get_state())
                self.plugin.db.commit()
                self._next()
                return
            file_path = audio.get_path(wait=False, done=self._move)
            if file_path:
                self._move(audio)


class PlaylistLoader:
    def __str__(self) -> str:
        return f'PlaylistLoader <{self.chat_id}>'

    def __init__(self, chat_id, add_entry):
        self.api = TelegramApi.loaded()
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
        self.playlist = TgPlaylist.read(self.chat_id )
        self.playlist.segments.insert(0, [0, 0])
        self.segment = self.playlist.segment(1)
        blob = {}
        self._load(blob, limit=1)
        return self

    def _add_audio(self, audio):
        # update audio, add entries to playlist
        if audio.message_id == self.segment[0]:
            self._end_of_page = True
        if audio.message_id == self.segment[1]:
            self._end_of_page = True
        if not self._end_of_page:
            self.add_entry(audio)

    def _next(self, blob, cmd):
        self.page = self.page + 1
        last_msg_id = blob.get('last_msg_id', 0)

        if last_msg_id == 0:
            GLib.timeout_add(60 * 5000, self.start)
            return

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

#         if cmd == 'DONE' or offset_msg_id == -1 or (last_msg_id == self.offset_msg_id and self._loaded):
        if cmd == 'DONE' or offset_msg_id == -1 or last_msg_id == self.offset_msg_id:
#             self.playlist.segments = [[ self.playlist.segments[0][0], -1]]
            self.playlist.segments = [[ self.playlist.segments[0][0], offset_msg_id]]
            self.playlist.save()
            self._loaded = True
            GLib.timeout_add(60 * 5000, self.start)
            return

        self.playlist.save()
        self.playlist.reload()
        self.segment = self.playlist.segment(1)

        self.offset_msg_id = offset_msg_id
        GLib.timeout_add(5000 if self.page > 10 else 1000, self._load, {"offset_msg_id": offset_msg_id})

    def stop(self):
        self._terminated = True

    def _load(self, blob={}, limit=50):
        if not self._terminated:
            self.api.load_messages_idle( self.chat_id, update=self._add_audio, done=self._next, blob={**blob}, limit=limit)
