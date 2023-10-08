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

import rb
from gi.repository import RB


def to_location(phone, chat_id, audio_id):
    return 'tg://%s/%s/%s' % (phone, chat_id, audio_id)

def get_location_audio_id(location):
    return location.split('/')[-1]

def get_location_data(location):
    d = location.split('/')
    return [d[-2], d[-1]]

def file_uri(uri):
    return 'file://%s' % uri

class TelegramEntryType(RB.RhythmDBEntryType):
    def __init__(self, plugin):
        RB.RhythmDBEntryType.__init__(self, name='telegram')
        self.account = plugin.account
        self.settings = plugin.settings
        self.api = plugin.api
        self.shell = plugin.shell
        self.db = plugin.db

    def setup(self, source):
        self.source = source

    def do_get_playback_uri(self, entry):
        print('================do_get_playback_uri==================')
        uri = entry.get_string(RB.RhythmDBPropType.MOUNTPOINT)

        if not uri:
            loc = entry.get_string(RB.RhythmDBPropType.LOCATION)
            chat_id, message_id = get_location_data(loc)
            print("converted track uri: %s" % loc)
            print("chat_id: %s" % chat_id)
            print("message_id: %s" % message_id)
            audio = self.api.get_audio(chat_id, message_id)
            print('audio %s' % audio)
            if not audio:
                return None

            def done(update):
                print('=========DONE========')
                uri = file_uri(update.local_path)
                self.db.entry_set(entry, RB.RhythmDBPropType.MOUNTPOINT, uri)
                self.db.entry_set(entry, RB.RhythmDBPropType.LAST_SEEN, 1)
                # self.shell.props.shell_player.play()
                self.source.add_to_queue(uri)
                self.shell.props.shell_player.do_next()

            uri = audio.get_path(wait=False, done=done)
            # entry.set_string(RB.RhythmDBPropType.MOUNTPOINT, uri)
            # if not uri:
            #     self.shell.props.shell_player.pause()

            if uri:
                return file_uri(uri)
            else:
                return False

        return uri

    def update_availability(self, *args, **kwargs):
        print('================update_availability==================')
        print(args)
        return

    def do_can_sync_metadata(self, entry):
        return True

    def can_sync_metadata(self, entry):
        return True

    def sync_metadata(self, entry, changes):
        print('================sync_metadata==================')
        print(entry)
        print(changes)
        return
