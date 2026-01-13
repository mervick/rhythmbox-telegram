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

import re
from gi.repository import RB  # type: ignore
from gi.repository import GObject, Gdk, Gio, GLib
import hashlib
import logging
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
from telegram.client import Telegram
from telegram.utils import AsyncResult
from telegram.client import AuthorizationState
from common import MessageType, audio_content_set, API_ERRORS, get_content_type, is_msg_valid
from common import get_chat_info, empty_cb, cb, show_error
from storage import Storage

import gettext
gettext.install('rhythmbox', RB.locale_dir())
_ = gettext.gettext

logger = logging.getLogger(__name__)


class TelegramClient(Telegram):
    """ Extended Telegram client with custom authorization handling """
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


class TelegramAuthError(Exception):
    """ Exception for Telegram authorization errors """
    def __init__(self, message, info):
        super().__init__(message)
        self.info = info

    def get_info(self):
        if self.info is not None:
            if type(self.info) == dict:
                return self.info.get('message', self.__str__())
        return self.__str__()


class TelegramAuthStateError(Exception):
    """ Exception for invalid Telegram authorization states """
    pass


def inst_key(api_id, phone):
    """ Generate instance key from API ID and phone number """
    return '|'.join([phone.strip('+'), api_id])


REGEX_TME_LINK = re.compile(r'^https://t\.me/(c/)?([a-zA-Z0-9_]+)/([0-9]+)(\?.+)?$')

API_ALL_MESSAGES_LOADED = 'ALL_MESSAGES_LOADED'
API_END_OF_SEGMENT = 'END_OF_SEGMENT'
API_PAGE_LOADED = 'API_PAGE_LOADED'

LAST_MESSAGE_ID = 0x100000  # 1048576

TDLIB_VERB_FATAL = 0
TDLIB_VERB_ERROR = 1
TDLIB_VERB_WARN  = 2
TDLIB_VERB_INFO  = 3
TDLIB_VERB_DEBUG = 4


