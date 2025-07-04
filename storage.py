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
import sqlite3
import json
import logging
import schema
from gi.repository import RB
from common import audio_content_set, empty_cb, get_audio_tags, get_date, get_year, mime_types, filepath_parse_pattern
from common import get_location_data, set_entry_state, version_to_number, extract_track_number
from typing import List, Literal, Dict

logger = logging.getLogger(__name__)

SEGMENT_START = 0
SEGMENT_END = 1
CURRENT_SEGMENT = 0

VISIBILITY_ALL = None
VISIBILITY_VISIBLE = 1
VISIBILITY_HIDDEN = 0

class Playlist:
    """ Represents a playlist with segments and metadata """
    id: int
    chat_id: int
    title: str
    original_title: str
    snapshot: str
    segments: List[List[int]]
    has_changed: bool = False

    def __str__(self) -> str:
        return f'Playlist <{self.chat_id}>'

    def __init__(self, data):
        """ Initialize playlist with data """
        self.update(data)

    def is_changed_segments(self):
        """ Check if segments have changed """
        return json.dumps(self.segments) != self.snapshot

    def update(self, data):
        """ Update playlist data """
        id_, chat_id, title, original_title, segments = data
        self.id = id_
        self.chat_id = chat_id
        self.title = title
        self.original_title = original_title
        self.snapshot = segments
        self.segments = json.loads(segments)

    def insert_empty(self):
        """ Insert empty segment at current position """
        self.segments.insert(CURRENT_SEGMENT, [0, 0])

    def set_current(self, segment_type, value):
        """ Set value for current segment """
        self.segments[CURRENT_SEGMENT][segment_type] = value

    def current(self, segment_type):
        """ Get current segment value """
        return self.segments[CURRENT_SEGMENT][segment_type] if len(self.segments) else 0

    def search(self, value):
        """ Search for value in segments """
        for num, segment in enumerate(self.segments):
            if num == CURRENT_SEGMENT:
                continue
            if value in segment:
                return num, segment.index(value)
        return None

    @staticmethod
    def read(chat_id):
        """ Read playlist from storage by chat_id """
        playlist = Storage.loaded().select('playlist', {"chat_id": chat_id})
        data = playlist if playlist else tuple([0, chat_id, '', '', '[]'])
        return Playlist(data)

    def join_segments(self, value):
        """ Join segments around specified value """
        segments = [self.segments[CURRENT_SEGMENT].copy()]
        segments_old = self.segments.copy()
        for num, segment in enumerate(segments_old):
            if num == CURRENT_SEGMENT:
                continue
            if value in segment:
                bound = segment.index(value)
                if bound == SEGMENT_START:
                    segments[CURRENT_SEGMENT][SEGMENT_END] = segment[SEGMENT_END]
                # else:
                #     segments[CURRENT_SEGMENT][SEGMENT_END] = value
                continue
            segments.append(segment)
        self.segments = segments

    def save(self):
        """ Save playlist to storage """
        if not self.is_changed_segments():
            return False
        playlist = {
            "chat_id": self.chat_id,
            "title": self.title,
            "original_title": self.original_title,
            "segments": json.dumps(self.segments)
        }
        # print('Saving playlist')
        self.has_changed = False
        if self.id != 0:
            return Storage.loaded().update('playlist', playlist, {"chat_id": self.chat_id}, 1)
        return Storage.loaded().insert('playlist', playlist)


