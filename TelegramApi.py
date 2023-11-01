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
from telegram_fn import MessageType, message_type_set, message_set, audio_content_set, photo_content_set, mime_types, \
    API_ERRORS, get_content_type, is_msg_valid, get_audio_type, get_chat_info, timestamp, empty_cb, cb
from TelegramStorage import TelegramStorage

# import gettext
# gettext.install('rhythmbox', RB.locale_dir())

logger = logging.getLogger(__name__)

# import logging.config
# logging.config.fileConfig('/path/to/logging.conf')
# logging.basicConfig(stream=sys.stdout, level=logging.INFO)
# logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

CHAT_ID = -1001361643016

def inst_key(api_hash, phone):
    return '|'.join([phone.strip('+'), api_hash])


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
        return f'AsyncCall <{self.id}>'

    def wait(self, timeout=None):
        print('cb.wait')
        result = self._ready.wait(timeout=timeout)
        if result is False:
            raise TimeoutError()

    def release(self, update):
        print('cb.set')
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
    first_message_id = 0
    state = None

    __instances = {}
    __instance = None

    me = None
    storage = None

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

        self.storage = TelegramStorage(self, self.files_dir)
        return self.state

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

    # @TODO update
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
                        self.storage.add_audio(data, commit=False)
                        # self.last_message_id = current_msg_id
            self.storage.commit()
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

    def load_messages_idle(self, chat_id, update=None, done=None, glob=None):
        glob = {
            **(glob if glob else {}),
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
                    self.storage.commit()
                    glob['done']()
                    return False

                if msg_type == MessageType.AUDIO:
                    logger.debug('Detect audio file')
                    d = self.storage.add_audio(data, commit=False)
                    glob['update'](d) if d else None

        self.storage.commit()

        i = glob.get('iter', 0)
        i = i + 1

        if i < 5:
            glob['result'] = None
            glob['iter'] = i
            return True

        glob['done'](glob)
        print('================= load_messages DONE ===============')
        return False

    def load_message_async(self, chat_id, message_id):
        print('load_message_async')
        r = self.tg.get_message(chat_id, message_id)
        r.wait()
        return r.update

    def _download_audio_async(self, data, priority=1):
        print('_download_audio_async')
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
        print('download_file_async')
        r = self.tg.call_method('downloadFile', {
            'file_id': file_id,
            'priority': priority,
            # 'synchronous': False
            'synchronous': True
        })
        r.wait()
        return r.update

    def download_audio_async(self, chat_id, message_id, priority=1):
        print('download_audio_async')
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
        print('download_audio_idle')
        update = {}

        def set_file(file):
            print('---------SET_FILE--------------')
            print(file)

            update['data']['content']['audio']['audio'] = file
            done(self.storage.add_audio(update['data'], convert=False, commit=True))

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

