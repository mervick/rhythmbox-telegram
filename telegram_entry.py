# rhythmbox-telegram
# Copyright (C) 2023-2026 Andrey Izman <izmanw@gmail.com>
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

from gi.repository import RB, GObject
from storage import Audio
from account import KEY_PRELOAD_PREV_TRACK, KEY_PRELOAD_NEXT_TRACK, KEY_PRELOAD_HIDDEN_TRACK
from account import KEY_PRELOAD_MAX_FILE_SIZE, KEY_PRELOAD_FILE_FORMATS, AUDIO_FORMAT_ALL
from common import file_uri, get_location_data, get_entry_state, idle_add_once


class TelegramEntryType(RB.RhythmDBEntryType):
    """
    An entry type for handling Telegram audio entries in Rhythmbox.
    This class extends RB.RhythmDBEntryType to manage playback, preloading,
    and handling of audio entries from Telegram.
    """
    __gsignals__ = {
        'entry_downloaded': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
    }

    def __str__(self) -> str:
        obj_id = hex(id(self))
        return f'TelegramEntryType <{obj_id}>'

    def __init__(self, plugin):
        RB.RhythmDBEntryType.__init__(self, name='TelegramEntry', save_to_disk=False)
        self.source = None
        self.plugin = plugin
        self.shell = plugin.shell
        self.db = plugin.db
        self.shell_player = self.shell.props.shell_player
        self._pending_playback = None
        self._entry_error_id = None
        self._entry_downloaded_id = None

    def activate(self):
        """
        Activates the entry type by connecting to the player's error signal
        and the entry_downloaded signal.
        """
        self._entry_error_id = self.shell_player.props.player.connect('error', self._on_player_error)
        self._entry_downloaded_id = self.connect('entry_downloaded', self._on_entry_downloaded)

    def deactivate(self):
        """
        Deactivates the entry type by disconnecting from the player's error signal
        and the entry_downloaded signal.
        """
        self.shell_player.props.player.disconnect(self._entry_error_id)
        self.disconnect(self._entry_downloaded_id)

    def _on_entry_downloaded(self, entry_type, entry):
        """
        Handles the 'entry_downloaded' signal. If the downloaded entry matches
        the pending playback entry, it starts playback.
        """
        if not self._pending_playback:
            return

        location = entry.get_string(RB.RhythmDBPropType.LOCATION)
        if location == self._pending_playback:
            self._pending_playback = None
            self.shell_player.play_entry(entry, entry.get_entry_type().source)
            # GLib.timeout_add(100, self.shell.props.shell_player.emit, "playing-changed", True)

    def _on_player_error(self, *args):
        """ Handles the player's error signal by stopping playback. """
        self.shell.props.shell_player.stop()

    def setup(self, source):
        self.source = source

    @staticmethod
    def entry_view_iter_prev(model, iter):
        """ Gets the previous iterator in the model. """
        path = model.get_path(iter)
        if path.prev():
            return model.get_iter(path)
        return None

    def get_prev_entry(self, current_entry):
        """ Gets the previous entry in the entry view relative to the current entry. """
        entry_view = self.source.props.query_model
        iter = entry_view.get_iter_first()
        found = False

        while iter:
            entry = entry_view.get_value(iter, 0)
            if found:
                return entry
            if entry == current_entry:
                found = True
                iter = self.entry_view_iter_prev(entry_view, iter)
            else:
                iter = entry_view.iter_next(iter)
        return None

    def get_next_entry(self, current_entry):
        """ Gets the next entry in the entry view relative to the current entry. """
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

    def _load_entry_audio(self, entry):
        """ Loads the audio for the given entry. """
        self.plugin.loader.add_entry(entry).start()

    def _is_preload_enabled_for_audio(self, audio):
        """ Determine whether preloading should be enabled for a given audio """
        max_file_size = self.plugin.account.settings[KEY_PRELOAD_MAX_FILE_SIZE]
        allowed_format = self.plugin.account.settings[KEY_PRELOAD_FILE_FORMATS]

        if 0 < max_file_size < audio.size / 1000000:
            return False
        if allowed_format != AUDIO_FORMAT_ALL and audio.get_file_ext() not in allowed_format:
            return False
        return True

    def do_get_playback_uri(self, entry):
        """
        Gets the playback URI for the given entry. If the  audio is not yet downloaded,
        it triggers the download and returns None or an invalid URI for the currently playing entry.
        When an invalid URI is returned, the player causes an error in which the
        _on_player_error() handler is called and this stops playback.
        Also, when an invalid uri is returned the audio is saved in _pending_playback
        for the next playback after the download is complete
        """
        location = entry.get_string(RB.RhythmDBPropType.LOCATION)
        chat_id, message_id = get_location_data(location)
        audio = self.plugin.storage.get_audio(chat_id, message_id)
        if not audio:
            return None

        preload_hidden = self.plugin.account.settings[KEY_PRELOAD_HIDDEN_TRACK]

        if self.plugin.account.settings[KEY_PRELOAD_PREV_TRACK]:
            prev_entry = self.get_prev_entry(entry)
            if prev_entry and (preload_hidden or get_entry_state(prev_entry) != Audio.STATE_HIDDEN):
                prev_audio = self.plugin.storage.get_entry_audio(prev_entry) if prev_entry else None

                if prev_audio and not prev_audio.is_file_exists():
                    if self._is_preload_enabled_for_audio(prev_audio):
                        idle_add_once(self._load_entry_audio, prev_entry)

        # The preloader loads first what was sent last
        if self.plugin.account.settings[KEY_PRELOAD_NEXT_TRACK]:
            next_entry = self.get_next_entry(entry)
            if next_entry and (preload_hidden or get_entry_state(next_entry) != Audio.STATE_HIDDEN):
                next_audio = self.plugin.storage.get_entry_audio(next_entry) if next_entry else None

                if next_audio and not next_audio.is_file_exists():
                    if self._is_preload_enabled_for_audio(next_audio):
                        idle_add_once(self._load_entry_audio, next_entry)

        if audio.is_file_exists():
            self._pending_playback = None
            return file_uri(audio.local_path)

        return_uri = None

        playing_entry = self.shell.props.shell_player.get_playing_entry()
        if playing_entry:
            playing_location = playing_entry.get_string(RB.RhythmDBPropType.LOCATION)
            if playing_location == location:
                idle_add_once(self.shell.props.shell_player.stop)
                return_uri = 'invalid'

        state = get_entry_state(entry)
        if state == Audio.STATE_LOADING:
            return return_uri

        self._pending_playback = location
        self._load_entry_audio(entry)
        return return_uri

    def do_can_sync_metadata(self, *_):
        return True


GObject.type_register(TelegramEntryType)
