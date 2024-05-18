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

import rb
from gi.repository import RB
from gi.repository import GLib
from common import get_audio_tags, file_uri


def to_location(hash, date, chat_id, audio_id):
    return 'tg://%s/%s/%s/%s' % (hash, date, chat_id, audio_id)

def get_location_audio_id(location):
    return location.split('/')[-1]

def get_location_data(location):
    d = location.split('/')
    return [d[-2], d[-1]]


class TelegramEntryType(RB.RhythmDBEntryType):
    def __init__(self, plugin):
        RB.RhythmDBEntryType.__init__(self, name='telegram')
        self.plugin = plugin
        self.account = plugin.account
        self.settings = plugin.settings
        self.api = plugin.api
        self.storage = plugin.storage
        self.shell = plugin.shell
        self.db = plugin.db

    def setup(self, source):
        self.source = source

    def do_get_playback_uri(self, entry):
        print('================do_get_playback_uri==================')
        uri = entry.get_string(RB.RhythmDBPropType.MOUNTPOINT)
        print(uri)

        if not uri:
            loc = entry.get_string(RB.RhythmDBPropType.LOCATION)
            # return loc
            chat_id, message_id = get_location_data(loc)
            print("converted track uri: %s" % loc)
            # print("chat_id: %s" % chat_id)
            print("message_id: %s" % message_id)
            audio = self.storage.get_audio(chat_id, message_id)
            # print('audio %s' % audio)
            if not audio:
                print('== return None')
                return None
            if self.plugin.is_downloading:
                print('== is_downloading, return None')
                return None

            self.plugin.is_downloading = True
            print('== start downloading')
            file_path = audio.get_path(wait=True)
            self.plugin.is_downloading = False
            print('== get file_path %s' % file_path)

            if file_path:
                tags = get_audio_tags(file_path)

                self.db.entry_set(entry, RB.RhythmDBPropType.TRACK_NUMBER, tags['track_number'])
                self.db.entry_set(entry, RB.RhythmDBPropType.TITLE, tags['title'])
                self.db.entry_set(entry, RB.RhythmDBPropType.ARTIST, tags['artist'])
                self.db.entry_set(entry, RB.RhythmDBPropType.ALBUM, tags['album'])
                self.db.entry_set(entry, RB.RhythmDBPropType.DURATION, tags['duration'])
                self.db.entry_set(entry, RB.RhythmDBPropType.DATE, tags['date'])
                self.db.entry_set(entry, RB.RhythmDBPropType.GENRE, tags['genre'])
                self.db.commit()

                # print(tags)
                return file_uri(file_path)
            else:
                return None

        return uri

    def do_can_sync_metadata(self, entry):
#         return False
        return True