class Audio:
    """ Represents an audio track with metadata and state """
    STATE_DEFAULT = 0
    STATE_DOWNLOADED = 1
    STATE_IN_LIBRARY = 2
    STATE_LOADING = 3
    STATE_HIDDEN = 8
    STATE_ERROR = 9

    id: int
    chat_id: int
    message_id: int
    mime_type: str
    track_number: int
    title: str
    artist: str
    album_artist: str
    album: str
    genre: str
    file_name: str
    created_at: int
    date: int
    size: int
    duration: int
    is_downloaded: int
    is_moved: Literal[0, 1]
    is_hidden: Literal[0, 1]
    local_path: str
    play_count: int
    rating: Literal[0, 1, 2, 3, 4, 5]

    is_error = False
    is_reloaded = False
    link = None

    def __str__(self) -> str:
        return f'Audio <{self.chat_id},{self.message_id}>'

    def __init__(self, data):
        self.update(data)

    def update(self, data):
        """ Update audio data """
        if type(data) == tuple:
            id_, chat_id, message_id, mime_type, track_number, title, artist, album, genre, file_name, created_at, \
                date, size, duration, is_downloaded, is_moved, is_hidden, local_path, play_count, rating = data
            self.id = id_
            self.chat_id = chat_id
            self.message_id = message_id
            self.mime_type = mime_type
            self.track_number = track_number
            self.title = title
            self.artist = artist
            self.album_artist = self.artist
            self.album = album or ''
            self.genre = genre or ''
            self.file_name = file_name
            self.created_at = created_at
            self.date = date
            self.size = size
            self.duration = duration
            self.is_downloaded = is_downloaded
            self.is_moved = is_moved
            self.is_hidden = is_hidden
            self.local_path = local_path
            self.play_count = play_count or 0
            self.rating = rating or 0
        else:
            self.id = data.get('id', 0)
            self.chat_id = data['chat_id']
            self.message_id = data['message_id']
            self.mime_type = data.get('mime_type', '')
            self.track_number = data.get('track_number', 0)
            self.title = data.get('title', '')
            self.artist = data.get('artist', '')
            self.album_artist = self.artist
            self.album = data.get('album', '')
            self.genre = data.get('genre', '')
            self.file_name = data.get('file_name', '')
            self.created_at = data.get('created_at', 0)
            self.date = data.get('date', 0)
            self.size = data.get('size', 0)
            self.duration = data.get('duration', 0)
            self.is_downloaded = data.get('is_downloaded', 0)
            self.is_moved = data.get('is_moved', 0)
            self.is_hidden = data.get('is_hidden', 0)
            self.local_path = data.get('local_path')
            self.play_count = data.get('play_count', 0)
            self.rating = data.get('rating', 0)

    def get_album_artist(self):
        """ Get album artist or fallback to artist """
        return self.album_artist if self.album_artist and len(self.album_artist) else self.artist

    def get_year(self):
        """ Get year from date """
        return get_year(self.date)

    def is_file_exists(self):
        """ Check if audio file exists """
        isfile = self.is_downloaded and self.local_path and len(self.local_path) > 1 and os.path.isfile(self.local_path)
        if not isfile:
            self.is_downloaded = 0
        return isfile

    def get_state(self):
        """ Get current state of audio """
        if self.is_error:
            return Audio.STATE_ERROR
        if self.is_hidden:
            return Audio.STATE_HIDDEN
        if self.is_moved:
            return Audio.STATE_IN_LIBRARY
        if self.is_downloaded:
            return Audio.STATE_DOWNLOADED
        return Audio.STATE_DEFAULT

    def _upd_and_move(self):
        """ Update tags and move file to organized location """
        if len(self.local_path or ''):
            # read tags
            tags = get_audio_tags(self.local_path)
            self.album_artist = tags.get('album_artist', '')
            for tag in dict(tags):
                if tags[tag] is None:
                    del tags[tag]
            # format temp filename
            src_dir = os.path.dirname(self.local_path)
            chn_dir = f"{self.chat_id}".replace('-100', '')
            sub_dir = filepath_parse_pattern('%aa/%aa - %at (%ay)', tags)
            dst_dir = str(os.path.join(src_dir, chn_dir, sub_dir))
            os.makedirs(dst_dir, exist_ok=True)
            new_path = os.path.join(dst_dir, '%s.%s' % (self.message_id, self.get_file_ext()))
            os.rename(self.local_path, new_path)
            # remove tags which not used by Audio
            if tags.get('album_artist'):
                del tags['album_artist']
            if tags.get('year'):
                del tags['year']
            # write both tags and new local_path
            self.save({**tags, "local_path": new_path})

    def download(self, success=empty_cb, fail=empty_cb):
        """ Download audio file """
        storage = Storage.loaded()
        api = storage.api

        def on_success(data):
            self.update(data)
            self._upd_and_move()
            success(self)

        def on_fail():
            self.is_error = True
            fail()

        api.download_audio_idle(self.chat_id, self.message_id, priority=1, on_success=on_success, on_error=on_fail)

    def get_path(self):
        """ Get file path if exists """
        if not self.is_file_exists():
            self.local_path = None # noqa
            return None
        return self.local_path

    def save(self, data):
        """ Save audio data to storage """
        res = Storage.loaded().update('audio', data, {"id": self.id}, limit=1)
        if res:
            for k in data.keys():
                setattr(self, k, data[k])
        return res

    def get_link(self):
        """ Get message link from Telegram """
        return Storage.loaded().api.get_message_link(self.chat_id, self.message_id)

    def get_file_ext(self):
        """ Get file extension from mime type or filename """
        if self.mime_type in mime_types.keys():
            return mime_types[self.mime_type]
        return os.path.splitext(self.file_name)[1][1:]

    def update_entry(self, entry, db=None, commit=True, state=True):
        """ Update Rhythmbox entry with audio data """
        if db is None:
            db = entry.get_entry_type().db
        db.entry_set(entry, RB.RhythmDBPropType.TRACK_NUMBER, self.track_number)
        db.entry_set(entry, RB.RhythmDBPropType.TITLE, self.title)
        db.entry_set(entry, RB.RhythmDBPropType.ARTIST, self.artist)
        db.entry_set(entry, RB.RhythmDBPropType.ALBUM, self.album)
        db.entry_set(entry, RB.RhythmDBPropType.ALBUM_ARTIST, self.artist)
        db.entry_set(entry, RB.RhythmDBPropType.GENRE, self.genre)
        db.entry_set(entry, RB.RhythmDBPropType.DURATION, self.duration)
        db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(self.created_at))
        db.entry_set(entry, RB.RhythmDBPropType.DATE, int(self.date))
        db.entry_set(entry, RB.RhythmDBPropType.PLAY_COUNT, int(self.play_count))
        db.entry_set(entry, RB.RhythmDBPropType.FILE_SIZE, int(self.size))
        db.entry_set(entry, RB.RhythmDBPropType.RATING, float(self.rating))
        if state:
            set_entry_state(db, entry, self.get_state())
        if commit:
            db.commit()


