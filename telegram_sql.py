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

TABLE_PARAMS = '''
CREATE TABLE params (
   `id` INTEGER PRIMARY KEY,
   `title` TEXT NOT NULL,
   `original_title` TEXT NOT NULL,
   `chat_id` INTEGER NOT NULL,
   `position` INTEGER
);
'''

TABLE_PLAYLIST = '''
CREATE TABLE playlist (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `title` TEXT NOT NULL,
   `original_title` TEXT NOT NULL,
   `chat_id` INTEGER NOT NULL,
   `position` INTEGER
);
'''

# @TODO remove audio_id, it is dynamically changes
TABLE_AUDIO = '''
CREATE TABLE audio (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `chat_id` INTEGER NOT NULL,
   `message_id` INTEGER NOT NULL,
   `audio_id` INTEGER NOT NULL,
   `mime_type` VARCHAR(48) NOT NULL,
   `title` TEXT NOT NULL,
   `artist` TEXT NOT NULL,
   `file_name` TEXT NOT NULL,
   `date` INTEGER NOT NULL,
   `size` INTEGER NOT NULL,
   `duration` INTEGER NOT NULL,
   `is_downloaded` INT(1) DEFAULT '0',
   `is_moved` INT(1) DEFAULT '0',
   `is_hidden` INT(1) DEFAULT '0',
   `local_path` TEXT DEFAULT NULL,
   `document_id` INTEGER DEFAULT NULL,
   `info_id` INTEGER DEFAULT NULL,
    UNIQUE (`message_id`) ON CONFLICT REPLACE,
    UNIQUE (`audio_id`) ON CONFLICT REPLACE
);
'''

# @TODO remove document_id, it is dynamically changes
TABLE_DOCUMENT = '''
CREATE TABLE document (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `chat_id` INTEGER NOT NULL,
   `message_id` INTEGER NOT NULL,
   `document_id` INTEGER NOT NULL,
   `mime_type` VARCHAR(48) NOT NULL,
   `file_name` TEXT NOT NULL,
   `date` INTEGER NOT NULL,
   `size` INTEGER NOT NULL,
   `artist` TEXT NOT NULL,
    UNIQUE (`message_id`) ON CONFLICT REPLACE,
    UNIQUE (`document_id`) ON CONFLICT REPLACE
);
'''

# @TODO remove message_id
TABLE_INFO = '''
CREATE TABLE info (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `chat_id` INTEGER NOT NULL,
   `message_id` INTEGER NOT NULL,
   `photo_id` INTEGER NOT NULL,
   `caption` TEXT NOT NULL,
   `date` INTEGER NOT NULL,
   `info` TEXT NOT NULL,
    UNIQUE (`message_id`) ON CONFLICT REPLACE,
    UNIQUE (`photo_id`) ON CONFLICT REPLACE
);
'''
