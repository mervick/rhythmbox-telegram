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

import sqlite3
import json
import os
import logging
import re
import schema as SQL
from common import audio_content_set, empty_cb


logger = logging.getLogger(__name__)


def parse_title(content):
    title = [None, content]
    s = content.strip()
    r = re.search("^\s*([^\n]+?)\s-\s([^\n]+)\n?", s)
    if not r:
        r = re.search("^\s*([^\n]+?)-([^\n]+)\n?", s)
    if r:
        groups = r.groups()
        title = [groups[0].strip(), groups[1].strip()]
    return title

def parse_info(content):
    info = {"content": content}
    title = parse_title(content)
    info["artist"] = title[0]
    info["title"] = title[1]
    r = re.search("genre:\s*([^\n]*)\n", content, re.IGNORECASE)
    if r:
        info["genre"] = r.groups()[0].strip()
    r = re.search("country:\s*([^\n]*)\n", content, re.IGNORECASE)
    if r:
        info["country"] = r.groups()[0].strip()
    return info

def parse_album_info(content):
    genre = None
    genres = None
    year = None
    artist, title = parse_title(content)
    if not artist:
        return None, None, year, genre, genres
    r = re.search("^\s*([^\n]+?)\s*(\(\s*\d+\s*\))?\s*$", title)
    if r:
        groups = r.groups()
        title = groups[0].strip()
        year = groups[1].replace('(', '').replace(')', '').strip()
    r = re.search("(?:^|\n)genre:\s*([^\n]*)(?:\n|$)", content, re.IGNORECASE)
    if r:
        genres = [x.strip() for x in r.groups()[0].strip().replace(',', '/').split('/')]
    else:
        genres = [x.replace('_', ' ').replace('-', ' ')
            for x in re.findall("\s*#([^\s#]*)", content, re.IGNORECASE)]
    if genres:
        genre = ' / '.join(genres)
    return artist, title, year, genre, genres


class TgPlaylist:
    def __str__(self) -> str:
        return f'TgPlaylist <{self.chat_id}>'

    def __init__(self, data):
        self._data = data
        self.update(data)

    def update(self, data):
        id_, chat_id, title, original_title, segments = data
        self.id = id_
        self.chat_id = chat_id
        self.title = title
        self.original_title = original_title
        self.segments = json.loads(segments)

    def segment(self, index):
        if len(self.segments) > index:
            return self.segments[index]
        return [0, 0]

    @staticmethod
    def read(chat_id):
        playlist = TelegramStorage.loaded().select('playlist', {"chat_id": chat_id})
        data = playlist if playlist else tuple([0, chat_id, '', '', '[]'])
        return TgPlaylist(data)

    def reload(self):
        self._data = TgPlaylist.read(self.chat_id)._data

    def save(self):
        print('TgPlaylist.save')
        segments = [segment for segment in self.segments if segment[0] != 0]
        print(segments)
        playlist = {
            "chat_id": self.chat_id,
            "title": self.title,
            "original_title": self.original_title,
            "segments": json.dumps(self.segments)
        }
        if self.id != 0:
            return TelegramStorage.loaded().update('playlist', playlist, {"chat_id": self.chat_id}, 1)
        return TelegramStorage.loaded().insert('playlist', playlist)