class Migration:
    """ Handles migrations """

    def __init__(self, db, migrations: Dict[str, str]):
        """ Initialize with db and migration scripts """
        self.db = db
        self.migrations: Dict[int, str] = {}

        for version, sql in migrations.items():
            self.add_migration(version, sql)

    def add_migration(self, version: str, sql: str):
        """ Add migration script for version """
        self.migrations[version_to_number(version)] = sql

    def _get_current_version(self) -> int:
        """ Get current database version """
        cursor = self.db.cursor()
        cursor.execute("PRAGMA table_info(migrations);")
        if not cursor.fetchall():
            version_1_0_0 = version_to_number('1.0.0')
            cursor.execute("CREATE TABLE migrations (version INTEGER PRIMARY KEY);")
            cursor.execute("INSERT INTO migrations (version) VALUES (?);", (version_1_0_0,))
            self.db.commit()
            return version_1_0_0

        cursor.execute("SELECT version FROM migrations ORDER BY version DESC LIMIT 1;")
        return int(cursor.fetchone()[0])

    def apply(self):
        """ Apply pending migrations """
        cursor = self.db.cursor()
        current_version = self._get_current_version()

        for version, migration in sorted(self.migrations.items(), key=lambda item: item[0]):
            if version > current_version:
                print(f"Running migration for version {version}")
                try:
                    if isinstance(migration, str):  # SQL query
                        cursor.execute(migration)
                    elif callable(migration):  # Python func
                        migration(cursor)
                    elif isinstance(migration, (list, tuple)):
                        # list or tuple of SQL queries and/or Python functions
                        for section in migration:
                            if isinstance(section, str):  # SQL query
                                cursor.execute(section)
                            elif callable(section):  # Python func
                                section(cursor)
                            else:
                                raise ValueError(f"Unsupported migration type: {type(section)}")
                    else:
                        raise ValueError(f"Unsupported migration type: {type(migration)}")

                    cursor.execute("INSERT INTO migrations (version) VALUES (?);", (version,))
                    self.db.commit()
                    print(f"Migration for version {version} applied successfully.")
                except Exception as e:
                    self.db.rollback()
                    print(f"Error applying migration for version {version}: {e}")
                    raise

