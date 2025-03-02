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

import os
import re
import shutil
from gi.repository import GLib, RB
from account import KEY_FOLDER_HIERARCHY, KEY_CONFLICT_RESOLVE, KEY_FILENAME_TEMPLATE
from account import KEY_DETECT_DIRS_IGNORE_CASE, KEY_DETECT_FILES_IGNORE_CASE
from common import CONFLICT_ACTION_RENAME, CONFLICT_ACTION_REPLACE, CONFLICT_ACTION_SKIP, CONFLICT_ACTION_ASK
from common import get_entry_location, CONFLICT_ACTION_IGNORE
from common import filepath_parse_pattern, SingletonMeta, get_entry_state, set_entry_state
from conflict_dialog import ConflictDialog
from storage import Playlist, Audio, SEGMENT_START, SEGMENT_END
from telegram_client import TelegramApi, API_ALL_MESSAGES_LOADED, LAST_MESSAGE_ID
from typing import Tuple


class AbsAudioLoader:
    def __init__(self, plugin):
        self.plugin = plugin
        self._queue = []
        self._running = False
        self._idx = 0

    def stop(self):
        self._running = False
        self._queue = []
        self._idx = 0

    def get_entry(self, idx):
        uri = self._queue[idx]
        return self.plugin.db.entry_lookup_by_location(uri)


class AudioTempLoader(AbsAudioLoader, metaclass=SingletonMeta):
    """
    AudioTempLoader is designed to sequentially download audio files into a temp directory.
    The most recently added records to the queue are loaded first.
    The downloading process is assigned the highest priority level.
    """
    def __init__(self, plugin):
        AbsAudioLoader.__init__(self, plugin)
        self._is_hidden = False

    def add_entry(self, entry):
        state = get_entry_state(entry)
        if state != Audio.STATE_IN_LIBRARY and state != Audio.STATE_LOADING:
            uri = get_entry_location(entry)
            if uri not in self._queue:
                self._queue.append(uri)
                set_entry_state(self.plugin.db, entry, Audio.STATE_LOADING)
                self.plugin.db.commit()
        return self

    def start(self):
        if len(self._queue) > 0:
            if not self._running:
                self._running = True
                self._idx = len(self._queue) - 1
                self._load()
        else:
            self.stop()
        return self

    def _process(self, audio):
        entry = self.get_entry(self._idx)
        if not entry:
            self._next(20)
            return
        if self._is_hidden:
            self._is_hidden = False
            audio.save({"is_hidden": True})
        audio.update_entry(entry)
        GLib.idle_add(entry.get_entry_type().emit, 'entry_downloaded', entry)
        self._next(1000)

    def _next(self, delay=1000):
        self._is_hidden = False
        del self._queue[self._idx]
        self._idx = len(self._queue) - 1
        if self._idx < 0:
            self.stop()
            return
        GLib.timeout_add(delay, self._load)

    def _load(self):
        if self._running:
            entry = self.get_entry(self._idx)
            if not entry:
                self._next(20)
                return
            audio = self.plugin.storage.get_entry_audio(entry)
            if not audio:
                self._next(20)
                return
            file_path = audio.get_path()
            if file_path:
                set_entry_state(self.plugin.db, entry, audio.get_state())
                self.plugin.db.commit()
                self._next(20)
            else:
                self._is_hidden = audio.is_hidden
                audio.download(success=self._process, fail=self._next)


