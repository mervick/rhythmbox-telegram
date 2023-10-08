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

import uuid
import threading
import sqlite3
import rb
from gi.repository import RB
from gi.repository import GObject, Gtk, Gdk, Gio, GLib
import os
import hashlib
from datetime import datetime
import logging
import enum
import re
import json
import telegram_sql as SQL
from typing import TYPE_CHECKING, Any, Dict, Optional
from telegram.client import Telegram
from telegram.utils import AsyncResult
from telegram.client import AuthorizationState

# import gettext
# gettext.install('rhythmbox', RB.locale_dir())

logger = logging.getLogger(__name__)

# import logging.config
# logging.config.fileConfig('/path/to/logging.conf')
# logging.basicConfig(stream=sys.stdout, level=logging.INFO)
# logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

CHAT_ID = -1001361643016

class MessageType(enum.Enum):
    NONE = None
    PHOTO = 'messagePhoto'
    DOCUMENT = 'messageDocument'
    AUDIO = 'messageAudio'

    @staticmethod
    def has(value):
        return value in message_type_set


message_type_set = set(item.value for item in MessageType)
message_set = {'id', 'chat_id', 'date', 'content'}
audio_content_set = {'mime_type', 'file_name', 'performer', 'title', 'duration', 'audio'}
photo_content_set = {'sizes'}

mime_types = {
    'audio/aac': 'aac',
    'audio/x-aac': 'aac',
    'audio/aacp': 'aac',
    'application/x-cdf': 'cda',
    'audio/midi': 'midi',
    'audio/x-midi': 'midi',
    'audio/mid': 'midi',
    'audio/mpeg': 'mp3',
    'audio/mpga': 'mpga',
    'audio/mp4': 'mp4',
    'audio/ogg': 'ogg',
    'audio/vorbis': 'ogg',
    'audio/opus': 'opus',
    'audio/wav': 'wav',
    'audio/vnd.wav': 'wav',
    'audio/3gpp': '3gp',
    'audio/3gpp2': '3g2',
    'audio/aiff': 'aiff',
    'audio/x-aiff': 'aiff',
    'audio/basic': 'au',
    'audio/l24': 'pcm',
    'audio/mp4a-latm': 'm4a',
    'audio/mpeg4-generic': 'm4a',
    'audio/x-m4a': 'm4a',
    'audio/x-m4p': 'm4a',
    'audio/x-m4b': 'm4a',
    'audio/mp4a': 'm4a'
}

API_ERRORS = {
    'FIRSTNAME_INVALID': _('The first name is invalid'),
    'LASTNAME_INVALID': _('The last name is invalid'),
    'PHONE_NUMBER_INVALID': _('The phone number is invalid'),
    'PHONE_CODE_HASH_EMPTY': _('phone_code_hash is missing'),
    'PHONE_CODE_EMPTY': _('phone_code is missing'),
    'PHONE_CODE_EXPIRED': _('The confirmation code has expired'),
    'API_ID_INVALID': _('The api_id/api_hash combination is invalid'),
    'PHONE_NUMBER_OCCUPIED': _('The phone number is already in use'),
    'PHONE_NUMBER_UNOCCUPIED': _('The phone number is not yet being used'),
    'USERS_TOO_FEW': _('Not enough users (to create a chat)'),
    'USERS_TOO_MUCH': _('The maximum number of users has been exceeded (to create a chat)'),
    'TYPE_CONSTRUCTOR_INVALID': _('The type constructor is invalid'),
    'FILE_PART_INVALID': _('The file part number is invalid'),
    'FILE_PARTS_INVALID': _('The number of file parts is invalid'),
    'MD5_CHECKSUM_INVALID': _('The MD5 checksums do not match'),
    'PHOTO_INVALID_DIMENSIONS': _('The photo dimensions are invalid'),
    'FIELD_NAME_INVALID': _('The field with the name FIELD_NAME is invalid'),
    'FIELD_NAME_EMPTY': _('The field with the name FIELD_NAME is missing'),
    'MSG_WAIT_FAILED': _('A request that must be completed before processing the current request returned an error'),
    'MSG_WAIT_TIMEOUT': _("A request that must be completed before processing the current request didn't finish processing yet"),
    'AUTH_KEY_UNREGISTERED': _('The key is not registered in the system'),
    'AUTH_KEY_INVALID': _('The key is invalid'),
    'USER_DEACTIVATED': _('The user has been deleted/deactivated'),
    'SESSION_REVOKED': _('The authorization has been invalidated, because of the user terminating all sessions'),
    'SESSION_EXPIRED': _('The authorization has expired'),
    'AUTH_KEY_PERM_EMPTY': _('The method is unavailable for temporary authorization key, not bound to permanent'),
}


