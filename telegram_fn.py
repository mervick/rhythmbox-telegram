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

from datetime import datetime
import logging
import enum

logger = logging.getLogger(__name__)

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
    'audio/x-flac': 'flac',
    'audio/flac': 'flac',
    'audio/x-ms-wma': 'wma',
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
    'audio/x-wav': 'wav',
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

def empty_cb(*args, **kwargs):
    pass

def cb(fn):
    return fn if fn else empty_cb
