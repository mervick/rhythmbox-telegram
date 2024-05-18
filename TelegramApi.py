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
from typing import TYPE_CHECKING, Any, Dict, Optional
from telegram.client import Telegram
from telegram.utils import AsyncResult
from telegram.client import AuthorizationState
from common import MessageType, message_type_set, message_set, audio_content_set, photo_content_set, mime_types, \
    API_ERRORS, get_content_type, is_msg_valid, get_audio_type, get_chat_info, timestamp, empty_cb, cb
from TelegramStorage import TelegramStorage

# import gettext
# gettext.install('rhythmbox', RB.locale_dir())

logger = logging.getLogger(__name__)

# import logging.config
# logging.config.fileConfig('/path/to/logging.conf')
# logging.basicConfig(stream=sys.stdout, level=logging.INFO)
# logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

def inst_key(api_hash, phone):
    return '|'.join([phone.strip('+'), api_hash])


class TelegramAuthError(Exception):
    pass


class TelegramAuthStateError(Exception):
    pass


class TelegramClient(Telegram):
    error = None

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


class AsyncCb:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.update = None
        self._ready = threading.Event()

    def __str__(self) -> str:
        return f'AsyncCb <{self.id}>'

    def wait(self, timeout=None):
        result = self._ready.wait(timeout=timeout)
        if result is False:
            raise TimeoutError()

    def release(self, update):
        self.update = update
        self._ready.set()


