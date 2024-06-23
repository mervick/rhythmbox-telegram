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
from gi.repository import GLib, RB
from common import filepath_parse_pattern, SingletonMeta, get_entry_state, set_entry_state
from TelegramStorage import TgPlaylist, TgAudio
from TelegramApi import TelegramApi


class AudioLoader(metaclass=SingletonMeta):
    """
    AudioLoader is designed to sequentially download audio files into a temp directory.
    The most recently added records to the queue are loaded first.
    The downloading process is assigned the highest priority level.
    """
    def __init__(self, plugin):
        self.plugin = plugin
        self.entries = []
        self._running = False
        self._idx = 0

    def is_downloading(self, entry):
        if self._running:
            uri = entry.get_string(RB.RhythmDBPropType.LOCATION)
            for in_entry in self.entries:
                if in_entry:
                    in_uri = in_entry.get_string(RB.RhythmDBPropType.LOCATION)
                    if in_uri == uri:
                        return True
        return False

    def add_entry(self, entry):
        state = get_entry_state(entry)
        if state != TgAudio.STATE_IN_LIBRARY and state != TgAudio.STATE_LOADING:
            self.entries.append(entry)
            set_entry_state(self.plugin.db, entry, TgAudio.STATE_LOADING)
            self.plugin.db.commit()
        return self

    def start(self):
        if len(self.entries) > 0:
            if not self._running:
                self._running = True
                self._idx = len(self.entries) - 1
                self._load()
        else:
            self.stop()
        return self

    def stop(self):
        self._running = False
        self.entries = []

    def _process(self, audio):
        entry = self.entries[self._idx]
        audio.update_entry(entry)
        GLib.idle_add(entry.get_entry_type().emit, 'entry_downloaded', entry)
        self._next()

    def _next(self):
        del self.entries[self._idx]
        self._idx = len(self.entries) - 1
        if self._idx < 0:
            self.stop()
            return
        GLib.timeout_add(1000, self._load)

    def _load(self):
        if self._running:
            entry = self.entries[self._idx]
            audio = self.plugin.storage.get_entry_audio(entry)
            if not audio:
                self._next()
                return
            file_path = audio.get_path()
            if file_path:
                set_entry_state(self.plugin.db, entry, audio.get_state())
                self.plugin.db.commit()
                self._next()
            else:
                audio.download(success=self._process, fail=self._next)


class AudioDownloader(metaclass=SingletonMeta):
    """
    AudioDownloader is designed to sequentially download audio files into a Music library.
    The first entries added to the queue are downloaded first.
    The downloading process is assigned a medium priority level.
    """
    def __init__(self, plugin):
        self.plugin = plugin
        self.entries = []
        self._running = False
        self._idx = 0
        self._info = {}
        self.setup()

    def setup(self):
        self.library_location = self.plugin.account.get_library_path().rstrip('/') # noqa
        self.folder_hierarchy = self.plugin.settings['folder-hierarchy'] # noqa
        self.conflict_resolve = self.plugin.settings['conflict-resolve'] # noqa
        self.filename_template = self.plugin.settings['filename-template'] # noqa

    def add_entries(self, entries):
        for entry in entries:
            state = get_entry_state(entry)
            if state != TgAudio.STATE_IN_LIBRARY:
                self.entries.append(entry)
                set_entry_state(self.plugin.db, entry, TgAudio.STATE_LOADING)
                self.plugin.db.commit()

    def stop(self):
        self._running = False
        self.entries = []
        self._idx = 0
        self._update_progress()

    def start(self):
        if len(self.entries) > 0:
            if not self._running:
                self._info = {}
                self._running = True
                self._idx = 0
                self._load()
            else:
                self._update_progress()
        else:
            self.stop()
        return self

    def _update_progress(self, audio=None):
        filename = ''
        if audio is not None:
            if len(audio.title) and len(audio.artist):
                filename = '%s - %s.%s' % (audio.artist, audio.title, audio.get_file_ext())
            else:
                filename = audio.file_name
        total = len(self.entries)
        info = {
            "active": self._running,
            "index": self._idx + 1,
            "total": total,
            "filename": filename if len(filename) else self._info.get('filename', ''),
            "fraction": self._idx / total if total > 0 else 1.0,
        }
        self._info = info
        self.plugin.emit('update_download_info', info)

    def _move_file(self, src, dst):
        dst_dir = str(os.path.dirname(dst)).rstrip('/')
        os.makedirs(dst_dir, exist_ok=True)

        if self.conflict_resolve == 'skip':
            if os.path.exists(dst):
                print(f"File '{dst}' already exists. Skipping.")
                return dst
            else:
                shutil.move(src, dst)

        elif self.conflict_resolve == 'overwrite':
            print(f"File '{dst}' already exists. Overwriting.")
            shutil.move(src, dst)

        elif self.conflict_resolve == 'rename':
            dst_base = os.path.basename(dst)
            name, ext = os.path.splitext(dst_base)
            counter = 1
            new_dst = dst
            while os.path.exists(new_dst):
                new_dst = os.path.join(dst_dir, f"{name} ({counter}){ext}")
                counter += 1
            shutil.move(src, new_dst)
            return new_dst
        return dst

    def _process(self, audio):
        entry = self.entries[self._idx]
        tags = {
            'title': audio.title,
            'artist': audio.artist,
            'album_artist': audio.get_album_artist(),
            'album': audio.album,
            'track_number': audio.track_number,
            'date': audio.date,
            'duration': audio.duration,
            'genre': audio.genre,
            'year': audio.get_year(),
        }
        file_ext = audio.get_file_ext()
        filename = filepath_parse_pattern(
            "%s/%s%s" % (self.folder_hierarchy, self.filename_template, f'.{file_ext}' if len(file_ext) else ''), tags)
        filename = "%s/%s" % (self.library_location, filename)
        filename = self._move_file(audio.local_path, filename)
        audio.save({"local_path": filename, "is_moved": True})
        audio.update_entry(entry)
        GLib.idle_add(entry.get_entry_type().emit, 'entry_downloaded', entry)
        self._next()

    def _next(self):
        self.entries[self._idx] = None
        self._idx = self._idx + 1
        if self._idx >= len(self.entries):
            self.stop()
            return
        GLib.timeout_add(1000, self._load)

    def _load(self):
        if self._running:
            entry = self.entries[self._idx]
            audio = self.plugin.storage.get_entry_audio(entry)
            if not audio:
                self._next()
                return
            self._update_progress(audio)
            if audio.is_moved:
                set_entry_state(self.plugin.db, entry, audio.get_state())
                self.plugin.db.commit()
                self._next()
                return
            file_path = audio.get_path()
            if file_path:
                self._process(audio)
            else:
                audio.download(success=self._process, fail=self._next)


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
        GLib.timeout_add(10000 if self.page > 10 else 5000, self._load, {"offset_msg_id": offset_msg_id})

    def stop(self):
        self._terminated = True

    def _load(self, blob={}, limit=50):
        if not self._terminated:
            self.api.load_messages_idle( self.chat_id, update=self._add_audio, done=self._next, blob={**blob}, limit=limit)