class AudioDownloader(AbsAudioLoader, metaclass=SingletonMeta):
    """
    AudioDownloader is designed to sequentially download audio files into a Music library.
    The first entries added to the queue are downloaded first.
    The downloading process is assigned a medium priority level.
    """
    library_location: str
    folder_hierarchy: str
    conflict_resolve: str
    filename_template: str
    detect_dirs_ignore_case: bool
    detect_files_ignore_case: bool

    def __init__(self, plugin):
        AbsAudioLoader.__init__(self, plugin)
        self._info = {}
        self.setup()

    def setup(self):
        self.library_location = self.plugin.account.get_library_path().rstrip('/')
        self.folder_hierarchy = self.plugin.settings[KEY_FOLDER_HIERARCHY]
        self.conflict_resolve = self.plugin.settings[KEY_CONFLICT_RESOLVE]
        self.filename_template = self.plugin.settings[KEY_FILENAME_TEMPLATE]
        self.detect_dirs_ignore_case = self.plugin.settings[KEY_DETECT_DIRS_IGNORE_CASE]
        self.detect_files_ignore_case = self.plugin.settings[KEY_DETECT_FILES_IGNORE_CASE]

    def add_entries(self, entries):
        commit = False
        for entry in entries:
            state = get_entry_state(entry)
            if state != Audio.STATE_IN_LIBRARY:
                uri = get_entry_location(entry)
                if uri not in self._queue:
                    self._queue.append(uri)
                    set_entry_state(self.plugin.db, entry, Audio.STATE_LOADING)
                    commit = True
        if commit:
            self.plugin.db.commit()

    def stop(self):
        AbsAudioLoader.stop(self)
        self._update_progress()

    def start(self):
        if len(self._queue) > 0:
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
        total = len(self._queue)
        info = {
            "active": self._running,
            "index": self._idx + 1,
            "total": total,
            "filename": filename if len(filename) else self._info.get('filename', ''),
            "fraction": self._idx / total if total > 0 else 1.0,
        }
        self._info = info
        self.plugin.emit('update_download_info', info)

    def _move_file(self, action, src, dst):
        dst_dir = str(os.path.dirname(dst)).rstrip('/')
        os.makedirs(dst_dir, exist_ok=True)

        if action == CONFLICT_ACTION_SKIP:
            if os.path.exists(dst):
                print(f"File '{dst}' already exists. Skipping.")
                return dst
            else:
                shutil.move(src, dst)

        elif action == CONFLICT_ACTION_REPLACE:
            shutil.move(src, dst)

        elif action == CONFLICT_ACTION_RENAME:
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

    def _move_audio_and_update(self, action, audio, filename):
        entry = self.get_entry(self._idx)
        if not entry:
            self._next(20)
            return
        if action != CONFLICT_ACTION_IGNORE:
            filename = self._move_file(action, audio.local_path, filename)
            audio.save({"local_path": filename, "is_moved": True})
        audio.update_entry(entry)
        GLib.idle_add(entry.get_entry_type().emit, 'entry_downloaded', entry)
        self._next(1000)

    def _create_dirs(self, root, directory):
        if not self.detect_dirs_ignore_case:
            path = os.path.join(root, directory)
            os.makedirs(path, exist_ok=True)
            return path

        current_path = root
        dirs = directory.split('/')

        for dir_name in dirs:
            pattern = re.compile(re.escape(dir_name), re.IGNORECASE)
            found = False
            for item in os.listdir(current_path):
                if os.path.isdir(os.path.join(current_path, item)) and pattern.fullmatch(item):
                    current_path = os.path.join(current_path, item)
                    found = True
                    break
            if not found:
                new_dir = os.path.join(current_path, dir_name)
                os.makedirs(new_dir)
                current_path = new_dir
        return current_path

    def _get_filename(self, filename):
        if not self.detect_files_ignore_case:
            return filename

        dirpath = os.path.dirname(filename)
        basename = os.path.basename(filename)
        pattern = re.compile(re.escape(basename), re.IGNORECASE)

        for item in os.listdir(dirpath):
            if os.path.isfile(os.path.join(dirpath, item)) and pattern.fullmatch(item):
                return os.path.join(dirpath, item)
        return filename

    def _process(self, audio):
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
        audio.meta_tags = tags

        filedir = filepath_parse_pattern(self.folder_hierarchy, tags)
        filepath = self._create_dirs(self.library_location, filedir)
        file_ext = audio.get_file_ext()
        extension = f'.{file_ext}' if len(file_ext) else ''
        basename = filepath_parse_pattern(self.filename_template, tags)
        filename = '%s/%s%s' % (filepath, basename, extension)
        filename = self._get_filename(filename)

        if self.conflict_resolve == CONFLICT_ACTION_ASK:
            if os.path.exists(filename):
                ConflictDialog(self.plugin, audio, filename, self._move_audio_and_update)
            else:
                self._move_audio_and_update(CONFLICT_ACTION_REPLACE, audio, filename)
        else:
            self._move_audio_and_update(self.conflict_resolve, audio, filename)

    def _next(self, delay=1000):
        self._queue[self._idx] = None
        self._idx = self._idx + 1
        if self._idx >= len(self._queue):
            self.stop()
            return
        GLib.timeout_add(delay, self._load)

    def _load(self):
        if self._running:
            entry = self.get_entry(self._idx)
            if not entry:
                self._next(20)
                return
            audio = self.plugin.storage.get_entry_audio(entry)
            if not audio:
                self._next(20)
                return
            self._update_progress(audio)
            if audio.is_moved:
                set_entry_state(self.plugin.db, entry, audio.get_state())
                self.plugin.db.commit()
                self._next(20)
                return
            file_path = audio.get_path()
            if file_path:
                self._process(audio)
            else:
                audio.download(success=self._process, fail=self._next)


MAX_PAGES_SHORT_INTERVAL = 10

