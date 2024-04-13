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

import gi
gi.require_version('Gtk', '3.0')
import json
import re
import rb
from gi.repository import RB
from gi.repository import GObject, Gtk, Gio, Peas, PeasGtk, GLib, Gdk
from telegram.client import AuthorizationState
from DialogCode import DialogCode
from TelegramApi import TelegramApi, TelegramAuthError, TelegramAuthStateError
import TelegramAccount
from SearchList import SearchListBox

# import gettext
# gettext.install('rhythmbox', RB.locale_dir())

__config = None
__settings = None

def account(cfg=None):
    global __config
    global __settings
    if cfg:
        __config = cfg
        __settings = cfg.settings
    return TelegramAccount.instance(__settings)

def config():
    global __config
    return __config

def safe_cast(val, to_type, default=None):
    try:
        return to_type(val)
    except (ValueError, TypeError):
        return default


class PrefsPage(GObject.GObject):
    def __init__(self, prefs, name=None, ui_file=None, main_box=None):
        self.box = Gtk.Box(hexpand=True)
        # init vars
        self._changes = {}
        self.has_errors = []
        # set custom values
        self.prefs = prefs
        if name is not None:
            self.name = name
        if ui_file is not None:
            self.ui_file = ui_file
        if main_box is not None:
            self.main_box = main_box
        # init UI
        self.box.set_border_width(5)
        self.ui = Gtk.Builder()
        self.ui.add_from_file(prefs.find_plugin_file(self.ui_file))
        self.pre_init_page()
        self.register_callbacks()

    def register_callbacks(self):
        pass

    def create_widget(self):
        self.init_page()
        self.box.add(self.get_main_object())

    def set_error(self, widget, is_error=True):
        if is_error:
            self.has_errors.append(widget)
            widget.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, 'error')
        else:
            widget.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

    def clear_errors(self):
        if self.has_errors:
            for widget in self.has_errors:
                self.set_error(widget, False)
            self.has_errors.clear()

    def show_error(self, title, description=None):
        err_dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, title)
        if description is not None:
            err_dialog.format_secondary_text(str(description))
        err_dialog.set_application(Gio.Application.get_default())
        err_dialog.run()
        err_dialog.destroy()

    def on_change(self, name, value):
        txt = json.dumps(value)
        if name not in self._changes or self._changes[name] != txt:
            self._changes[name] = txt
            config().emit('reload_sources')

    def get_main_object(self):
        return self.ui.get_object(self.main_box)

    def pre_init_page(self):
        pass

    def init_page(self):
        pass


class ChannelsPrefsPage(PrefsPage):
    name = _('Music Channels')
    main_box = 'channels_vbox'
    ui_file = 'ui/prefs/channels.ui'

    def on_list_box_change(self, v):
        self.prefs.settings.set_string('channels', json.dumps(v))
        self.on_change("channels", [channel["id"] for channel in v])

    def on_channels_clear(self, obj=None):
        print('on_channels_clear')
        self.search_list_box.reset()
        self.prefs.account.settings.set_string('channels', '[]')

    def on_channels_reload(self, obj=None):
        print('on_channels_reload')
        selected = json.loads(self.prefs.account.settings['channels'])
        self.search_list_box.set_selected(selected)

    def on_channels_fetch(self, obj=None):
        print('on_channels_fetch')
        def _set_chats(chats):
            self.search_list_box.clear_list()
            self.search_list_box.set_items(list(chats.values()))
            # @TODO add spinner?
#             self.loading = False
#             upd_spinner()
        self.prefs.api.get_chats_idle(_set_chats)

    def register_callbacks(self):
        self.prefs.connect('channels-clear', self.on_channels_clear)
        self.prefs.connect('channels-reload', self.on_channels_reload)
        self.prefs.connect('channels-fetch', self.on_channels_fetch)

    def pre_init_page(self):
        popover = self.ui.get_object("channels_popover")
        placeholder = self.ui.get_object("list_box_placeholder")
        search_entry = self.ui.get_object("search_entry")

        list_frame = self.ui.get_object("list_frame")
        empty_label = self.ui.get_object("empty_label")
        channels_list_box = self.ui.get_object("channels_list_box")
        channels_flow_box = self.ui.get_object("channels_flow_box")