def get_content_type(data):
    if '@type' in data['content'] and MessageType.has(data['content']['@type']):
        return MessageType(data['content']['@type'])
    return MessageType.NONE

def is_msg_valid(data):
    return message_set <= set(data)

def parse_title(content):
    title = [None, content]
    r = re.search("^\s*([^\n]+?)\s\-\s([^\n]+)\n?", content)
    if not r:
        r = re.search("^\s*([^\n]+?)\-([^\n]+)\n?", content)
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
        info["genre"] = r.group()[0].strip()
    r = re.search("country:\s*([^\n]*)\n", content, re.IGNORECASE)
    if r:
        info["country"] = r.group()[0].strip()
    return info

def get_audio_type(mime_type):
    if mime_type in mime_types.keys():
        return mime_types[mime_type]
    mime = mime_type.split('/', 2)
    return mime[1] if len(mime) > 1 else mime_type

def get_chat_info(chat):
    # photo = chat['photo'] if 'photo' in chat else {"minithumbnail": None}
    # last_message = chat['last_message'] if 'last_message' in chat else {"content": None}

    return {
        'id': chat['id'],
        'title': chat['title'],
        # 'photo': photo['minithumbnail'],
        # 'photo': None,
        # 'content': last_message['content'],
        # 'content': None,
    }

def timestamp():
    return datetime.timestamp(datetime.now())


class TelegramAuthError(Exception):
    pass

class TelegramAuthStateError(Exception):
    pass

class TelegramClient(Telegram):
    error = None
    # def __init__(self, *args, **kwargs):
    #     super(Telegram, self).__init__(*args, **kwargs)
    #     self.error = None

    def _wait_authorization_result(self, result: AsyncResult) -> AuthorizationState:
        authorization_state = None

        if result:
            result.wait(raise_exc=False)

            if result.error:
                self.error = result.error_info
                raise TelegramAuthError(f'Telegram error: {result.error_info}')

            if result.update is None:
                raise RuntimeError('Something wrong, the result update is None')

            if result.id == 'getAuthorizationState':
                authorization_state = result.update['@type']
            else:
                authorization_state = result.update['authorization_state']['@type']

        return AuthorizationState(authorization_state)


def inst_key(api_hash, phone):
    return '|'.join([phone.strip('+'), api_hash])

class SyncResult:
    def __init__(self, result):
        self._r = result
        self.ok_received = False
        self.error = False
        self.error_info: Optional[Dict[Any, Any]] = None
        self.update: Optional[Dict[Any, Any]] = None

    def is_ready(self):
        ready = self._r._ready.is_set()
        if ready:
            self.ok_received = self._r.ok_received
            self.error = self._r.error
            self.error_info = self._r.error_info
            self.update = self._r.update
        return ready

def empty_cb(*args, **kwargs):
    pass

def cb(fn):
    return fn if fn else empty_cb

class AsyncCb:
    def __init__(self, result_id=None):
        self.id = result_id if result_id else uuid.uuid4().hex
        self.update = None
        self._ready = threading.Event()

    def __str__(self) -> str:
        return f'AsyncCall <{self.id}>'

    def wait(self, timeout=None):
        result = self._ready.wait(timeout=timeout)
        if result is False:
            raise TimeoutError()

    def set(self, update):
        print('cb.set')
        self.update = update
        self._ready.set()

