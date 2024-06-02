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

from gi.repository import RB
from common import file_uri, get_location_data


class TelegramEntryType(RB.RhythmDBEntryType):
    def __init__(self, plugin):
        RB.RhythmDBEntryType.__init__(self, name='telegram')
        self.source = None
        self.plugin = plugin
        self.shell = plugin.shell
        self.db = plugin.db

    def setup(self, source):
        self.source = source

    def do_get_playback_uri(self, entry):
        uri = entry.get_string(RB.RhythmDBPropType.MOUNTPOINT)
        if not uri:
            location = entry.get_string(RB.RhythmDBPropType.LOCATION)
            chat_id, message_id = get_location_data(location)
            audio = self.plugin.storage.get_audio(chat_id, message_id)
            if not audio:
                return None
            if self.plugin.is_downloading:
                return None

            self.plugin.is_downloading = True
            file_path = audio.get_path(wait=True)
            self.plugin.is_downloading = False

            if file_path:
                audio.update_tags(file_path)

                self.db.entry_set(entry, RB.RhythmDBPropType.TRACK_NUMBER, audio.track_number)
                self.db.entry_set(entry, RB.RhythmDBPropType.TITLE, audio.title)
                self.db.entry_set(entry, RB.RhythmDBPropType.ARTIST, audio.artist)
                self.db.entry_set(entry, RB.RhythmDBPropType.ALBUM, audio.album)
                self.db.entry_set(entry, RB.RhythmDBPropType.ALBUM_ARTIST, audio.artist)
                self.db.entry_set(entry, RB.RhythmDBPropType.GENRE, audio.genre)
                self.db.entry_set(entry, RB.RhythmDBPropType.DURATION, audio.duration)
                self.db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(audio.created_at))
                self.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, audio.get_state())
                self.db.entry_set(entry, RB.RhythmDBPropType.DATE, int(audio.date))
                self.db.entry_set(entry, RB.RhythmDBPropType.PLAY_COUNT, int(audio.play_count))
                self.db.entry_set(entry, RB.RhythmDBPropType.FILE_SIZE, int(audio.size))
                self.db.commit()

                return file_uri(file_path)
            else:
                self.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, audio.get_state())
                self.db.commit()
                return None

        return uri

    def do_can_sync_metadata(self, entry): # noqa
        return True