INTERVAL_SHORT  = 5000    # 5 sec
INTERVAL_MEDIUM = 20000   # 20 sec
INTERVAL_LONG   = 120000  # 2 min

SIGNAL_REACHED_START = 'SIGNAL_REACHED_START'
SIGNAL_REACHED_END   = 'SIGNAL_REACHED_END'
SIGNAL_REACHED_NEXT  = 'SIGNAL_REACHED_NEXT'


class PlaylistTimer(metaclass=SingletonMeta):
    _props: Tuple[any, any] | None
    _timer_id: int | None

    def __init__(self):
        self._props = None
        self._timer_id = None

    def add(self, interval, callback, *args):
        self.remove()
        self._props = (callback, args)
        self._timer_id = GLib.timeout_add(interval, self.callback)

    def remove(self):
        ret = False
        if self._timer_id:
            ret = GLib.source_remove(self._timer_id)
            self._timer_id = None
        return ret

    def callback(self):
        self._timer_id = None
        if self._props:
            callback, args = self._props
            callback(*args)
            self._props = None
        return False

    def clear(self):
        self._timer_id = None
        self._props = None


class PlaylistLoader:
    api: TelegramApi
    playlist: Playlist
    timer: PlaylistTimer | None
    terminated: bool
    last_msg_id: int

    def __str__(self) -> str:
        return f'PlaylistLoader <{self.chat_id}>'

    def __init__(self, source, chat_id, add_entry):
        self.terminated = False
        self.api = TelegramApi.loaded()
        self.source = source
        self.chat_id = chat_id
        self.add_entry = add_entry
        self.page = 0
        self.timer = PlaylistTimer()

    def start(self, *obj):
        """ Start loading messages starting from new messages """
        if self.terminated:
            return
        self.last_msg_id = 0
        self.playlist = Playlist.read(self.chat_id)
        self.playlist.insert_empty()
        self._load({}, limit=1)

    def _add_audio(self, audio, blob):
        """ Add audio as entry in the playlist. """
        if not audio.is_reloaded:
            self.add_entry(audio)

    def _each(self, data, blob):
        """ Iterate over all messages, check for segment boundaries """
        message_id = int(data['id'])
        result = self.playlist.search(message_id)

        if result is not None:
            blob['signal'] = SIGNAL_REACHED_NEXT
            blob['message_id'] = message_id
            return False

        if self.playlist.current(SEGMENT_START) == 0:
            self.playlist.set_current(SEGMENT_START, message_id)
        return True

    def _process(self, blob, cmd):
        """ Read data, update playlist segments, loading next page """
        if self.terminated:
            return
        GLib.timeout_add(2000, self.source.emit, 'playlist-fetch-end')

        signal = blob.get('signal')
        offset_msg_id = blob.get('last_msg_id', 0)

        if cmd == API_ALL_MESSAGES_LOADED or offset_msg_id in (0, self.last_msg_id, LAST_MESSAGE_ID):
            self.source.has_reached_end = True
            self.timer.add(INTERVAL_LONG, self.start)
            return

        if self.playlist.current(SEGMENT_START) == 0:
            self.playlist.set_current(SEGMENT_START, offset_msg_id)
        self.playlist.set_current(SEGMENT_END, offset_msg_id)

        if signal == SIGNAL_REACHED_NEXT:
            message_id = blob.get('message_id')
            self.playlist.set_current(SEGMENT_END, message_id)
            self.playlist.join_segments(message_id)
            offset_msg_id = self.playlist.current(SEGMENT_END)

        if self.playlist.save():
            self.playlist = Playlist.read(self.chat_id)

        if (signal == SIGNAL_REACHED_NEXT and self.source.has_reached_end) or offset_msg_id == LAST_MESSAGE_ID:
            self.source.has_reached_end = True
            self.timer.add(INTERVAL_LONG, self.start)
            return

        if self.page <= MAX_PAGES_SHORT_INTERVAL:
            self.page = self.page + 1

        self.last_msg_id = offset_msg_id
        self.timer.add(INTERVAL_MEDIUM if self.page > MAX_PAGES_SHORT_INTERVAL else INTERVAL_SHORT, self._load, {"offset_msg_id": offset_msg_id})

    def _load(self, blob, limit=50):
        """ Load messages """
        if self.terminated:
            return

        self.source.emit('playlist-fetch-started')
        self.api.load_messages_idle(self.chat_id, update=self._add_audio, each=self._each, on_success=self._process,
                                    blob={**blob}, limit=limit)

    def fetch(self):
        """ Fetch next messages """
        if self.timer.remove():
            self.timer.callback()

    def stop(self):
        """ Stop loading """
        self.terminated = True
        self.timer.remove()
        self.timer.clear()
        self.source.emit('playlist-fetch-end')