class TgAudio:
    def __init__(self, api, data):
        self._api = api
        self._data = data
        self.update(data)

    def update(self, data):
        if type(data) == tuple:
            id_, chat_id, message_id, audio_id, mime_type, title, artist, file_name, date, size, duration, \
                is_downloaded, is_moved, is_hidden, local_path, document_id, info_id = data
            self.id = id_
            self.chat_id = chat_id
            self.message_id = message_id
            self.audio_id = audio_id
            self.mime_type = mime_type
            self.title = title
            self.artist = artist
            self.file_name = file_name
            self.date = date
            self.size = size
            self.duration = duration
            self.is_downloaded = is_downloaded
            self.is_moved = is_moved
            self.is_hidden = is_hidden
            self.local_path = local_path
            self.document_id = document_id
            self.info_id = info_id
        else:
            self.id = data['id']
            self.chat_id = data['chat_id']
            self.message_id = data['message_id']
            self.audio_id = data['audio_id'] if data['audio_id'] else None
            self.mime_type = data['mime_type']
            self.title = data['title']
            self.artist = data['artist']
            self.file_name = data['file_name']
            self.date = data['date']
            self.size = data['size']
            self.duration = data['duration']
            self.is_downloaded = data.get('is_downloaded', False)
            self.is_moved = data.get('is_moved', False)
            self.is_hidden = data.get('is_hidden', False)
            self.local_path = data.get('local_path')
            self.document_id = data.get('local_path')
            self.info_id = data.get('info_id')

    def get_path(self, priority=1, wait=True, done=empty_cb):
        print('get_path')
        if not self.is_downloaded:
            print('not is_downloaded')
            if wait:
                call = AsyncCb(f'tg_audio_{self.id}')
                print('create AsyncCb')
                TelegramApi.loaded().download_audio_idle(self.chat_id, self.message_id, priority=priority, done=call.set)
                print('start download_audio_idle')
                call.wait()
                print('call wait')
                self.update(call.update)
                print('call update')
            else:
                def on_done(data):
                    print('=========done========')
                    print(data)
                    # update = TelegramApi.loaded().add_audio(data, convert=False)
                    self.update(data)
                    done(self)

                TelegramApi.loaded().download_audio_idle(self.chat_id, self.message_id, priority=priority, done=on_done)
                return None

        return self.local_path

    def __str__(self) -> str:
        return f'TgAudio <{self._data}>'


