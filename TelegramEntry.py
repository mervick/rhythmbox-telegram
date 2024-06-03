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
        self._set_entry = None

    def setup(self, source):
        self.source = source

    def _update_entry(self, entry, audio):
        audio.update_tags()

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

    def do_get_playback_uri(self, entry):
        location = entry.get_string(RB.RhythmDBPropType.LOCATION)
        chat_id, message_id = get_location_data(location)
        audio = self.plugin.storage.get_audio(chat_id, message_id)

        if not audio:
            return None

        if audio.is_file_exists():
            self._set_entry = None
            return file_uri(audio.local_path)

        if self.plugin.is_downloading:
            return None

        state = entry.get_string(RB.RhythmDBPropType.COMMENT)
        if state == 'STATE_LOADING':
            return None

        self.plugin.is_downloading = True
        self._set_entry = entry
        self.db.entry_set(entry, RB.RhythmDBPropType.COMMENT, 'STATE_LOADING')
        self.db.commit()

        def on_done(au):
            self.plugin.is_downloading = False
            self._update_entry(entry, au)
            if self._set_entry is not None:
                self.shell.props.shell_player.play_entry(self._set_entry, self.plugin.source)

        def on_error():
            self.plugin.is_downloading = False
            self._set_entry = None

        audio.download_file(done=on_done, error=on_error)
        return None

    def do_can_sync_metadata(self, entry): # noqa
        return True
