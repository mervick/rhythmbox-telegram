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


TABLE_PLAYLIST = '''
CREATE TABLE playlist (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `chat_id` INTEGER NOT NULL,
   `title` TEXT NOT NULL,
   `original_title` TEXT NOT NULL,
   `segments` TEXT NOT NULL DEFAULT '[]',
    UNIQUE (`chat_id`) ON CONFLICT REPLACE
);
'''

TABLE_AUDIO = '''
CREATE TABLE audio (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `chat_id` INTEGER NOT NULL,
   `message_id` INTEGER NOT NULL,
   `mime_type` VARCHAR(48) NOT NULL,
   `title` TEXT NOT NULL,
   `artist` TEXT NOT NULL,
   `album` TEXT DEFAULT NULL,
   `year` INTEGER DEFAULT NULL,
   `genre` TEXT DEFAULT NULL,
   `file_name` TEXT NOT NULL,
   `date` INTEGER NOT NULL,
   `size` INTEGER NOT NULL,
   `duration` INTEGER NOT NULL,
   `is_downloaded` INT(1) DEFAULT '0',
   `is_moved` INT(1) DEFAULT '0',
   `is_hidden` INT(1) DEFAULT '0',
   `local_path` TEXT DEFAULT NULL,
   `info_id` INTEGER DEFAULT NULL,
    UNIQUE (`message_id`) ON CONFLICT REPLACE
);
'''

TABLE_INFO = '''
CREATE TABLE info (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `chat_id` INTEGER NOT NULL,
   `message_id` INTEGER NOT NULL,
   `caption` TEXT NOT NULL,
   `date` INTEGER NOT NULL,
   `info` TEXT NOT NULL,
    UNIQUE (`message_id`) ON CONFLICT REPLACE
);
'''
