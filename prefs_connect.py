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

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
from telegram.client import AuthorizationState
from auth_dialog import AuthDialog
from account import KEY_CONNECTED
from telegram_client import TelegramApi, TelegramAuthError, TelegramAuthStateError
from prefs_base import PrefsPageBase
from common import show_error


def safe_cast(val, to_type, default=None):
    try:
        return to_type(val)
    except (ValueError, TypeError):
        return default


class PrefsConnectPage(PrefsPageBase):
    name = _('Connect')
    main_box = 'connect_vbox'
    ui_file = 'ui/prefs/connect.ui'

    loading = None
    spinner = None
    api = None

    def _create_widget(self):
        logo = self.ui.get_object("logo")
        api_id_entry = self.ui.get_object("api_id_entry")
        api_hash_entry = self.ui.get_object("api_hash_entry")
        phone_entry = self.ui.get_object("phone_number_entry")
        connect_btn = self.ui.get_object("connect_btn")
        connect_status = self.ui.get_object("connect_status")
        details_box = self.ui.get_object('details_box')
        helpbox_wrap = self.ui.get_object('helpbox_wrap')
        helpbox = self.ui.get_object('helpbox')

        def update_connect(connected=None):
            self.on_change(KEY_CONNECTED, connected)
            if connected is not None:
                self.connected = connected
            else:
                connected = self.connected

            not_connected_sensitive = not self.loading and not connected
            connected_sensitive = not self.loading and connected

            self.prefs.page2.set_sensitive(connected_sensitive)
            self.prefs.page3.set_sensitive(connected_sensitive)
            self.prefs.page4.set_sensitive(connected_sensitive)
            self.prefs.page5.set_sensitive(connected_sensitive)

            details_box.set_sensitive(not_connected_sensitive)
            helpbox.set_sensitive(not_connected_sensitive)

            upd_spinner()

            connect_btn.set_sensitive(not self.loading)
            status = _('Connected ✅') if connected_sensitive else _('Not Connected ❌')

            if self.loading:
                btn_label = _('Disconnecting...') if not connected else _('Connecting...')
            else:
                btn_label = _('Connect') if not connected else _('Disconnect')

            connect_btn.set_label(btn_label)
            connect_status.set_markup('<small>%s: %s</small>' % (_('Status'), status))

            return connected

        def fill_account_details():
            logo.set_size_request(500, -1)
            (api_id, api_hash, phone_number, connected) = self.prefs.account.get_secure()

            if connected:
                self.prefs.emit('channels-reload')

            api_id_entry.set_text(api_id or "")
            api_hash_entry.set_text(api_hash or "")
            phone_entry.set_text(phone_number or "")

            update_connect(connected)

            if connected:
                self.loading = True
                connect_api()

        def account_details_changed(entry, event):
            api_id = re.sub("\D", "", api_id_entry.get_text())
            api_hash = api_hash_entry.get_text().strip()
            phone_number = re.sub("(?!(^\+)|\d).", "", phone_entry.get_text())
            api_id_entry.set_text(api_id)
            api_hash_entry.set_text(api_hash)
            phone_entry.set_text(phone_number)
            self.prefs.account.update(api_id, api_hash, phone_number)
            self.clear_errors()

        def upd_spinner():
            if self.loading:
                if self.spinner is None:
                    helpbox_wrap.set_property('height_request', 80)
                    self.spinner = Gtk.Spinner()
                    helpbox_wrap.pack_start(self.spinner, True, True, 0)
                    helpbox_wrap.remove(helpbox)
                self.spinner.show()
                self.spinner.start()
            elif self.loading is False:
                helpbox_wrap.set_property('height_request', -1)
                if self.spinner:
                    self.spinner.stop()
                    helpbox_wrap.remove(self.spinner)
                self.spinner = None
                if helpbox.get_parent() is None:
                    helpbox_wrap.pack_start(helpbox, True, True, 0)
                self.loading = None

        def connect_btn_clicked(event):
            self.loading = True
            if update_connect(not self.connected):
                connect_api()
            else:
                disconnect_api()

        def set_state(state, init_connection=False):
            self.loading = False
            update_connect(state)
            self.prefs.account.set_connected(state)

            if state:
                if init_connection:
                    self.prefs.plugin.connect_api()
                self.prefs.emit('api-connect')
                self.prefs.emit('channels-fetch')

            else:
                self.prefs.emit('api-disconnect')

            return state

        def validate(api_id, api_hash, phone_number):
            errors = []
            if not api_id:
                self.set_error(api_id_entry)
                errors.append(_('API Id is required'))
            if not api_hash:
                self.set_error(api_hash_entry)
                errors.append(_('API Hash is required'))
            if safe_cast(api_id, int) is None:
                self.set_error(api_id_entry)
                errors.append(_('API Id must be integer'))
            if not phone_number:
                self.set_error(phone_entry)
                errors.append(_('The phone number is required'))
            if not re.search('^\+?\d{10,14}$', phone_number):
                self.set_error(phone_entry)
                errors.append(_('The phone number is invalid'))
            if errors:
                show_error(_('Validation error'), errors[0], parent=self.box)
                return False

            return True

        def connect_api(code=None):
            (api_id, api_hash, phone_number, connected) = self.prefs.account.get_secure()

            if validate(api_id, api_hash, phone_number):
                self.api = TelegramApi.api(api_id, api_hash, phone_number)
                self.prefs.api = self.api

                try:
                    self.api.login(code)
                except TelegramAuthStateError as e:
                    if self.api.state == AuthorizationState.WAIT_CODE:
                        def unable_to_login():
                            show_error(_("Unable to login Telegram"), _('Login code is required'), parent=self.box)
                            set_state(False)

                        AuthDialog(self, connect_api, unable_to_login)
                        return
                    else:
                        show_error(_("Unable to login Telegram"), e, parent=self.box)
                except TelegramAuthError as e:
                    err = self.api.get_error()
                    show_error(_("Unable to login Telegram"), err if err else e, parent=self.box)
                except RuntimeError as e:
                    show_error(_("Unable to login Telegram"), e, parent=self.box)

                set_state(self.api.state == AuthorizationState.READY, True)
            else:
                set_state(False)

        def disconnect_api():
            self.prefs.emit('channels-clear')
            self.api.reset_chats()
            set_state(False)

        self.ui.connect_signals({"connect_btn_clicked_cb": connect_btn_clicked})
        api_id_entry.connect("focus-out-event", account_details_changed)
        api_hash_entry.connect("focus-out-event", account_details_changed)
        phone_entry.connect("focus-out-event", account_details_changed)

        fill_account_details()
        upd_spinner()
