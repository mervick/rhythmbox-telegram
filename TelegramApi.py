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

import uuid, re
import threading
from gi.repository import RB
from gi.repository import GObject, Gdk, Gio, GLib
import hashlib
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
from telegram.client import Telegram
from telegram.utils import AsyncResult
from telegram.client import AuthorizationState
from common import MessageType, audio_content_set, API_ERRORS, get_content_type, is_msg_valid
from common import get_chat_info, empty_cb, cb, show_error
from TelegramStorage import TelegramStorage, TgCache

logger = logging.getLogger(__name__)

REGEX_TME_LINK = re.compile('^https://t\.me/(c/)?([a-zA-Z0-9_]+)/([0-9]+)(\?.+)?$')

def inst_key(api_hash, phone):
    return '|'.join([phone.strip('+'), api_hash])


class TelegramAuthError(Exception):
    def __init__(self, message, info):
        super().__init__(message)
        self.info = info

    def get_info(self):
        if self.info is not None:
            if type(self.info) == dict:
                return self.info.get('message', self.__str__())
        return self.__str__()


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
                raise TelegramAuthError(f'Telegram error: {result.error_info}', info=result.error_info)

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

    _is_listen_chats = False
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
        self.hash = hasher.hexdigest()[0:10]
        plugin_dir = Gio.file_new_for_path(RB.user_data_dir()).resolve_relative_path('telegram').get_path()
        self.files_dir = os.path.join(plugin_dir, hasher.hexdigest())
        self.temp_dir = os.path.join(self.files_dir, 'files')

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
        if self.state:
            self.start_update_chats()
        else:
            self.stop_update_chats()
        return self.state

    def _update_new_chat_cb(self, update):
        if 'chat' in update and 'id' in update['chat']:
            chat_id = update['chat']['id']
            self.chats.append(chat_id)
            self.chats_info[chat_id] = get_chat_info(update['chat'])
            # if self._update and self._updater:
            #     self._updater(self.chats_info)

    def start_update_chats(self):
        if not self._is_listen_chats:
            self._is_listen_chats = True
            self.tg.add_update_handler('updateNewChat', self._update_new_chat_cb)

    def stop_update_chats(self):
        self.tg.remove_update_handler('updateNewChat', self._update_new_chat_cb)

    def _get_joined_chats(self):
        chats = dict()
        # cache = TgCache(TgCache.KEY_CHANNELS)
        # if cache.get() is not None:
        #     chats = cache.get()
        for k in self.chats_info.keys():
            if k in self.chats:
                chats[k] = self.chats_info[k]
        # cache.set(chats)
        return chats

    def _chats_idle_cb(self, data):
        step = data.get("step", 0)
        r = data.get("result", None)

        # Step 0. Get first 100 chat ids
        if step == 0:
            # no result, call tg.get_chats
            if not r:
                # max limit is 100
                data['result']  = self.tg.get_chats(limit=100)
                return True
            # wait to load
            if not r._ready.is_set():
                return True
            data['result'] = None
            # save chats ids
            for chat_id in r.update['chat_ids']:
                if chat_id not in self.chats:
                    self.chats.append(chat_id)
            # next step
            data["step"] = 1

        # Step 1. Loading chats info by ids
        elif step == 1:
            idx = data.get("idx", 0)
            # no result, call get_chat by id
            if not r:
                # get idx of not loaded chat
                while idx < len(self.chats) and self.chats[idx] in self.chats_info:
                    idx += 1
                if idx < len(self.chats):
                    chat_id = self.chats[idx]
                    print('get_chat %s' % chat_id)
                    data['result'] = self.tg.get_chat(chat_id)
                else:
                    # all chats loaded, move to next step
                    data['result'] = None
                    data["step"] = 2
                return True
            # wait to load
            if not r._ready.is_set():
                return True
            data['result'] = None
            # save chat info, increment idx
            chat_id = self.chats[idx]
            self.chats_info[chat_id] = get_chat_info(r.update)
            data["idx"] = idx + 1

        # Step 2. Load chats
        elif step == 2:
            # no result, call loadChats
            if not r:
                # max limit is 100
                data['result'] = self.tg.call_method('loadChats', {'limit': 100})
                return True
            # wait to load
            if not r._ready.is_set():
                return True
            data['result'] = None
            data["idc"] = data.get('idc', 0) + 1
            # call loadChats 4 times (> 400 chats?)
            if data["idc"] >= 4:
                # save total_count
                self.total_count = len(self.chats)
                # next step
                data["step"] = 3

        # All chats loaded, callback
        else:
            data["update"](self._get_joined_chats())
            return False
        return True

    def reset_chats(self):
        cache = TgCache(TgCache.KEY_CHANNELS)
        cache.set({})
        self.total_count = 0
        self.chats = []
        self.chats_info = {}

    def get_chats_idle(self, update):
        Gdk.threads_add_idle(0, self._chats_idle_cb, {"update": update})

    def load_message_idle(self, chat_id, message_id, done=empty_cb, cancel=empty_cb):
        logger.debug('%s %s %s %s' % (chat_id, message_id, done, cancel))
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
            logger.debug('tg, load messages: No messages found, exit loop')
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
                    d = self.storage.add_audio(data)
                    blob['update'](d) if d else None

        blob['done'](blob, 'NEXT')
        return False

    def _download_audio_async(self, data, priority=1):
        if not ('audio' in data['content'] and audio_content_set <= set(data['content']['audio'])):
            logger.debug('Audio message has no required keys, skipping...')
            logger.debug(data.get('content'))
            return None

        content = data['content']
        audio = content['audio']
        completed = audio['audio']['remote']['is_uploading_completed']
        audio_id = audio['audio']['id']

        if not completed:
            logger.debug('Audio message: %d not uploaded, skipping...', audio_id)
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

    def get_message_link(self, chat_id, message_id):
        r = self.tg.call_method('getMessageLink', {
            'chat_id': int(chat_id),
            'message_id': int(message_id),
            "for_album": False,
            "for_group": False
        })
        r.wait()
        return r.update['link'] if 'link' in r.update else None

    def get_message_direct_link(self, chat_id, message_id):
        link = self.get_message_link(chat_id, message_id)
        m = REGEX_TME_LINK.match(link)
        if not m:
            return link
        # private
        if m.group(1):
            return "tg://privatepost?channel=%s&post=%s&single" % (m.group(2), m.group(3))
        # public
        return "tg://resolve?domain=%s&post=%s&single" % (m.group(2), m.group(3))

    def download_audio(self, chat_id, message_id, priority=1):
        r = self.tg.get_message(chat_id, message_id)
        r.wait()
        msg = r.update
        if msg:
            file = self._download_audio_async(msg, priority=priority)
            if file:
                msg['content']['audio']['audio'] = file
                return msg
        return None

    def download_audio_idle(self, chat_id, message_id, priority=1, done=empty_cb, cancel=empty_cb):
        update = {}

        def set_file(file):
            update['data']['content']['audio']['audio'] = file
            done(self.storage.add_audio(update['data'], convert=False))

        def download(data):
            if not data:
                cancel()
                return
            update['data'] = data
            self._download_audio_idle_cb(data, priority=priority, done=set_file, cancel=cancel)

        self.load_message_idle(chat_id, message_id, done=download, cancel=cancel)

    def _download_audio_idle_cb(self, data, priority=1, done=empty_cb, cancel=empty_cb):
        if not ('audio' in data['content'] and audio_content_set <= set(data['content']['audio'])):
            logger.warning('Audio message has no required keys, skipping...')
            logger.debug(data.get('content'))
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

        self.download_file_idle(audio_id, priority=priority, done=done, cancel=cancel)

    def download_file_idle(self, file_id, priority=1, done=empty_cb, cancel=empty_cb):
        logger.debug('download_file_idle')
        blob = {
            "result": self.tg.call_method('downloadFile', {
                'file_id': file_id,
                'priority': priority,
                # 'synchronous': False
                'synchronous': True
            }),
            "done": cb(done),
            "cancel": cb(cancel)
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._wait_cb, blob)

    def _wait_cb(self, blob):
        r = blob.get('result', None)
        if not r.ok_received and r.error:
            show_error(_('Error: Telegram API request failed'), format_error(r))
            cb(blob.get('cancel'))()
            return False

        if not r._ready.is_set():
            return True

        blob.get('done')(r.update)
        return False


def format_error(r: AsyncResult):
    message = None
    info = r.error_info
    if info:
        if 'message' in info:
            message = info.get('message')
            if '@extra' in info:
                if 'request_id' in info['@extra']:
                    message = '%s, request_id: %s' % (message, info['@extra'].get('request_id'))
    return message