class TelegramApi:
    total_count = 0
    chats = []
    chats_info = {}

    artist = ''
    artist_audio = []
    artist_document = 0

    last_message_id = 0
    first_message_id = 0
    state = None

    __instances = {}
    __instance = None

    me = None

    # _updater = None
    # _update = False

    # @staticmethod
    # def get_instance():
    #     return get_instance()
    #
    # @staticmethod
    # def api(api_id, api_hash, phone):
    #     __instance = None
    #     api_id = int(api_id)
    #     if not __instance:
    #         __instance = TelegramApi(api_id, api_hash, phone)
    #     elif __instance.api_id != api_id or __instance.api_hash != api_hash or __instance.phone != phone:
    #         __instance.stop()
    #         __instance = TelegramApi(api_id, api_hash, phone)
    #     return __instance

    @staticmethod
    def loaded():
        return TelegramApi.__instance

    @staticmethod
    def api(api_id, api_hash, phone):

        key = inst_key(api_hash, phone)
        if key not in TelegramApi.__instances or not TelegramApi.__instances[key]:
            TelegramApi.__instances[key] = TelegramApi(int(api_id), api_hash, phone)
        # elif __instance.api_id != api_id or __instance.api_hash != api_hash or __instance.phone != phone:
        #     __instance.stop()
        # __instance = TelegramApi(api_id, api_hash, phone)
        TelegramApi.__instance = TelegramApi.__instances[key]
        return TelegramApi.__instances[key]

    def __init__(self, api_id, api_hash, phone):
        # print('==========================================================================================')
        # print('INIT TG %s, %s, %s' % (api_id, api_hash, phone))
        # print('==========================================================================================')
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone.strip('+')

        # plugin_dir = Gio.file_new_for_path(RB.user_data_dir()).resolve_relative_path('telegram')
        files_dir = Gio.file_new_for_path(RB.user_data_dir()).resolve_relative_path('telegram').get_path()
        # files_dir = os.path.join(plugin_dir, 'tdlib_files')
        # files_dir = '/home/izman/.tdlib_files/'

        hasher = hashlib.md5()
        hasher.update((inst_key(api_hash, phone)).encode('utf-8'))
        self.files_dir = os.path.join(files_dir, hasher.hexdigest())

        print('================FILES_DIR================')
        print(self.files_dir)

        self.tg = TelegramClient(
            api_id=self.api_id,
            api_hash=self.api_hash,
            phone=self.phone,
            database_encryption_key=self.api_hash,
            files_directory=self.files_dir,
        )

    def get_error(self):
        err = self.tg.error['message'] if self.tg.error and 'message' in self.tg.error else None
        return API_ERRORS[err] if err in API_ERRORS else err

    def is_ready(self):
        return self.state == AuthorizationState.READY

    def login(self, code=None):
        if code and self.state == self.tg.authorization_state.WAIT_CODE:
            self.tg.send_code(code=code)

        self.state = self.tg.login(blocking=False)

        if self.state != self.tg.authorization_state.READY:
            raise TelegramAuthStateError(self.state)

        self.db_file = os.path.join(self.files_dir, 'data.sqlite')
        create_db = not os.path.exists(self.db_file)
        self.db = sqlite3.connect(self.db_file)
        self.db_cur = self.db.cursor()

        if create_db:
            try:
                self.db.execute(SQL.TABLE_PARAMS)
                self.db.execute(SQL.TABLE_PLAYLIST)
                self.db.execute(SQL.TABLE_AUDIO)
                self.db.execute(SQL.TABLE_DOCUMENT)
                self.db.execute(SQL.TABLE_INFO)
            except Exception as e:
                os.remove(self.db_file)
                raise Exception(e)

        return self.state

    def add_audio(self, data, convert=True, commit=True):
        print('============add_audio===========')
        print(data)
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

        print('=========EXECUTE INSERT AUDIO========')
        self.db_cur.execute("""
            INSERT INTO `audio` (
                chat_id, message_id, audio_id, mime_type, title, artist, file_name, date, size, duration, 
                local_path, is_downloaded) 
            VALUES (
                :chat_id, :message_id, :audio_id, :mime_type, :title, :artist, :file_name, :date, :size, :duration, 
                :local_path, :is_downloaded)
        """, d)

        # logger.info('Audio added %d', self.db_cur.lastrowid)
        print('Audio added %d', self.db_cur.lastrowid)
        d['id'] = self.db_cur.lastrowid
        print(d)
        result = d if not convert else TgAudio(self, d)
        if commit:
            self.db.commit()
        return result

    def add_photo(self, data):
        if not ('photo' in data['content'] and 'sizes' in data['content']['photo']):
            logger.warning('Photo message content has no required keys, skipping...')
            print(data['content'])
            return

        d = {}
        content = data['content']
        photo = content['photo']['sizes'][0]

        d['info'] = ''
        d['caption'] = ''
        d['chat_id'] = data['chat_id']
        d['message_id'] = data['id']
        d['date'] = data['date']

        if 'caption' in content and 'text' in content['caption']:
            caption = content['caption']['text']
            info = parse_info(caption)
            d['info'] = json.dumps(info)

        d['photo_id'] = photo['photo']['id']

        self.db_cur.execute("""
            INSERT INTO `audio` (chat_id, message_id, audio_id, mime_type, title, artist, file_name, date, size, duration) 
            VALUES (:chat_id, :message_id, :audio_id, :mime_type, :title, :artist, :file_name, :date, :size, :duration)
        """, d)

        logger.info('Audio added %d', self.db_cur.lastrowid)
        return self.db_cur.lastrowid

    def _updateNewChat(self, update):
        if 'chat' in update and 'id' in update['chat']:
            chat_id = update['chat']['id']
            self.chats.append(chat_id)
            self.chats_info[chat_id] = get_chat_info(update['chat'])
            # if self._update and self._updater:
            #     self._updater(self.chats_info)

    def _load_chats_async(self):
        r = self.tg.call_method('loadChats', {
            'limit': 100,
        })
        r.wait()

    def _load_chats(self):
        # self.tg.add_update_handler('updateNewChat', self._updateNewChat)
        extra = 2
        while True:
            total_count = len(self.chats)
            self._load_chats_async()
            if total_count + 10 >= len(self.chats):
                if extra == 0:
                    break
                extra -= 1
        # self.tg.remove_update_handler('updateNewChat', self._updateNewChat)

    def _listen_chats(self):
        self.tg.add_update_handler('updateNewChat', self._updateNewChat)

    def _stop_chats(self):
        self.tg.remove_update_handler('updateNewChat', self._updateNewChat)

    def _get_chats_async(self):
        r = self.tg.get_chats(
            limit=100
        )
        r.wait()

        if not r.update or not r.update['total_count']:
            return 0

        self.chats = r.update['chat_ids']
        return r.update['total_count']

    def _load_chats_info_async(self):
        self.chats_info = {}
        for chat_id in self.chats:
            r = self.tg.get_chat(chat_id)
            r.wait()
            if not r.update or not r.update['@type']:
                raise Exception('Cannot load chat info')
            if r.update['id'] != chat_id:
                raise Exception('Invalid chat id')

            self.chats_info[chat_id] = get_chat_info(r.update)

    def get_chats_async(self, updater=None, refresh=False):
        if not self.chats or refresh:
            self._listen_chats()
            self._get_chats_async()
            self._load_chats_info_async()
            self._load_chats()
            self._stop_chats()
        return self.chats_info

    def _get_joined_chats(self):
        chats = dict()
        for k in self.chats_info.keys():
            if k in self.chats:
                chats[k] = self.chats_info[k]
        return chats

    def _chats_idle_cb(self, data):
        step = data.get("step", 0)
        # print('== STEP %d' % step)

        # start, reset chats, listen, get chats
        if step == 0:
            self.chats = []
            self.chats_info = {}
            self._listen_chats()
            self._get_chats_async()
            data["step"] = 1

        # load chats info
        elif step == 1:
            idx = data.get("idx", 0)
            while idx < len(self.chats) and self.chats[idx] in self.chats_info:
                # print('== skip chat_id %s' % self.chats[idx])
                idx += 1
            if idx < len(self.chats):
                # print('== load chat_id %s' % self.chats[idx])
                chat_id = self.chats[idx]
                r = self.tg.get_chat(chat_id)
                r.wait()
                self.chats_info[chat_id] = get_chat_info(r.update)
                data["idx"] = idx + 1
            else:
                data["step"] = 2

        # load chats
        elif step == 2:
            total_count = len(self.chats)
            self._load_chats_async()
            print('== %d %d %d' % (total_count, len(self.chats), len(self.chats_info.keys())))
            if total_count >= len(self.chats):
                data["idx"] = data.get('idx', 0) + 1
                if data["idx"] > 3:
                    data["step"] = 3
                    self.total_count = total_count

        # callback, stop
        else:
            self._stop_chats()
            data["update"](self._get_joined_chats())
            return False
        return True

    def reset_chats(self):
        self.total_count = 0
        self.chats = []
        self.chats_info = {}

    def get_chats_idle(self, update):
        if not self.chats:
            Gdk.threads_add_idle(0, self._chats_idle_cb, {"update": update})
            return
        update(self._get_joined_chats())

    # def get_chats(self, on_update, refresh=False):
    #     if not self.chats or refresh:
    #         self.chats = []
    #         self.total_count = 0
    #         self._parsed_count = 0
    #         page = 1
    #         limit = 100
    #         self._last_cnt = 0
    #         self._ts1 = 0
    #
    #         # def _timer():
    #         #     print('@@@@@@@@@@@@@@@_timer')
    #         #     cnt = self._parsed_count
    #         #     ts2 = timestamp()
    #         #
    #         #     if ts2 - self._ts1 < 0.5:
    #         #         return
    #         #     self._ts1 = ts2
    #         #
    #         #     def fn():
    #         #         print('@@@@@@@@@@@@@@@fn')
    #         #         if cnt == self._parsed_count and self._parsed_count < self.total_count and self._last_cnt != cnt:
    #         #             self._last_cnt = cnt
    #         #             _load_chats()
    #         #         else:
    #         #             _done()
    #         #
    #         #     GLib.timeout_add(200, fn)
    #
    #         def _handle_count(update):
    #             print('@@@@@@@@@@@@@@@_handle_count')
    #             if 'total_count' in update and 'chat_list' in update and update['chat_list']['@type'] == 'chatListMain':
    #                 self.total_count = update['total_count']
    #                 on_update(self.chats_info, self.total_count)
    #
    #         def _handle_chat(update):
    #             print('@@@@@@@@@@@@@@@_handle_chat')
    #             chat = get_chat_info(update['chat'])
    #             self.chats_info[chat['id']] = chat
    #             self._parsed_count += 1
    #             if len(self.chats_info.keys()) % limit - 1 == 0:
    #                 _load_chats()
    #             # _timer()
    #             on_update(self.chats_info, self.total_count)
    #
    #         def _handle_main(update):
    #             print('@@@@@@@@@@@@@@@_handle_main')
    #             if update and update['total_count']:
    #                 self.chats = update['chat_ids']
    #                 print('[[[[_handle_main]]]]')
    #                 self.total_count = update['total_count']
    #                 # self.tg.remove_update_handler('getChats', _handle_main)
    #                 # self.tg.remove_update_handler('chats', _handle_main)
    #                 on_update(self.chats_info, self.total_count)
    #                 _load_chats()
    #                 _load_info()
    #
    #         def _next_chat():
    #             print('@@@@@@@@@@@@@@@_next_chat')
    #             ids = list(set(self.chats) - set(self.chats_info.keys()))
    #             print('_______________IDS__ %s' % ids)
    #             if ids:
    #                 return ids[0]
    #             return None
    #
    #         def _load_info():
    #             print('@@@@@@@@@@@@@@@_load_info %d %d %d' % (list(set(self.chats), self._parsed_count, self.total_count)))
    #             if self._parsed_count < self.total_count:
    #                 chat_id = _next_chat()
    #                 if id:
    #                     self.tg.get_chat(chat_id)
    #                 GLib.timeout_add(100, _load_info)
    #
    #         def _load_chats():
    #             print('@@@@@@@@@@@@@@@_load_chats')
    #             self.tg.call_method('loadChats', {
    #                 'limit': limit,
    #             })
    #
    #         def _done():
    #             print('@@@@@@@@@@@@@@@_done')
    #             self.tg.remove_update_handler('updateUnreadChatCount', _handle_count)
    #             self.tg.remove_update_handler('updateNewChat', _handle_chat)
    #             self.tg.remove_update_handler('getChat', _handle_chat)
    #             self.tg.remove_update_handler('chat', _handle_chat)
    #             self.tg.remove_update_handler('getChats', _handle_main)
    #             self.tg.remove_update_handler('chats', _handle_main)
    #             on_update(self.chats_info, self.total_count, True)
    #
    #         self.tg.add_update_handler('updateUnreadChatCount', _handle_count)
    #         self.tg.add_update_handler('updateNewChat', _handle_chat)
    #         self.tg.add_update_handler('getChat', _handle_chat)
    #         self.tg.add_update_handler('chat', _handle_chat)
    #         self.tg.add_update_handler('getChats', _handle_main)
    #         self.tg.add_update_handler('chats', _handle_main)
    #
    #         print('@@@@@@@@@@@@@@@_start')
    #         self.tg.get_chats(
    #             limit=limit
    #         )
    #         return _done
    #
    # def get_chats1(self, on_update, on_done, refresh=False):
    #     if not self.chats or refresh:
    #         self.total_count = 0
    #         page = 1
    #         limit = 100
    #
    #         def _remove_handlers():
    #             self.tg.remove_update_handler('updateUnreadChatCount', _set_total_count)
    #             self.tg.remove_update_handler('updateNewChat', _set_chat)
    #             self.tg.remove_update_handler('getChat', _set_chat)
    #             on_done()
    #
    #         def _load_chats_info():
    #             sz = page * limit
    #             rsz = len(self.chats_info.keys())
    #             if self.total_count > sz and rsz >= sz:
    #                 r = self.tg.call_method('loadChats', {
    #                     'limit': limit,
    #                 })
    #                 page += 1
    #             elif rsz >= sz:
    #                 _remove_handlers()
    #
    #         def _set_chat(update):
    #             print('=============_set_chat================')
    #             if not update or not update['@type']:
    #                 return
    #             print('=============UPDATE.%s================' % update['@type'])
    #             print(update)
    #             chat = get_chat_info(update['chat'])
    #             self.chats_info[chat['id']] = chat
    #             on_update(self.chats_info, self.total_count)
    #             _load_next()
    #             _load_chats_info()
    #
    #         def _load_chat_info(chat_id):
    #             self.tg.get_chat(chat_id)
    #
    #         def _load_next():
    #             if load_info:
    #                 ids = list(set(self.chats) - set(self.chats_info.keys()))
    #                 if ids:
    #                     _load_chat_info(ids[0])
    #
    #         def _set_chats(update):
    #             if not update or not update['@type']:
    #                 return
    #             print('=============UPDATE.%s================' % update['@type'])
    #             if update and update['total_count']:
    #                 self.chats = update['chat_ids']
    #                 print('=============_set_chats %d================' % len(self.chats))
    #                 self.total_count = update['total_count']
    #                 self.tg.remove_update_handler('getChats', _set_chats)
    #                 self.tg.remove_update_handler('chats', _set_chats)
    #                 on_update(self.chats_info, self.total_count)
    #                 load_info = True
    #                 _load_next()
    #                 # _load_chats_info()
    #             else:  # @TODO ?
    #                 pass
    #
    #         def _set_total_count(update):
    #             if 'total_count' in update and 'chat_list' in update and update['chat_list']['@type'] == 'chatListMain':
    #                 self.total_count = update['total_count']
    #                 on_update(self.chats_info, self.total_count)
    #
    #         self.tg.add_update_handler('updateUnreadChatCount', _set_total_count)
    #         self.tg.add_update_handler('updateNewChat', _set_chat)
    #         self.tg.add_update_handler('getChat', _set_chat)
    #         self.tg.add_update_handler('getChats', _set_chats)
    #         self.tg.add_update_handler('chats', _set_chats)
    #
    #         self.tg.get_chats(
    #             limit=limit
    #         )

    def get_messages(self, chat_id):
        msg_id = 0
        last_timestamp = 0

        # while True:
        for i in range(0, 5):
            # last_date = '' if last_timestamp == 0 else str(datetime.fromtimestamp(last_timestamp))
            r = self.tg.get_chat_history(chat_id, 50, msg_id)
            r.wait()
            # print(r.update)
            if not r.update or not r.update['total_count']:
                print('not messages')
                break
            msgs = r.update['messages']
            msg_id = msgs[-1]['id']
            # last_timestamp = msgs[-1]['date']
            print(msgs)

        # print(msg_id)

    def get_chat_audio(self, chat_id, limit=None, convert=True):
        audio = self.db.execute(
            'SELECT * FROM `audio` WHERE chat_id = %s %s' % (chat_id, ("LIMIT %i" % limit) if limit else ''))
        result = audio.fetchall()
        if result and convert:
            items = []
            for item in result:
                items.append(TgAudio(self, item))
            return items
        return result

    def get_audio(self, chat_id, message_id, convert=True):
        audio = self.db.execute(
            "SELECT * FROM `audio` WHERE chat_id = '%s' and message_id = '%s' LIMIT 1" % (chat_id, message_id))
        result = audio.fetchone()
        if result and convert:
            return TgAudio(self, result)
        return result

    def get_any_audio(self):
        audio = self.db.execute('SELECT * FROM `audio` WHERE 1=1')
        return audio.fetchall()
        # return audio

    # @TODO
    def load_messages(self):
        exit_loop = False
        offset_msg_id = 0
        first_message_id = 0

        # while True:
        for i in range(0, 5):
            r = self.tg.get_chat_history(CHAT_ID, 50, offset_msg_id)
            r.wait()
            if not r.update or not r.update['total_count']:
                logger.info('No messages found, exit loop')
                break
            msgs = r.update['messages']
            if offset_msg_id == 0:
                first_message_id = msgs[0]['id']
            offset_msg_id = msgs[-1]['id']

            for data in msgs:
                if is_msg_valid(data):
                    msg_type = get_content_type(data)
                    if msg_type == MessageType.AUDIO:
                        current_msg_id = data['id']
                        if self.first_message_id == current_msg_id:
                            exit_loop = True
                            break
                        logger.debug('Detect audio file')
                        self.add_audio(data, commit=False)
                        # self.last_message_id = current_msg_id
            self.db.commit()
            if exit_loop:
                self.first_message_id = first_message_id
                break

    def load_message_idle(self, chat_id, message_id, done=empty_cb, cancel=empty_cb):
        print('load_message_idle')
        glob = {
            "chat_id": chat_id,
            "message_id": message_id,
            "done": done,
            "cancel": cancel,
            "result": self.tg.get_message(chat_id, message_id)
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._wait_cb, glob)

    def load_messages_idle(self, chat_id, update=None, done=None):
        glob = {
            "chat_id": chat_id,
            "update": update if done else empty_cb,
            "done": done if done else empty_cb
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._load_messages_idle_cb, glob)

    def _load_messages_idle_cb(self, glob):
        offset_msg_id = glob.get('offset_msg_id', 0)
        r = glob.get('result', None)

        if not r:
            r = self.tg.get_chat_history(glob.get('chat_id'), 100, offset_msg_id)
            glob['result'] = r
            return True

        if not r._ready.is_set():
            return True

        if not r.update or not r.update['total_count']:
            logger.info('tg, load messages: No messages found, exit loop')
            glob['done']()
            return False

        first_message_id = glob.get('first_message_id', 0)
        msgs = r.update['messages']

        if len(msgs):
            if offset_msg_id == 0:
                glob['first_message_id'] = msgs[0]['id']
            glob['offset_msg_id'] = msgs[-1]['id']

        for data in msgs:
            if is_msg_valid(data):
                msg_type = get_content_type(data)
                current_msg_id = data['id']
                if first_message_id == current_msg_id:
                    self.db.commit()
                    glob['done']()
                    return False

                if msg_type == MessageType.AUDIO:
                    logger.debug('Detect audio file')
                    d = self.add_audio(data, commit=False)
                    glob['update'](d) if d else None

        self.db.commit()

        i = glob.get('iter', 0)
        i = i + 1

        if i < 5:
            glob['result'] = None
            glob['iter'] = i
            return True

        glob['done']()
        print('================= load_messages DONE ===============')
        return False

    def download_audio_idle(self, chat_id, message_id, priority=1, done=empty_cb, cancel=empty_cb):
        print('download_audio_idle')
        update = {}

        def set_file(file):
            print('---------SET_FILE--------------')
            print(file)

            update['data']['content']['audio']['audio'] = file
            done(self.add_audio(update['data'], convert=False, commit=True))

        def download(data):
            print('---------DOWNLOAD_AUDIO--------------')
            print(data)

            update['data'] = data
            self._download_audio_idle(data, priority=priority, done=set_file, cancel=cancel)

        self.load_message_idle(chat_id, message_id, done=download, cancel=cancel)

    def _download_audio_idle(self, data, priority=1, done=empty_cb, cancel=empty_cb):
        print('_download_audio_idle')
        if not ('audio' in data['content'] and audio_content_set <= set(data['content']['audio'])):
            logger.warning('Audio message has no required keys, skipping...')
            print(data['content'])
            cancel()
            return

        content = data['content']
        audio = content['audio']
        completed = audio['audio']['remote']['is_uploading_completed']
        audio_id = audio['audio']['id']

        if not completed:
            logger.warning('Audio message: %d not uploaded, skipping...', audio_id)
            cancel()
            return

        self.download_file_idle(audio_id, priority=priority, done=done)

    def download_file_idle(self, file_id, priority=1, done=None):
        print('download_file_idle')
        glob = {
            "result": self.tg.call_method('downloadFile', {
                'file_id': file_id,
                'priority': priority,
                # 'synchronous': False
                'synchronous': True
            }),
            "done": cb(done),
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._wait_cb, glob)

    def _wait_cb(self, glob):
        r = glob.get('result', None)

        if not r._ready.is_set():
            return True

        glob.get('done')(r.update)
        return False

    def _updateMe(self, update):
        pass

    def get_logged(self):
        # self.tg.add_update_handler('updateUser', self._updateMe)
        # self.tg.add_update_handler('user', self._updateMe)
        r = self.tg.get_me()
        r.wait()

        if r.update and '@type' in r.update:
            user = r.update
            photo_big = user.get('profile_photo', {}).get('big')
            self.me = {
                'id': user.get('id'),
                'first_name': user.get('first_name'),
                'last_name': user.get('last_name'),
                'username': user.get('usernames', {}).get('editable_username'),
                'phone_number': user.get('phone_number'),
                'profile_photo': user.get('profile_photo', {}),
                # 'id': user.get('id'),
            }

            path = photo_big.get('local', {}).get('path')
            can_be_downloaded = photo_big.get('local', {}).get('can_be_downloaded')
            is_downloading_active = photo_big.get('local', {}).get('is_downloading_active')
            photo_id = photo_big.get('id')

            if photo_id and can_be_downloaded and not is_downloading_active:
                self.download_file(photo_id, 32)

            print(path)
        return self.me

    # def stop(self):
    #     global __instance
    #     __instance = None
    #     self.tg.stop()


# TelegramApi.api = get_api