class TgAudio:
    def __str__(self) -> str:
        return f'TgAudio <{self.chat_id},{self.message_id}>'

    def __init__(self, data):
        self._data = data
        self.update(data)

    def update(self, data):
        if type(data) == tuple:
            id_, chat_id, message_id, mime_type, title, artist, album, year, genre, file_name, date, \
                size, duration, is_downloaded, is_moved, is_hidden, local_path, info_id = data
            self.id = id_
            self.chat_id = chat_id
            self.message_id = message_id
            self.mime_type = mime_type
            self.title = title
            self.artist = artist
            self.album = album
            self.year = year
            self.genre = genre
            self.file_name = file_name
            self.date = date
            self.size = size
            self.duration = duration
            self.is_downloaded = is_downloaded
            self.is_moved = is_moved
            self.is_hidden = is_hidden
            self.local_path = local_path
            self.info_id = info_id
        else:
            self.id = data['id']
            self.chat_id = data['chat_id']
            self.message_id = data['message_id']
            self.mime_type = data['mime_type']
            self.title = data['title']
            self.artist = data['artist']
            self.album = data.get('album')
            self.year = data.get('year')
            self.genre = data.get('genre')
            self.file_name = data['file_name']
            self.date = data['date']
            self.size = data['size']
            self.duration = data['duration']
            self.is_downloaded = data.get('is_downloaded', False)
            self.is_moved = data.get('is_moved', False)
            self.is_hidden = data.get('is_hidden', False)
            self.local_path = data.get('local_path')
            self.info_id = data.get('info_id')

    def _is_file_exists(self):
        isfile = self.is_downloaded and os.path.isfile(self.local_path)
        if not isfile:
            self.is_downloaded = False

    def get_path(self, priority=1, wait=False, done=empty_cb):
        print('get_path')
        if not self._is_file_exists():
            print('not_downloaded')
            api = TelegramStorage.loaded().api
            if wait:
                audio = api.download_audio_async(self.chat_id, self.message_id, priority)
                print('== audio %s' % audio)
                if not audio:
                    # @TODO remove audio, mark as invalid
                    return ''
                self.update(audio)
                return self.local_path
            else:
                def on_done(data):
                    # update = TelegramApi.loaded().add_audio(data, convert=False)
                    self.update(data)
                    done(self)

                api.download_audio_idle(self.chat_id, self.message_id, priority=priority, done=on_done)
                return None

        return self.local_path

    def save(self, data):
        res = TelegramStorage.loaded().update('audio', data, {"id": self.id}, limit=1)
        if res:
            for k in data.keys():
                setattr(self, k, data[k])
        return res


class TelegramStorage:
    __instance = None

    def __str__(self) -> str:
        return f'TelegramStorage <{self.api.hash}>'

    def __init__(self, api, files_dir):
        self.api = api
        self.files_dir = files_dir
        self.db_file = os.path.join(self.files_dir, 'data.sqlite')
        create_db = not os.path.exists(self.db_file)
        self.db = sqlite3.connect(self.db_file)
        self.db_cur = self.db.cursor()
        TelegramStorage.__instance = self

#         self.db.execute('SHOW CREATE TABLE playlist')
#         self.db.execute('DROP TABLE playlist')
#         self.db.execute(SQL.TABLE_PLAYLIST)

        if create_db:
            try:
                # self.db.execute(SQL.TABLE_PARAMS)
                self.db.execute(SQL.TABLE_PLAYLIST)
                self.db.execute(SQL.TABLE_AUDIO)
                # self.db.execute(SQL.TABLE_DOCUMENT)
#                 self.db.execute(SQL.TABLE_INFO)
            except Exception as e:
                os.remove(self.db_file)
                raise Exception(e)

    @staticmethod
    def loaded():
        return TelegramStorage.__instance

    def commit(self):
        self.db.commit()

    def select(self, table, where, limit=1):
        set_where = []
        set_values = []
        for k in where.keys():
            set_where.append(f'{k} = ?')
            set_values.append(where[k])
        set_where = ' and '.join(set_where)
        sql = f"SELECT * FROM `{table}` WHERE {set_where}"
        if limit and limit > 0:
            sql = f'{sql} LIMIT {limit}'
        cur = self.db.execute(sql, tuple(set_values))
        if limit and limit > 1:
            return cur.fetchall()
        return cur.fetchone()

    def update(self, table, data, where, limit=0):
        set_keys, set_values = self._prepare(data)
        set_where = []
        for k in where.keys():
            set_where.append(f'{k} = ?')
            set_values.append(where[k])
        set_where = ' AND '.join(set_where)
        sql = f"UPDATE `{table}` SET {set_keys} WHERE {set_where}"
        if limit and limit > 0:
            sql = f'{sql} LIMIT {limit}'
        print(sql)
        self.db_cur.execute(sql, tuple(set_values))
        result = self.db_cur.rowcount > 0
        self.db.commit()
        return result

    def insert(self, table, data):
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
        print(sql)
        self.db_cur.execute(sql, tuple(set_values))
        result = self.db_cur.rowcount > 0
        self.db.commit()
        return result

    def _prepare(self, data): # noqa
        if not data:
            return None
        set_keys = []
        set_values = []
        for k in data.keys():
            set_keys.append(f'`{k}` = ?')
            set_values.append(data[k])
        set_keys = ', '.join(set_keys)
        return set_keys, set_values