#         channel_box = self.ui.get_object("channel_box")
#         channel_wrap = self.ui.get_object('channel_wrap_box')

        search_list_box = SearchListBox(search_entry, placeholder, channels_flow_box, channels_list_box, list_frame, empty_label)
        search_list_box.connect_on_change(self.on_list_box_change)
        self.search_list_box = search_list_box

        add_chat_btn = self.ui.get_object("add_chat_btn")
        add_chat_btn.set_popover(popover)


class ConnectPrefsPage(PrefsPage):
    name = _('Connect')
    main_box = 'connect_vbox'
    ui_file = 'ui/prefs/connect.ui'

    loading = None
    spinner = None
    api = None

    def init_page(self):
        settings_box = self.ui.get_object('connect_vbox')
        logo = self.ui.get_object("logo")
        api_id_entry = self.ui.get_object("api_id_entry")
        api_hash_entry = self.ui.get_object("api_hash_entry")
        phone_entry = self.ui.get_object("phone_number_entry")
        connect_btn = self.ui.get_object("connect_btn")
        details_box = self.ui.get_object('details_box')
        helpbox_wrap = self.ui.get_object('helpbox_wrap')
        helpbox = self.ui.get_object('helpbox')

        def update_connect(connected=None):
            self.on_change("connected", connected)
            if connected is not None:
                self.connected = connected
            else:
                connected = self.connected
            enabled = not self.loading and not connected
            upd_spinner()
            details_box.set_sensitive(enabled)
            helpbox.set_sensitive(enabled)
            connect_btn.set_sensitive(not self.loading)
            btn_label = _('Connect') if not connected else _('Disconnect')

            if self.loading:
                btn_label = _('Disconnecting...') if not connected else _('Connecting...')
            connect_btn.set_label(btn_label)
            # @TODO enable/disable prefs pages
#             channel_box.set_sensitive(not self.loading and not enabled)

#             if enabled and not self.loading:
#                 if self.removed_help:
#                     self.removed_help = False
#                     settings_box.pack_start(helpbox, True, True, 0)
#             elif not self.removed_help:
#                 self.removed_help = True
#                 settings_box.remove(helpbox)

            return connected

        def fill_account_details():
            # helpbox.set_size_request(450, -1)
            logo.set_size_request(500, -1)
            (api_id, api_hash, phone_number, connected) = self.prefs.account.get_secure()

            if connected:
                print('emit.channels-reload')
                self.prefs.emit('channels-reload')
#                 selected = json.loads(account().settings['channels'])
#                 search_list_box.set_selected(selected)

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
            # @TODO fixme
            print('upd_spinner')
            return
            if self.loading:
                if self.spinner is None:
                    helpbox_wrap.set_property('height_request', 80)
                    self.spinner = Gtk.Spinner()
                    helpbox_wrap.pack_start(self.spinner, True, True, 0)
                    helpbox_wrap.remove(helpbox)
                self.spinner.show()
                self.spinner.start()
            elif self.loading is not None:
                helpbox_wrap.set_property('height_request', -1)
                if self.spinner:
                    self.spinner.stop()
                    helpbox_wrap.remove(self.spinner)
                self.spinner = None
                if self.connected:
                    helpbox_wrap.pack_start(helpbox, True, True, 0)
            elif not self.connected:
                self.loading = False
                helpbox_wrap.set_property('height_request', 40)
                self.spinner = Gtk.Spinner()
                helpbox_wrap.pack_start(self.spinner, True, True, 0)
                helpbox_wrap.remove(helpbox)
                self.spinner.show()

        def connect_btn_clicked(event):
            self.loading = True
            if update_connect(not self.connected):
                connect_api()
            else:
                disconnect_api()

        def set_state(state):
            self.loading = False
            update_connect(state)
            self.prefs.account.set_connected(state)

            if state:
                print('emit.channels-fetch')
                self.prefs.emit('channels-fetch')
