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

import os
import re
from rb import rbconfig # noqa
from gi.repository import Gio
from common import SingletonMeta, show_error

# settings keys
KEY_API_ID = "api-id"
KEY_API_HASH = "api-hash"
KEY_PHONE = "phone"
KEY_CONNECTED = "connected"

KEY_CHANNELS = "channels"
KEY_LIBRARY_PATH = "library-path"

KEY_CONFLICT_RESOLVE = "conflict-resolve"
KEY_FOLDER_HIERARCHY = "folder-hierarchy"
KEY_FILENAME_TEMPLATE = "filename-template"
KEY_PAGE_GROUP = "page-group"
KEY_AUDIO_VISIBILITY = "audio-visibility"

VAL_AV_VISIBLE = "visible"
VAL_AV_HIDDEN = "hidden"
VAL_AV_ALL = "all"
VAL_AV_DUAL = "dual"

KEY_TOP_PICKS_COLUMN = "top-picks-column"
KEY_RATING_COLUMN = "rating-column"
KEY_DATE_ADDED_COLUMN = "date-added-column"
KEY_FILE_SIZE_COLUMN = "file-size-column"
KEY_AUDIO_FORMAT_COLUMN = "audio-format-column"

KEY_PRELOAD_NEXT_TRACK = "preload-next-track"
KEY_PRELOAD_PREV_TRACK = "preload-prev-track"
KEY_PRELOAD_HIDDEN_TRACK = "preload-hidden-track"

KEY_DETECT_DIRS_IGNORE_CASE = "detect-dirs-ignore-case"
KEY_DETECT_FILES_IGNORE_CASE = "detect-files-ignore-case"


Secret = None
if rbconfig.libsecret_enabled:
    try:
        import gi
        gi.require_version('Secret', '1')
        from gi.repository import Secret
    except ImportError:
        pass


class Account(metaclass=SingletonMeta):
    def __init__(self, plugin=None):
        self.plugin = plugin
        self.activated = False
        self.settings = None
        self.secret = None

    def unlock_keyring(self):
        schema_test = Secret.Schema.new('org.gnome.rhythmbox.plugins.telegram-test', Secret.SchemaFlags.DONT_MATCH_NAME,
                                        {"test": Secret.SchemaAttributeType.STRING})
        return Secret.password_store_sync(schema_test, {"test": "test"}, Secret.COLLECTION_DEFAULT, "test", 'test', None)

    def init(self):
        if self.activated:
            return
        self.activated = True

        schema_source = Gio.SettingsSchemaSource.get_default()
        schema = schema_source.lookup('org.gnome.rhythmbox.plugins.telegram', False)
        self.settings = Gio.Settings.new_full(schema, None, None)

        if Secret is None:
            print("You need to install libsecret for secure storage of Telegram secret keys")
            show_error("You need to install libsecret for secure storage of Telegram secret keys",
                       "Due to the absence of libsecret, Telegram secret keys will be stored in plaintext in the Gnome GSettings")
        else:
            self.unlock_keyring()
            self.schema = Secret.Schema.new('org.gnome.rhythmbox.plugins.telegram', Secret.SchemaFlags.DONT_MATCH_NAME,
                {"rhythmbox-plugin": Secret.SchemaAttributeType.STRING})
            self.keyring_attributes = {"rhythmbox-plugin": "telegram"}
            self.secret_service = Secret.Service.get_sync(Secret.ServiceFlags.OPEN_SESSION, None)
            items = self.secret_service.search_sync(self.schema, self.keyring_attributes,
                Secret.SearchFlags.LOAD_SECRETS, None)
            if not items or len(items) == 0 or not items[0].get_secret():
                print("Couldn't find an existing keyring entry")
                return
            self.secret = items[0].get_secret().get().decode("utf-8")

    def get_secure(self, key=None):
        def _get_all():
            if self.secret is None:
                connected = self.settings[KEY_CONNECTED]
                return self.settings[KEY_API_ID], self.settings[KEY_API_HASH], self.settings[KEY_PHONE], \
                    connected is True or connected == 'True'
            try:
                (api_id, api_hash, phone, connected) = self.secret.split("\n")
                if not api_id or not api_hash or not phone:
                    connected = False
                return api_id, api_hash, phone, connected is True or connected == 'True'
            except ValueError:
                return '', '', '', False

        props = _get_all()
        if key:
            keys = {
                KEY_API_ID: 0,
                KEY_API_HASH: 1,
                KEY_PHONE: 2,
                KEY_CONNECTED: 3,
            }
            if key in keys:
                return props[keys[key]]
        return props

    def get_library_path(self):
        # from settings
        if KEY_LIBRARY_PATH in self.settings and self.settings[KEY_LIBRARY_PATH]:
            return self.settings[KEY_LIBRARY_PATH]
        # from rhythmbox global settings
        locations = self.plugin.rhythmdb_settings.get_strv('locations')
        if locations and len(locations):
            path = locations[0]
        # get default music path
        else:
            path = os.path.expanduser('~/Music')
        return re.sub(r'^file://', '', path)

    def update(self, api_id, api_hash, phone, connected=False):
        if not api_id or not api_hash or not phone:
            connected = False
        connected = connected is True or connected == 'True'
        if Secret is None:
            print("No secret, use default storage")
            self.settings.set_string(KEY_API_ID, api_id)
            self.settings.set_string(KEY_API_HASH, api_hash)
            self.settings.set_string(KEY_PHONE, phone)
            self.settings.set_boolean(KEY_CONNECTED, connected)
            return
        secret = '\n'.join((api_id, api_hash, phone, str(connected)))
        if secret == self.secret:
            return
        self.secret = secret
        result = Secret.password_store_sync(self.schema, self.keyring_attributes, Secret.COLLECTION_DEFAULT,
            "Rhythmbox: Telegram credentials", secret, None)
        if not result:
            print("Couldn't create keyring item!")

    def set_connected(self, connected):
        api_id, api_hash, phone, connected_ = self.get_secure()
        self.update(api_id, api_hash, phone, connected)