class TelegramApi(GObject.Object):
    """ Main Telegram API wrapper for Rhythmbox integration """
    object = GObject.Property(type=GObject.Object)
    application_version = '1.0.0'

    state = None
    storage = None

    __instances = {}

    @staticmethod
    def loaded():
        """ Check if any Telegram instance is currently loaded """
        return TelegramApi.__current

    @staticmethod
    def api(api_id, api_hash, phone):
        """ Get or create Telegram API instance """
        key = inst_key(api_id, phone)
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
        self.files_dir = os.path.join(str(plugin_dir), hasher.hexdigest())
        self.temp_dir = os.path.join(self.files_dir, 'files')

        self.chats = {}
        self.chats_count = 0
        self.last_message_id = 0
        self.is_chat_updates_started = False

        self.tg = TelegramClient(
            api_id=self.api_id,
            api_hash=self.api_hash,
            phone=self.phone,
            database_encryption_key=self.api_hash,
            files_directory=self.files_dir,
            device_model='Rhythmbox Telegram Plugin',
            application_version=TelegramApi.application_version,
            use_secret_chats=False,
            tdlib_verbosity=TDLIB_VERB_FATAL
        )

    ############################################################
    # Authorization and state management
    ############################################################
    def login(self, code=None):
        """
        Authenticate with Telegram.
        If called without a code, initiates login and requests a verification code
        to be sent to the user's device.
        """
        if code and self.state == self.tg.authorization_state.WAIT_CODE:
            self.tg.send_code(code=code)

        self.state = self.tg.login(blocking=False)
        if self.state != self.tg.authorization_state.READY:
            raise TelegramAuthStateError(self.state)

        self.storage = Storage(self, self.files_dir)
        if self.state:
            self.start_chat_updates()
        else:
            self.stop_chat_updates()
        return self.state

    def get_error(self):
        """ Get last error message """
        err = self.tg.error.get('message') if self.tg.error else None
        return API_ERRORS[err] if err in API_ERRORS else err

    def is_ready(self):
        """ Check if API is ready for operations """
        return self.state == AuthorizationState.READY

    ############################################################
    # Managing chats
    ############################################################
    def start_chat_updates(self):
        """ Start listening for new chat updates """
        if not self.is_chat_updates_started:
            self.is_chat_updates_started = True
            self.tg.add_update_handler('updateNewChat', self._update_new_chat_cb)

    def stop_chat_updates(self):
        """ Stop chat updates listener """
        self.is_chat_updates_started = False
        self.tg.remove_update_handler('updateNewChat', self._update_new_chat_cb)

    def _update_new_chat_cb(self, update):
        """ Callback for handling new chat updates from Telegram """
        chat = update.get('chat', {})
        chat_id = chat.get('id')
        if chat_id:
            self.chats[chat_id] = get_chat_info(chat)

    def _chats_idle_cb(self, data):
        """ Idle callback for loading chats asynchronously """
        r = data.get('result')
        if not r:
            r = data['result'] = self.tg.call_method('loadChats', {'limit': 100})
        if not r._ready.is_set():  # wait to load
            return True

        data['result'] = None
        total = len(self.chats)

        if self.chats_count == total:
            self.chats_count = total
            data['update'](self.chats)
            return False

        self.chats_count = total
        return True

    def reset_chats(self):
        """ Clear cached chats data """
        self.chats_count = 0
        self.chats = {}

    def get_chats_idle(self, update):
        """ Load chats asynchronously """
        Gdk.threads_add_idle(0, self._chats_idle_cb, {'update': update})

    ############################################################
    # Managing messages
    ############################################################
    def load_pinned_messages_idle(self, chat_id, from_message_id, offset=0, limit=100, on_success=empty_cb, on_error=empty_cb):
        """ Load pinned messages IDLE """
        logger.debug('load pinned messages %s' % (chat_id))
        blob = {
            "chat_id": chat_id,
            "from_message_id": from_message_id,
            "offset": offset,
            "limit": limit,
            "on_success": on_success,
            "on_error": on_error,
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._load_pinned_messages_idle_cb, blob)

    def _load_pinned_messages_idle_cb(self, blob):
        """ Load pinned messages IDLE callback """
        r = blob.get('result', None)

        if not r:
            r = blob['result'] = self.tg.call_method(
                'searchChatMessages',
                params={
                    'chat_id': blob.get('chat_id'),
                    "query": "",
                    "from_message_id": blob.get('from_message_id', 0),
                    "offset": blob.get('offset', 0),
                    "limit": blob.get('limit', 100),
                    "filter": { "@type": "searchMessagesFilterPinned" }
                }
            )

        if not r._ready.is_set():
            return True

        if not r.update or not r.update['total_count'] or not r.update['messages']:
            logger.debug('tg, load pinned messages: No messages found, exit loop')
            blob['on_success']()
            return False

        msgs = r.update.get('messages', [])
        last_msg_id = msgs[-1]['id']

        if last_msg_id == LAST_MESSAGE_ID:
            logger.debug('tg, load pinned messages: No messages found, exit loop')
            blob['on_success']()
            return False

        blob['on_success'](msgs)
        return False

    def load_message_idle(self, chat_id, message_id, on_success=empty_cb, on_error=empty_cb):
        """ Load single message asynchronously """
        logger.debug('load message %s %s' % (chat_id, message_id))
        blob = {
            "chat_id": chat_id,
            "message_id": message_id,
            "on_success": on_success,
            "on_error": on_error,
            "result": self.tg.get_message(chat_id, message_id)
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, _wait_cb, blob)

    def load_messages_idle(self, chat_id, update=None, each=None, on_success=None, blob=None, limit=100, offset=0):
        """ Load multiple messages asynchronously """
        blob = {
            **(blob if blob else {}),
            "limit": limit,
            "offset": offset,
            "chat_id": chat_id,
            "update": update if update else empty_cb,
            "each": each if each else empty_cb,
            "on_success": on_success if on_success else empty_cb
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self._load_messages_idle_cb, blob)

    def _load_messages_idle_cb(self, blob):
        """ Idle callback for loading messages asynchronously """
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
            blob['on_success'](blob, API_ALL_MESSAGES_LOADED)
            return False

        msgs = r.update.get('messages', [])
        blob['last_msg_id'] = msgs[-1]['id']

        if blob['last_msg_id'] == LAST_MESSAGE_ID:
            logger.debug('tg, load messages: No messages found, exit loop')
            blob['on_success'](blob, API_ALL_MESSAGES_LOADED)
            return False

        for data in msgs:
            if is_msg_valid(data):
                msg_type = get_content_type(data)
                current_msg_id = data['id']

                if last_msg_id == current_msg_id:
                    blob['on_success'](blob, API_END_OF_SEGMENT)
                    return False

                ret = blob['each'](data, blob)
                if type(ret) is bool and not ret:
                    break

                if msg_type == MessageType.AUDIO:
                    logger.debug('Detect audio file')
                    audio = self.storage.add_audio(data)
                    blob['update'](audio, blob) if audio else None

        blob['on_success'](blob, API_PAGE_LOADED)
        return False

    def get_message_link(self, chat_id, message_id):
        """ Get shareable link for a message """
        r = self.tg.call_method('getMessageLink', {
            'chat_id': int(chat_id),
            'message_id': int(message_id),
            "for_album": False,
            "for_group": False
        })
        r.wait()
        return r.update.get('link') if r.update else None

    def get_message_direct_link(self, link):
        """ Convert public link to direct Telegram URI """
        if not link:
            return None
        m = REGEX_TME_LINK.match(link)
        if not m:
            return link
        # private
        if m.group(1):
            return "tg://privatepost?channel=%s&post=%s&single" % (m.group(2), m.group(3))
        # public
        return "tg://resolve?domain=%s&post=%s&single" % (m.group(2), m.group(3))

    ############################################################
    # Managing files
    ############################################################
    def download_audio_idle(self, chat_id, message_id, priority=1, on_success=empty_cb, on_error=empty_cb):
        """ Download audio message asynchronously """
        def download(data, *arg):
            if not data:
                on_error()
                return
            update = {'data': data}

            def set_file(file, *arg):
                update['data']['content']['audio']['audio'] = file
                on_success(self.storage.add_audio(update['data'], convert=False))
            self._download_audio_idle_cb(data, priority=priority, on_success=set_file, on_error=on_error)

        self.load_message_idle(chat_id, message_id, on_success=download, on_error=on_error)

    def _download_audio_idle_cb(self, data, priority=1, on_success=empty_cb, on_error=empty_cb):
        """ Idle callback for downloading audio files from Telegram """
        content = data.get('content', {})
        audio = content.get('audio')

        if not (audio and audio_content_set <= set(audio)):
            logger.warning('Audio message has no required keys, skipping...')
            logger.debug(content)
            on_error()
            return

        completed = audio['audio']['remote']['is_uploading_completed']
        audio_id = audio['audio']['id']

        if not completed:
            logger.warning('Audio message: %d not uploaded, skipping...', audio_id)
            on_error()
            return

        self.download_file_idle(audio_id, priority=priority, on_success=on_success, on_error=on_error)

    def download_file_idle(self, file_id, priority=1, on_success=empty_cb, on_error=empty_cb):
        """ Download any file asynchronously """
        logger.debug('download_file_idle')
        blob = {
            "result": self.tg.call_method('downloadFile', {
                'file_id': file_id,
                'priority': priority,
                # 'synchronous': False
                'synchronous': True
            }),
            "on_success": on_success if on_success else empty_cb,
            "on_error": on_error if on_error else empty_cb,
        }
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, _wait_cb, blob)


def _wait_cb(blob):
    """ Callback handler for async operations """
    r = blob.get('result', None)
    if not r.ok_received and r.error:
        show_error(_('Error: Telegram API request failed'), format_error(r))
        cb(blob.get('on_error'))()
        return False

    if not r._ready.is_set():
        return True

    blob.get('on_success')(r.update)
    return False

def format_error(r: AsyncResult) -> str | None:
    """ Format Telegram API error message """
    info = r.error_info if r.error_info else {}
    message = info.get('message')
    if message:
        request_id = info.get('@extra', {}).get('request_id')
        if request_id:
            message = f"{message}, request_id: {request_id}"
    return message
