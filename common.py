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

import enum
import math
import base64
import hashlib
from datetime import datetime
from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes
from gi.repository import RB, GLib, Gio, Gtk

import gettext
gettext.install('rhythmbox', RB.locale_dir())


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


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
    'audio/mpeg3': 'mp3',
    'audio/mp3': 'mp3',
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

def get_entry_state(entry):
    return entry.get_ulong(RB.RhythmDBPropType.MTIME)

def set_entry_state(db, entry, state):
    db.entry_set(entry, RB.RhythmDBPropType.MTIME, state)

def get_entry_location(entry):
    return entry.get_string(RB.RhythmDBPropType.LOCATION)

def is_same_entry(entry1, entry2):
    return get_entry_location(entry1) == get_entry_location(entry2)

def to_location(api_hash, chat_id, message_id, audio_id):
    return 'tg://%s/%s/%s/%s' % (api_hash, chat_id, message_id, audio_id)

def get_location_audio_id(location):
    return location.split('/')[-1]

def get_location_data(location):
    d = location.split('/')
    return [d[-3], d[-2]]

def file_uri(path):
    return GLib.filename_to_uri(path, None)

def open_path(path):
    Gio.app_info_get_default_for_uri(file_uri(path), None)

def get_content_type(data):
    if '@type' in data['content'] and MessageType.has(data['content']['@type']):
        return MessageType(data['content']['@type'])
    return MessageType.NONE

def is_msg_valid(data):
    return message_set <= set(data)

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

def empty_cb(*args, **kwargs): # noqa
    pass

def cb(fn):
    return fn if fn else empty_cb

def get_option_title(options, value):
    for option in options:
        if option[1] == value:
            return option[0]

META_TAGS = {
    'title': RB.MetaDataField.TITLE,
    'artist': RB.MetaDataField.ARTIST,
    'album': RB.MetaDataField.ALBUM,
    'album_artist': RB.MetaDataField.ALBUM_ARTIST,
    'track_number': RB.MetaDataField.TRACK_NUMBER,
    'date': RB.MetaDataField.DATE,
    'duration': RB.MetaDataField.DURATION,
    'genre': RB.MetaDataField.GENRE,
}

def get_audio_tags(file_path):
    tags = {}
    metadata = RB.MetaData()
    uri = GLib.filename_to_uri(file_path, None)
    metadata.load(uri)

    for tag_name in META_TAGS:
        tags[tag_name] = None
        try:
            tag = metadata.get(META_TAGS[tag_name])
            tags[tag_name] = tag[1] if tag[0] else None
            if tag_name == 'date':
                tags['year'] = GLib.Date.new_julian(tag[1]).get_year() if tag[0] else None
        except TypeError:
            pass

    return tags

filename_illegal1 = '<>/\\|*'
filename_illegal2 = '":'

def clear_filename(filename):
    for char in filename_illegal1:
        filename = filename.replace(char, '_')
    for char in filename_illegal2:
        filename = filename.replace(char, '')
    return filename

# %at -- album title
# %aa -- album artist
# %aA -- album artist (lowercase)
# %as -- album artist sortname
# %aS -- album artist sortname (lowercase)
# %ay -- album release year
# %an -- album disc number
# %aN -- album disc number, zero padded
# %ag -- album genre
# %aG -- album genre (lowercase)
# %tn -- track number (i.e 8)
# %tN -- track number, zero padded (i.e. 08)
# %tt -- track title
# %ta -- track artist
# %tA -- track artist (lowercase)
# %ts -- track artist sortname
# %tS -- track artist sortname (lowercase)

filepath_pattern_markers = {
    "%at": "album",
    "%aa": "album_artist",
    "%aA": "album_artist_lower",
    "%ay": "year",
    "%ag": "genre",
    "%aG": "genre_lower",
    "%tn": "track_number",
    "%tN": "track_number_padded",
    "%tt": "title",
    "%ta": "artist",
    "%tA": "artist_lower",
}

def get_first_artist(artist):
    return artist.split('\x01')[0].split(';')[0]

def filepath_parse_pattern(pattern, tags):
    # Parse a filename pattern and replace markers with values from the tags
    _tags = {**tags}
    # Remove the '\x01\x02' characters from the string, for some reason some artist have 2 or
    # maybe even more lines separated by \x01\x02
    _tags['artist'] = get_first_artist(_tags.get('artist', 'Unknown'))
    _tags['artist_lower'] = _tags.get('artist').lower()
    _tags['album_artist'] = get_first_artist(_tags.get('album_artist', 'Unknown'))
    _tags['album_artist_lower'] = _tags.get('album_artist').lower()
    _tags['genre_lower'] = _tags.get('genre', 'Unknown').lower()
    _tags['track_number_padded'] = "%02i" % int(_tags.get('track_number', 1))

    for marker in filepath_pattern_markers:
        tag = clear_filename(str(_tags.get(filepath_pattern_markers[marker], 'Unknown')))
        pattern = pattern.replace(marker, tag)

    return pattern

def get_date(unix_ts):
    dt = GLib.DateTime.new_from_unix_local(int(unix_ts))
    date = GLib.Date.new_dmy(dt.get_day_of_month(), GLib.DateMonth(dt.get_month()), dt.get_year())
    return date.get_julian()

def get_year(julian):
    date = GLib.Date.new_julian(julian)
    return date.get_year()

def show_error(title, description=None, parent=None): # noqa
    if parent is not None:
        if not isinstance(parent, Gtk.Window):
            parent = parent.get_toplevel()
            if not isinstance(parent, Gtk.Window):
                parent = None
    err_dialog = Gtk.MessageDialog(
        parent=parent,
        flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        message_format=title)
    # err_dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, title) # noqa
    if description is not None:
        err_dialog.format_secondary_text(str(description)) # noqa
    err_dialog.set_application(Gio.Application.get_default())
    err_dialog.run() # noqa
    err_dialog.destroy()

# def detect_theme_scheme():
#     theme = str(Gtk.Settings.get_default().get_property('gtk-theme-name')).lower().find('dark')
#     dark = Gtk.Settings.get_default().get_property('gtk-application-prefer-dark-theme')
#
#     return 'dark' if theme != -1 or dark else 'light'

def encrypt(original_text, password):
    def pad(s):
        return s + (AES.block_size - len(s) % AES.block_size) * chr(AES.block_size - len(s) % AES.block_size)
    key = hashlib.sha256(password.encode('utf-8')).digest()
    raw = pad(original_text)
    iv = get_random_bytes(AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw.encode())).decode('utf-8')

def decrypt(encrypted_text, password):
    def unpad(s):
        return s[:-ord(s[len(s) - 1:])]
    encrypted_text = base64.b64decode(encrypted_text)
    key = hashlib.sha256(password.encode('utf-8')).digest()
    iv = encrypted_text[:AES.block_size]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(encrypted_text[AES.block_size:])).decode('utf-8')

def pretty_file_size(size_bytes, digits=2):
    if size_bytes == 0:
        return "0 bytes"
    size_name = ("bytes", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1000)))
    p = math.pow(1000, i)
    s = round(size_bytes / p, digits)
    return f"{s} {size_name[i]}"
