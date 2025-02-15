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

from common import version_to_number


INIT_VERSION = version_to_number('1.0.13')

INIT_SCHEMA = f'''
CREATE TABLE playlist (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `chat_id` INTEGER NOT NULL,
   `title` TEXT NOT NULL,
   `original_title` TEXT NOT NULL,
   `segments` TEXT NOT NULL DEFAULT '[]',
    UNIQUE (`chat_id`) ON CONFLICT REPLACE
);

CREATE TABLE audio (
   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
   `chat_id` INTEGER NOT NULL,
   `message_id` INTEGER NOT NULL,
   `mime_type` VARCHAR(48) NOT NULL,
   `track_number` INTEGER DEFAULT '1',
   `title` TEXT NOT NULL,
   `artist` TEXT NOT NULL,
   `album` TEXT DEFAULT NULL,
   `genre` TEXT DEFAULT NULL,
   `file_name` TEXT NOT NULL,
   `created_at` INTEGER NOT NULL,
   `date` INTEGER NOT NULL,
   `size` INTEGER NOT NULL,
   `duration` INTEGER NOT NULL,
   `is_downloaded` INT(1) DEFAULT '0',
   `is_moved` INT(1) DEFAULT '0',
   `is_hidden` INT(1) DEFAULT '0',
   `local_path` TEXT DEFAULT NULL,
   `play_count` INTEGER DEFAULT '0',
   `rating` INT(1) DEFAULT '0',
    UNIQUE (`chat_id`, `message_id`) ON CONFLICT REPLACE
);
CREATE INDEX idx_chat_id ON audio(chat_id);

CREATE TABLE migrations (
    version INTEGER PRIMARY KEY
);
INSERT INTO migrations (version) VALUES ( {INIT_VERSION} );
'''

MIGRATIONS = {
    # '1.0.13': MIGRATION_1_0_13,
}
