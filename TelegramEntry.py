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

from gi.repository import RB, GLib
from common import file_uri, get_location_data, TG_RhythmDBPropType


class TelegramEntryType(RB.RhythmDBEntryType):
    def __init__(self, plugin):
        RB.RhythmDBEntryType.__init__(self, name='telegram')
        self.source = None
        self.plugin = plugin
        self.shell = plugin.shell
        self.db = plugin.db
        self.shell_player = self.shell.props.shell_player
        self._set_entry = None
        self._was_stopped = None
        self._entry_error_id = None

    def activate(self):
        self._entry_error_id = self.shell_player.props.player.connect('error', self._on_player_error)

    def deactivate(self):
        self.shell_player.props.player.disconnect(self._entry_error_id)

    def _on_player_error(self, *args):
        self._was_stopped = True
        self.shell.props.shell_player.stop()

    def setup(self, source):
        self.source = source

    def do_get_playback_uri(self, entry):
        uri = self._get_playback_uri(entry)
        # self.latest_uri = uri
        return uri

    def get_next_entry(self, current_entry):
        entry_view = self.source.props.query_model
        iter = entry_view.get_iter_first()
        found = False

        while iter:
            entry = entry_view.get_value(iter, 0)
            if found:
                return entry
            if entry == current_entry:
                found = True
            iter = entry_view.iter_next(iter)
        return None

    def _get_playback_uri(self, entry):
        location = entry.get_string(RB.RhythmDBPropType.LOCATION)
        chat_id, message_id = get_location_data(location)
        audio = self.plugin.storage.get_audio(chat_id, message_id)
        if not audio:
            return None

        next_entry = self.get_next_entry(entry)
        if next_entry:
            next_audio = self.plugin.storage.get_entry_audio(next_entry)
            if next_audio and not next_audio.is_file_exists():
                self.plugin.loader.add_entry(next_entry).start()

        if audio.is_file_exists():
            self._set_entry = None
            return file_uri(audio.local_path)

        # if self.plugin.loader.is_downloading(entry):
        #     return None

        return_val = None

        playing_entry = self.shell.props.shell_player.get_playing_entry()
        playing_location = playing_entry.get_string(RB.RhythmDBPropType.LOCATION) if playing_entry else None

        if playing_location == location:
            self._was_stopped = True
            GLib.idle_add(self.shell.props.shell_player.stop)
            return_val = 'invalid'

        if self.plugin.is_downloading:
            return return_val

        state = entry.get_string(TG_RhythmDBPropType.STATE)
        if state == 'STATE_LOADING':
            return return_val

        self.plugin.is_downloading = True
        self._set_entry = entry
        self.db.entry_set(entry, TG_RhythmDBPropType.STATE, 'STATE_LOADING')
        self.db.commit()

        def success(upd_audio):
            self.plugin.is_downloading = False
            upd_audio.update_tags()
            upd_audio.update_entry(entry)
            if self._set_entry is not None:
                play_entry = self._set_entry
                self._set_entry = None
                self.shell_player.play_entry(play_entry, self.plugin.source)

                if self._was_stopped:
                    self._was_stopped = False
                    GLib.timeout_add(100, self.shell.props.shell_player.emit, "playing-changed", True)

        def fail():
            audio.is_error = True
            self.db.entry_set(entry, RB.RhythmDBPropType.PLAYBACK_ERROR, 1)
            self.db.entry_set(entry, TG_RhythmDBPropType.STATE, 'STATE_ERROR')
            self.db.commit()
            self.plugin.is_downloading = False
            self._set_entry = None

        audio.download(success=success, fail=fail)
        return return_val

    def do_can_sync_metadata(self, entry): # noqa
        return True