#     def update_audio(self, chat_id, message_id, data):
#         # @TODO remove ?
#         if not data:
#             return
#         set_keys = []
#         set_values = []
#         for k in data.keys():
#             set_keys.append(f'`{k}` = ?')
#             set_values.append(data[k])
#         set_keys = ', '.join(set_keys)
#         set_values.append(chat_id)
#         set_values.append(message_id)
#
#         self.db_cur.execute(
#             f"UPDATE `audio` SET {set_keys} WHERE chat_id = ? and message_id = ? LIMIT 1",
#             tuple(set_values)
#         )
#         result = self.db_cur.rowcount > 0
#         self.db.commit()
#         return result

    def get_audio(self, chat_id, message_id, convert=True):
        audio = self.db.execute(
            "SELECT * FROM `audio` WHERE chat_id = '%s' and message_id = '%s' LIMIT 1" % (chat_id, message_id))
        result = audio.fetchone()
        if result and convert:
            return TgAudio(result)
        return result

    def get_chat_audio(self, chat_id, limit=None, convert=True):
        audio = self.db.execute(
            'SELECT * FROM `audio` WHERE chat_id = %s %s' % (chat_id, ("LIMIT %i" % limit) if limit else ''))
        result = audio.fetchall()
        if result and convert:
            items = []
            for item in result:
                items.append(TgAudio(item))
            return items
        return result

    def add_audio(self, data, convert=True, commit=True):
        if not ('audio' in data['content'] and audio_content_set <= set(data['content']['audio'])):
            logger.warning('Audio message has no required keys, skipping...')
            print(data['content'])
            return
        d = {}
        content = data['content']
        audio = content['audio']
        completed = audio['audio']['remote']['is_uploading_completed']
        local = audio['audio']['local']
        d['audio_id'] = audio_id = audio['audio']['id']

        if not completed:
            logger.warning('Audio message: %d not uploaded, skipping...', audio_id)
            return

        d['chat_id'] = data['chat_id']
        d['message_id'] = data['id']
        d['date'] = data['date']
        d['mime_type'] = audio['mime_type']
        d['file_name'] = audio['file_name']
        d['artist'] = audio['performer']
        d['title'] = audio['title']
        d['duration'] = audio['duration']
        d['size'] = audio['audio']['size']
        d['local_path'] = local['path']
        d['is_downloaded'] = 1 if local['is_downloading_completed'] else 0

        self.db_cur.execute("""
            INSERT INTO `audio` (
                chat_id, message_id, mime_type, title, artist, file_name, date, size, duration,
                local_path, is_downloaded)
            VALUES (
                :chat_id, :message_id, :mime_type, :title, :artist, :file_name, :date, :size, :duration,
                :local_path, :is_downloaded)
        """ , d)

        d['id'] = self.db_cur.lastrowid
        result = d if not convert else TgAudio(d)
        if commit:
            self.db.commit()
        return result

#     def add_photo(self, data):
#         if not ('photo' in data['content'] and 'sizes' in data['content']['photo']):
#             logger.warning('Photo message content has no required keys, skipping...')
#             print(data['content'])
#             return
#
#         d = {}
#         content = data['content']
#         photo = content['photo']['sizes'][0]
#
#         d['info'] = ''
#         d['caption'] = ''
#         d['chat_id'] = data['chat_id']
#         d['message_id'] = data['id']
#         d['date'] = data['date']
#
#         if 'caption' in content and 'text' in content['caption']:
#             caption = content['caption']['text']
#             info = parse_info(caption)
#             d['info'] = json.dumps(info)
#
#         self.db_cur.execute("""
#             INSERT INTO `info` (chat_id, message_id, caption, date, info)
#             VALUES (:chat_id, :message_id, :caption, :date, :info)
#         """, d)
#
#         logger.info('Info added %d', self.db_cur.lastrowid)
#         return self.db_cur.lastrowid