#                 self.loading = True
#                 upd_spinner()
#
#                 def _set_chats(chats):
#                     search_list_box.clear_list()
#                     search_list_box.set_items(list(chats.values()))
#                     self.loading = False
#                     upd_spinner()
#
#                 self.api.get_chats_idle(_set_chats)

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
                self.show_error(_('Validation error'), errors[0])
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
                            self.show_error(_("Unable to login Telegram"), _('Login code is required'))
                            set_state(False)

                        DialogCode(self, connect_api, unable_to_login)
                        return
                    else:
                        self.show_error(_("Unable to login Telegram"), e)
                except TelegramAuthError as e:
                    err = self.api.get_error()
                    self.show_error(_("Unable to login Telegram"), err if err else e)
                except RuntimeError as e:
                    self.show_error(_("Unable to login Telegram"), e)

                set_state(self.api.state == AuthorizationState.READY)
            else:
                set_state(False)

        def disconnect_api():
            print('emit.channels-clear')
            self.prefs.emit('channels-clear')
#             search_list_box.reset()
            self.api.reset_chats()
#             account().settings.set_string('channels', '[]')
            set_state(False)

        self.ui.connect_signals({"connect_btn_clicked_cb": connect_btn_clicked})
        api_id_entry.connect("focus-out-event", account_details_changed)
        api_hash_entry.connect("focus-out-event", account_details_changed)
        phone_entry.connect("focus-out-event", account_details_changed)

        fill_account_details()
        upd_spinner()


class SettingsPrefsPage(PrefsPage):
    name = _('Settings')
    main_box = 'settings_vbox'
    ui_file = 'ui/prefs/settings.ui'


class TempPrefsPage(PrefsPage):
    name = _('Temporary Files')
    main_box = 'temp_vbox'
    ui_file = 'ui/prefs/temp.ui'


class TelegramConfig(GObject.GObject, PeasGtk.Configurable):
    __gtype_name__ = 'TelegramConfig'
    object = GObject.property(type=GObject.GObject)
    loading = None
    spinner = None
    parent = None
    api = None
    removed_help = False
    _changes = {}

    __gsignals__ = {
        'channels-clear' : (GObject.SignalFlags.RUN_FIRST, None, ()),
        'channels-reload' : (GObject.SignalFlags.RUN_FIRST, None, ()),
        'channels-fetch' : (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.shell = self.object
        self.account = account()
        self.settings = self.account.settings

    def find_plugin_file(self, file):
        return rb.find_plugin_file(self, file)

    def do_create_configure_widget(self):
        # Create Notebook
        main_box = Gtk.Box()
        self.main_box = main_box
        main_box.set_border_width(5)
        notebook = Gtk.Notebook(vexpand=True, hexpand=True)
        main_box.add(notebook)
#         self.add(self.notebook)

        page1 = ConnectPrefsPage(prefs=self)
        page2 = ChannelsPrefsPage(prefs=self)
        page3 = SettingsPrefsPage(prefs=self)
        page4 = TempPrefsPage(prefs=self)

        page1.register_callbacks()
        page2.register_callbacks()
        page3.register_callbacks()
        page4.register_callbacks()

        page1.create_widget()
        page2.create_widget()
        page3.create_widget()
        page4.create_widget()

        notebook.append_page(page1.box, Gtk.Label(page1.name))
        notebook.append_page(page2.box, Gtk.Label(page2.name))
        notebook.append_page(page3.box, Gtk.Label(page3.name))
        notebook.append_page(page4.box, Gtk.Label(page4.name))

        GLib.timeout_add(1000, self.update_window)

        return main_box

    def get_center(self):
        self.parent = self.main_box.get_toplevel().get_property('window')
        position = self.parent.get_position()
        geometry = self.parent.get_geometry()
        left_center = round(position.x + (geometry.width - geometry.x) / 2)
        top_center = round(position.y + (geometry.height - geometry.y) / 2)
        return {"x": left_center, "y": top_center}

    def update_window(self):
        gtk_win = self.main_box.get_toplevel()
#         gtk_win = settings_box.get_toplevel()
        gtk_win.set_default_size(500, 600)
        gtk_win.set_resizable(False)
        donate_btn = gtk_win.add_button("Donate", Gtk.ResponseType.HELP)
        style_context = donate_btn.get_style_context()
        style_context.add_class('suggested-action')
        gtk_win.set_border_width(5)
        box = gtk_win.get_content_area()
        box.set_spacing(2)

GObject.type_register(TelegramConfig)
