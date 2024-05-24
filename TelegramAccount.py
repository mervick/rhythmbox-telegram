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

import os
import re
from rb import rbconfig # noqa
from common import SingletonMeta, show_error

Secret = None
if rbconfig.libsecret_enabled:
    try:
        import gi
        gi.require_version('Secret', '1')
        from gi.repository import Secret
    except ImportError:
        pass


class TelegramAccount(metaclass=SingletonMeta):
    def __init__(self, plugin=None):
        self.settings = plugin.settings
        self.plugin = plugin
        self.secret = None

        if Secret is None:
            print("You need to install libsecret for secure storage of Telegram secret keys")
            show_error("You need to install libsecret for secure storage of Telegram secret keys",
                       "Due to the absence of libsecret, Telegram secret keys will be stored in plaintext in the Gnome GSettings")

        if Secret is not None:
            self.schema = Secret.Schema.new('org.gnome.rhythmbox.plugins.telegram', Secret.SchemaFlags.DONT_MATCH_NAME,
                {"rhythmbox-plugin": Secret.SchemaAttributeType.STRING})
            self.keyring_attributes = {"rhythmbox-plugin": "telegram"}
            self.secret_service = Secret.Service.get_sync(Secret.ServiceFlags.OPEN_SESSION, None)
            items = self.secret_service.search_sync(self.schema, self.keyring_attributes,
                Secret.SearchFlags.LOAD_SECRETS, None)
            if not items:
                print("Couldn't find an existing keyring entry")
                return
            self.secret = items[0].get_secret().get().decode("utf-8")

    def get_secure(self, key=None):
        def _get_all():
            if self.secret is None:
                connected = self.settings['connected']
                return self.settings['api-id'], self.settings['api-hash'], self.settings['phone'], \
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
                "api_id": 0,
                "api_hash": 1,
                "phone": 2,
                "connected": 3,
            }
            if key in keys:
                return props[keys[key]]
        return props

    def get_library_path(self):
        # from settings
        if 'library-path' in self.settings and self.settings['library-path']:
            return self.settings['library-path']
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
            self.settings.set_string('api-id', api_id)
            self.settings.set_string('api-hash', api_hash)
            self.settings.set_string('phone', phone)
            self.settings.set_boolean('connected', connected)
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