class TelegramApi(GObject.Object):
    object = GObject.property(type=GObject.Object)
    total_count = 0
    chats = []
    chats_info = {}

    artist = ''
    artist_audio = []
    artist_document = 0

    last_message_id = 0
    state = None

    me = None
    storage = None

    __instances = {}
    __current = None

    @staticmethod
    def loaded():
        return TelegramApi.__current

    @staticmethod
    def api(api_id, api_hash, phone):

        key = inst_key(api_hash, phone)
        if key not in TelegramApi.__instances or not TelegramApi.__instances[key]:
            TelegramApi.__instances[key] = TelegramApi(int(api_id), api_hash, phone)
        TelegramApi.__current = TelegramApi.__instances[key]
        return TelegramApi.__instances[key]

    def __init__(self, api_id, api_hash, phone):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone.strip('+')
        hasher = hashlib.md5()
        hasher.update((inst_key(api_hash, phone)).encode('utf-8'))
        self.hash = hasher.hexdigest()
        plugin_dir = Gio.file_new_for_path(RB.user_data_dir()).resolve_relative_path('telegram').get_path()
        self.files_dir = os.path.join(plugin_dir, hasher.hexdigest())

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

        self.storage = TelegramStorage(self, self.files_dir)
        return self.state

    def _update_new_chat(self, update):
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
        # self.tg.add_update_handler('updateNewChat', self._update_new_chat)
        extra = 2
        while True:
            total_count = len(self.chats)
            self._load_chats_async()
            if total_count + 10 >= len(self.chats):
                if extra == 0:
                    break
                extra -= 1
        # self.tg.remove_update_handler('updateNewChat', self._update_new_chat)

    def _listen_chats(self):
        self.tg.add_update_handler('updateNewChat', self._update_new_chat)

    def _stop_chats(self):
        self.tg.remove_update_handler('updateNewChat', self._update_new_chat)

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

    def load_message_idle(self, chat_id, message_id, done=empty_cb, cancel=empty_cb):
        blob = {
            "chat_id": chat_id,
            "message_id": message_id,
            "done": done,
            "cancel": cancel,
            "result": self.tg.get_message(chat_id, message_id)
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._wait_cb, blob)

    def load_messages_idle(self, chat_id, update=None, done=None, blob=None, limit=100, offset=0):
        blob = {
            **(blob if blob else {}),
            "limit": limit,
            "offset": offset,
            "chat_id": chat_id,
            "update": update if update else empty_cb,
            "done": done if done else empty_cb
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._load_messages_idle_cb, blob)

    def _load_messages_idle_cb(self, blob):
        offset_msg_id = blob.get('offset_msg_id', 0)
        last_msg_id = blob.get('last_msg_id', 0)
        limit = blob.get('limit', 100)
        offset = blob.get('offset', 0)
        r = blob.get('result', None)

        if not r:
            r = self.tg.get_chat_history(chat_id=blob.get('chat_id'), limit=limit,
                from_message_id=offset_msg_id, offset=offset)
            blob['result'] = r
            return True

        if not r._ready.is_set():
            return True

        if not r.update or not r.update['total_count'] or not r.update['messages']:
            logger.info('tg, load messages: No messages found, exit loop')
            blob['done'](blob, 'DONE')
            return False

        msgs = r.update.get('messages', [])

        if len(msgs):
            blob['last_msg_id'] = msgs[-1]['id']

        for data in msgs:
            if is_msg_valid(data):
                msg_type = get_content_type(data)
                current_msg_id = data['id']
                if last_msg_id == current_msg_id:
                    blob['done'](blob, 'END_OF_SEGMENT')
                    return False

                if msg_type == MessageType.AUDIO:
                    logger.debug('Detect audio file')
                    d = self.storage.add_audio(data, commit=True)
                    blob['update'](d) if d else None

        blob['done'](blob, 'NEXT')
        return False

    def load_message_async(self, chat_id, message_id):
        r = self.tg.get_message(chat_id, message_id)
        r.wait()
        return r.update

    def _download_audio_async(self, data, priority=1):
        if not ('audio' in data['content'] and audio_content_set <= set(data['content']['audio'])):
            logger.warning('Audio message has no required keys, skipping...')
            print(data['content'])
            return None

        content = data['content']
        audio = content['audio']
        completed = audio['audio']['remote']['is_uploading_completed']
        audio_id = audio['audio']['id']

        if not completed:
            logger.warning('Audio message: %d not uploaded, skipping...', audio_id)
            return None

        return self.download_file_async(audio_id, priority=priority)

    def download_file_async(self, file_id, priority=1):
        r = self.tg.call_method('downloadFile', {
            'file_id': file_id,
            'priority': priority,
            # 'synchronous': False
            'synchronous': True
        })
        r.wait()
        return r.update

    def download_audio_async(self, chat_id, message_id, priority=1):
        # msg = self.load_message_async(chat_id, message_id)
        r = self.tg.get_message(chat_id, message_id)
        r.wait()
        msg = r.update
        print('== msg: %s' % msg)
        if msg:
            file = self._download_audio_async(msg, priority=priority)
            print('== file: %s' % file)
            if file:
                msg['content']['audio']['audio'] = file
                return self.storage.add_audio(msg, convert=False, commit=True)
        return None

    def download_audio_idle(self, chat_id, message_id, priority=1, done=empty_cb, cancel=empty_cb):
        update = {}

        def set_file(file):
            update['data']['content']['audio']['audio'] = file
            done(self.storage.add_audio(update['data'], convert=False, commit=True))

        def download(data):
            update['data'] = data
            self._download_audio_idle(data, priority=priority, done=set_file, cancel=cancel)

        self.load_message_idle(chat_id, message_id, done=download, cancel=cancel)

    def _download_audio_idle(self, data, priority=1, done=empty_cb, cancel=empty_cb):
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
        blob = {
            "result": self.tg.call_method('downloadFile', {
                'file_id': file_id,
                'priority': priority,
                # 'synchronous': False
                'synchronous': True
            }),
            "done": cb(done),
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._wait_cb, blob)

    def _wait_cb(self, blob):
        r = blob.get('result', None)
        if not r._ready.is_set():
            return True
        blob.get('done')(r.update)
        return False

    def _updateMe(self, update):
        pass

    def get_logged(self):
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
            }

            path = photo_big.get('local', {}).get('path')
            can_be_downloaded = photo_big.get('local', {}).get('can_be_downloaded')
            is_downloading_active = photo_big.get('local', {}).get('is_downloading_active')
            photo_id = photo_big.get('id')

            if photo_id and can_be_downloaded and not is_downloading_active:
                self.download_file(photo_id, 32)

            print(path)
        return self.me