class Storage:
    """ Manages database storage and operations """
    _instance = None

    def __str__(self) -> str:
        return f'Storage <{self.api.hash}>'

    def __init__(self, api, files_dir):
        """ Initialize storage """
        self.api = api
        self.files_dir = files_dir
        self.db_file = os.path.join(self.files_dir, 'data.sqlite')
        create_db = not os.path.exists(self.db_file)
        self.db = sqlite3.connect(self.db_file)
        Storage._instance = self

        if create_db:
            try:
                self.db.executescript(schema.INIT_SCHEMA)
            except Exception as e:
                os.remove(self.db_file)
                raise Exception(e)

        migration = Migration(self.db, schema.MIGRATIONS)
        migration.apply()

    @staticmethod
    def loaded():
        """ Get loaded storage instance """
        return Storage._instance

    def select(self, table, where, limit=1):
        """ Select rows from table """
        set_where = []
        set_values = []
        for k in where.keys():
            set_where.append(f'{k} = ?')
            set_values.append(where[k])
        set_where = ' and '.join(set_where)
        sql = f"SELECT * FROM `{table}` WHERE {set_where}"
        if limit and limit > 0:
            sql = f'{sql} LIMIT {limit}'
        cursor = self.db.execute(sql, tuple(set_values))
        if not limit or limit > 1:
            return cursor.fetchall()
        return cursor.fetchone()

    def update(self, table, data, where, limit=0):
        """ Update rows in table """
        set_keys, set_values = self._prepare(data)
        set_where = []
        for k in where.keys():
            set_where.append(f'{k} = ?')
            set_values.append(where[k])
        set_where = ' AND '.join(set_where)
        sql = f"UPDATE `{table}` SET {set_keys} WHERE {set_where}"
        if limit and limit > 0:
            sql = f'{sql} LIMIT {limit}'
        cursor = self.db.execute(sql, tuple(set_values))
        result = cursor.rowcount > 0
        self.db.commit()
        return result

    def insert(self, table, data):
        """ Insert row into table """
        set_keys = []
        set_place = []
        set_values = []
        for k in data.keys():
            set_keys.append(f'{k}')
            set_values.append(data[k])
            set_place.append('?')
        set_keys = ', '.join(set_keys)
        set_place = ', '.join(set_place)
        sql = f"INSERT INTO `{table}` ({set_keys}) VALUES ({set_place})"
        cursor = self.db.execute(sql, tuple(set_values))
        result = cursor.rowcount > 0
        self.db.commit()
        return result

    def _prepare(self, data):
        """ Prepare data for SQL operations """
        if not data:
            return None
        set_keys = []
        set_values = []
        for k in data.keys():
            set_keys.append(f'`{k}` = ?')
            set_values.append(data[k])
        set_keys = ', '.join(set_keys)
        return set_keys, set_values

    def get_entry_audio(self, entry):
        """ Get Audio instance from Rhythmbox entry """
        uri = entry.get_string(RB.RhythmDBPropType.LOCATION)
        chat_id, message_id = get_location_data(uri)
        return self.get_audio(chat_id, message_id, True)

    def get_audio(self, chat_id, message_id, convert=True):
        """ Get audio by chat and message ID """
        audio = self.db.execute(
            "SELECT * FROM `audio` WHERE chat_id = '%s' and message_id = '%s' LIMIT 1" % (chat_id, message_id))
        result = audio.fetchone()
        if result and convert:
            return Audio(result)
        return result

    def load_entries(self, chat_id, each, visibility=VISIBILITY_ALL):
        """ Load entries for chat with visibility filter """
        sql = 'SELECT * FROM `audio` WHERE chat_id = ?' # noqa
        data = (chat_id,)
        if visibility == VISIBILITY_VISIBLE:
            sql += ' AND is_hidden = ?'
            data = (chat_id, 0)
        elif visibility == VISIBILITY_HIDDEN:
            sql += ' AND is_hidden = ?'
            data = (chat_id, 1)
        cursor = self.db.cursor()
        cursor.execute(sql, data)
        for row in cursor:
            each(Audio(row))
        cursor.close()

    def each(self, callback, table, where, order=None):
        """ Iterate through table rows """
        set_where = []
        set_values = []
        for k in where.keys():
            set_where.append(f'{k} = ?')
            set_values.append(where[k])
        set_where = ' and '.join(set_where)
        sql = f"SELECT * FROM `{table}` WHERE {set_where}"
        if order:
            sql += ' ORDER BY %s' % order
        cursor = self.db.cursor()
        cursor.execute(sql, tuple(set_values))
        for row in cursor:
            callback(row)
        cursor.close()

    def add_audio(self, data, convert=True):
        """ Add new audio to storage """
        content = data.get('content', {})
        audio = content.get('audio')

        if not (audio and audio_content_set <= set(audio)):
            logger.warning('Audio message has no required keys, skipping...')
            logger.debug(content)
            return
        d = {}

        completed = audio['audio']['remote']['is_uploading_completed']
        local = audio['audio']['local']
        d['audio_id'] = audio_id = audio['audio']['id']

        if not completed:
            logger.warning('Audio message: %d not uploaded, skipping...', audio_id)
            return

        d['track_number'] = extract_track_number(audio['file_name'])
        d['chat_id'] = data['chat_id']
        d['message_id'] = data['id']
        d['mime_type'] = audio['mime_type']
        d['file_name'] = audio['file_name']
        d['artist'] = audio['performer']
        d['title'] = audio['title']
        d['duration'] = audio['duration']
        d['size'] = audio['audio']['size']
        d['local_path'] = local['path']
        d['is_downloaded'] = 1 if local['is_downloading_completed'] else 0
        d['created_at'] = data['date']
        d['date'] = get_date(data['date'])

        tg_audio = self.get_audio(d['chat_id'], d['message_id'], True)
        if tg_audio:
            # flag for indicate already loaded audio for PlaylistLoader
            tg_audio.is_reloaded = True
            if d['local_path']:
                # update audio only if it was downloaded
                # print('Update audio %s' % tg_audio.id)
                tg_audio.save({
                    'size': d['size'],
                    'local_path': d['local_path'],
                    'is_downloaded': d['is_downloaded'],
                    'is_moved': 0,
                })
            d['id'] = tg_audio.id
            d['size'] = tg_audio.size
            d['local_path'] = tg_audio.local_path
            d['is_downloaded'] = tg_audio.is_downloaded
            d['is_moved'] = tg_audio.is_moved

            return d if not convert else tg_audio

        cursor = self.db.execute("""
            INSERT INTO `audio` (
                chat_id, message_id, mime_type, title, artist, file_name, `date`, `created_at`, size, duration,
                local_path, is_downloaded, track_number)
            VALUES (
                :chat_id, :message_id, :mime_type, :title, :artist, :file_name, :date, :created_at, :size, :duration,
                :local_path, :is_downloaded, :track_number)
        """ , d)

        d['id'] = cursor.lastrowid
        self.db.commit()
        return d if not convert else Audio(d)
