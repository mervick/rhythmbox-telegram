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

import functools
import json
import re
import rb
from gi.repository import RB
from gi.repository import GObject, Gtk, Gio, Peas, PeasGtk, GLib, Gdk
from telegram.client import AuthorizationState
from DialogCode import DialogCode
from TelegramApi import TelegramApi, TelegramAuthError, TelegramAuthStateError
import TelegramAccount

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

# COLOR_INVALID = Color(50000, 0, 0)


class SearchListBox:
    def __init__(self, entry, list_box, flow_box, channels_list_box, list_frame, empty_label):
        self.entry = entry
        self.list_box = list_box
        self.flow_box = flow_box
        self.channels_list_box = channels_list_box
        self.list_frame = list_frame
        self.empty_label = empty_label
        self.items = []
        self.query = None
        self.selected = []
        self.on_change = None
        self.entry.connect("search-changed", self.search)

    def connect_on_change(self, on_change):
        self.on_change = on_change

    def _on_change(self):
        if self.on_change:
            self.on_change(self.selected)

    def set_selected(self, selected):
        self.clear_selected()
        if selected:
            for item in selected:
                self.add_selected(item)

    def clear_selected(self):
        if len(self.selected):
            self.selected = []
            self._remove_all_selected()
        self._on_change()

    def _remove_all_selected(self):
        self.selected = []
        for widget in self.flow_box.get_children():
            self.flow_box.remove(widget)
        self.list_frame.remove(self.channels_list_box)
        self.list_frame.add(self.empty_label)

    def remove_selected(self, widget, selected):
        items = []
        for item in self.selected:
            if item["id"] == selected["id"]:
                # del self.selected[i]
                # self.selected = list(self.selected)
                self.flow_box.remove(widget)
                # return
            else:
                items.append(item)
        self.selected = items
        if not len(self.selected):
            self._remove_all_selected()
        self._on_change()

    def add_selected(self, selected):
        for item in self.selected:
            if item["id"] == selected["id"]:
                return
        _selected = {"id": selected["id"], "title": selected["title"]}
        self.selected.append(_selected)
        if len(self.selected) == 1:
            self.list_frame.remove(self.empty_label)
            self.list_frame.add(self.channels_list_box)
            self.flow_box.set_property('homogeneous', False)
            self.flow_box.set_property('hexpand', True)
        btn = Gtk.ModelButton(label=_selected['title'], visible=True)
        btn.set_alignment(0, 0.5)
        btn.connect("clicked", lambda e: self.remove_selected(btn, _selected))
        self.flow_box.add(btn)
        self._on_change()

    def search(self, event=None, force=False):
        query = self.entry.get_text().strip()
        # self.entry.set_text(query)
        if self.query != query or force:
            self.query = query
            self.clear_list()
            if query:
                query_casefold = query.casefold()
                for item in self.items:
                    # if item['title'].find(query) != -1:
                    # if query_casefold in item['title'].casefold():
                    if query_casefold in item['casefold']:
                        self._add_item(item)
            else:
                for item in self.items:
                    self._add_item(item)

    def set_items(self, items):
        self.items = []
        for item in items:
            self.add(item, update=False)
            # if item not in self.items and item["title"]:
            #     self.add(item)
        self._sort()
        self.search(force=True)

    def _sort(self):
        # self.items = sorted(self.items, key=functools.cmp_to_key(lambda a, b: 1 if a["casefold"] > b["casefold"] else -1))
        self.items.sort(key=functools.cmp_to_key(lambda a, b: 1 if a["casefold"] > b["casefold"] else -1))

    def add(self, item, update=True):
        if item["title"]:
            exists = False
            for item_have in self.items:
                if item_have["id"] == item["id"]:
                    exists = True
                    break
            if not exists:
                item = dict(item)
                item["casefold"] = item["title"].casefold()
                self.items.append(item)
                # self._add_item(item)
        if update:
            self._sort()
            self.search()

    def select_clicked_cb(self, event, item_id):
        # print('clicked_cb %s ', item_id)
        selected = filter(lambda i: i["id"] == item_id, self.items)
        # print(selected)
        self.add_selected(list(selected)[0])

    def _add_item(self, item):
        btn = Gtk.ModelButton(label=item['title'], visible=True)
        btn.connect("clicked", lambda e: self.select_clicked_cb(e, item['id']))
        btn.set_alignment(0, 0.5)
        self.list_box.pack_start(btn, False, False, 0)

    def clear_list(self):
        for widget in self.list_box.get_children():
            self.list_box.remove(widget)

    def reset(self):
        self.query = None
        self.items = []
        self.selected = []
        self.entry.set_text('')
        self.search(force=True)

# class Prefs(GObject.GObject):
#     def __init__(self, configurable):
#         GObject.GObject.__init__(self)
#         self.config = configurable

class PrefsDialog(Gtk.Dialog):
    def __init__(self, parent):
        self.config = parent
        Gio.Application.get_default()
#         super().__init__(title="My Dialog", transient_for=parent, flags=0)
        super().__init__(title="My Dialog", flags=0)
        self.init_dialog()

    def init_dialog(self):
        self.add_button("_Close", Gtk.ResponseType.CLOSE)
        donate_btn = self.add_button("Donate", Gtk.ResponseType.HELP)
        style_context = donate_btn.get_style_context()
        style_context.add_class('suggested-action')

#         self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
#                          Gtk.STOCK_OK, Gtk.ResponseType.OK)

#         self.set_title("Telegram Preferences")
#         self.set_resizable(False)
        self.set_default_size(500, 800)

        label = Gtk.Label(label="This is a dialog to display additional information")

        box = self.get_content_area()
        box.add(label)

        # Create Notebook
        self.notebook = Gtk.Notebook(vexpand=True)
        box.add(self.notebook)

        # Create Boxes
        self.page1 = Gtk.Box()
        self.page1.set_border_width(50)
        self.page1.add(Gtk.Label("Welcome to Geeks for Geeks"))
        self.notebook.append_page(self.page1, Gtk.Label("Click Here 1"))

        self.page2 = Gtk.Box()
        self.page2.set_border_width(50)
        self.page2.add(Gtk.Label("A computer science portal for geeks"))
        self.notebook.append_page(self.page2, Gtk.Label("Click Here 2"))

        self.show_all()

    def init_dialog1(self):
#         btns_ui = Gtk.Builder()
#         btns_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs/btns.ui"))

#         box = Gtk.Box()
#         button1 = Gtk.Button(label="Close")
#         button2 = Gtk.Button(label="Donate")
#
#         button1_style_context = button1.get_style_context()
#         button1_style_context.add_class('suggested-action')

#         self.add(box)
        self.set_default_size(500, 800)

        label = Gtk.Label(label="This is a dialog to display additional information")

        box = self.get_content_area()
        box.add(label)
#         box.pack_end(button1, True, False, 0)
#         box.pack_end(button2, True, False, 0)
        self.show_all()


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

    def get_center(self):
        self.parent = self.get_main_object().get_toplevel().get_property('window')
        position = self.parent.get_position()
        geometry = self.parent.get_geometry()
        left_center = round(position.x + (geometry.width - geometry.x) / 2)
        top_center = round(position.y + (geometry.height - geometry.y) / 2)
        return {"x": left_center, "y": top_center}

    def get_main_object(self):
        return self.ui.get_object(self.main_box)

    def init_page(self):
        pass


class ChannelsPrefsPage(PrefsPage):
    name = _('Music Channels')
    main_box = 'channels_vbox'
    ui_file = 'ui/prefs/channels.ui'

    def on_list_box_change(self, v):
        self.prefs.settings.set_string('channels', json.dumps(v))
        self.on_change("channels", [channel["id"] for channel in v])

    def on_channels_clear(self):
        self.search_list_box.reset()
        self.prefs.account.settings.set_string('channels', '[]')

    def on_channels_reload(self):
        selected = json.loads(self.prefs.account.settings['channels'])
        self.search_list_box.set_selected(selected)

    def on_channels_fetch(self):
        def _set_chats(chats):
            self.search_list_box.clear_list()
            self.search_list_box.set_items(list(chats.values()))
            # @TODO add spinner?
#             self.loading = False
#             upd_spinner()
        self.prefs.api.get_chats_idle(_set_chats)

    def init_page(self):
        self.prefs.connect('channels-clear', self.on_channels_clear)
        self.prefs.connect('channels-reload', self.on_channels_reload)
        self.prefs.connect('channels-fetch', self.on_channels_fetch)

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
        'channels-clear' : (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
#         'channels-set' : (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (GObject.TYPE_PYOBJECT,)),
        'channels-reload' : (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
        'channels-fetch' : (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.shell = self.object
        self.account = account()
        self.settings = self.account.settings

    def find_plugin_file(self, file):
        return rb.find_plugin_file(self, file)

    def do_create_configure_widget(self):
#         PrefsDialog(self)
#         Gdk.threads_add_timeout(GLib.PRIORITY_DEFAULT_IDLE, 5000, add_btn, None)

        # Create Notebook
        main_box = Gtk.Box()
        main_box.set_border_width(5)
        notebook = Gtk.Notebook(vexpand=True, hexpand=True)
        main_box.add(notebook)
#         self.add(self.notebook)

        page = ConnectPrefsPage(prefs=self)
        notebook.append_page(page.box, Gtk.Label(page.name))

        # Create Boxes
        depr_cnnct_page = Gtk.Box(hexpand=True)
        depr_cnnct_page.set_border_width(5)
        notebook.append_page(depr_cnnct_page, Gtk.Label("Connect"))

        connect_page = Gtk.Box(hexpand=True)
        connect_page.set_border_width(5)
        notebook.append_page(connect_page, Gtk.Label("Connect"))

        channels_page = Gtk.Box(hexpand=True)
        channels_page.set_border_width(5)
        notebook.append_page(channels_page, Gtk.Label("Music channels"))

        settings_page = Gtk.Box(hexpand=True)
        settings_page.set_border_width(5)
        notebook.append_page(settings_page, Gtk.Label("Settings"))

        temp_page = Gtk.Box(hexpand=True)
        temp_page.set_border_width(5)
        notebook.append_page(temp_page, Gtk.Label("Temp files"))

        depr_cnnct_page_ui = Gtk.Builder()
        settings_page_ui = Gtk.Builder()
        channels_page_ui = Gtk.Builder()
        temp_page_ui = Gtk.Builder()

        depr_cnnct_page_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs/connect.ui"))
        settings_page_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs/settings.ui"))
        channels_page_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs/channels.ui"))
#         channels_page_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs/chn.ui"))
        temp_page_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs/temp.ui"))

        connect_page.add(depr_cnnct_page_ui.get_object('connect_vbox'))
        settings_page.add(settings_page_ui.get_object('settings_vbox'))
        channels_page.add(channels_page_ui.get_object('channels_vbox'))
        temp_page.add(temp_page_ui.get_object('temp_vbox'))

        prefs_ui = Gtk.Builder()
        popup_ui = Gtk.Builder()
        prefs_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs5.ui"))
#         prefs_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs5.ui"))
#         prefs_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs6.ui"))
        popup_ui.add_from_file(rb.find_plugin_file(self, "ui/popup.ui"))

        popover = popup_ui.get_object("main_menu_popover")
        list_box = popup_ui.get_object("list_box")
        search_entry = popup_ui.get_object("search_entry")

        list_frame = prefs_ui.get_object("list_frame")
        empty_label = prefs_ui.get_object("empty_label")
        channels_list_box = prefs_ui.get_object("channels_list_box")
        channels_flow_box = prefs_ui.get_object("channels_flow_box")

        settings_box = prefs_ui.get_object('telegram_vbox')
        logo = prefs_ui.get_object("logo")
        api_id_entry = prefs_ui.get_object("api_id_entry")
        api_hash_entry = prefs_ui.get_object("api_hash_entry")
        phone_entry = prefs_ui.get_object("phone_number_entry")
        connect_btn = prefs_ui.get_object("connect_btn")
        details_box = prefs_ui.get_object('details_box')
        helpbox = prefs_ui.get_object('helpbox')
        channel_box = prefs_ui.get_object("channel_box")
        channel_wrap = prefs_ui.get_object('channel_wrap_box')

        def listbox_change(v):
            account().settings.set_string('channels', json.dumps(v))
            on_change("channels", [channel["id"] for channel in v])

        search_list_box = SearchListBox(search_entry, list_box, channels_flow_box, channels_list_box, list_frame, empty_label)
        search_list_box.connect_on_change(listbox_change)

        add_chat_btn = prefs_ui.get_object("add_chat_btn")
        add_chat_btn.set_popover(popover)

        has_errors = []

        def on_change(name, value):
            txt = json.dumps(value)
            if name not in self._changes or self._changes[name] != txt:
                self._changes[name] = txt
                config().emit('reload_sources')

        def clear_errors():
            if has_errors:
                for widget in has_errors:
                    set_error(widget, False)
                has_errors.clear()

        def set_error(widget, is_error=True):
            if is_error:
                has_errors.append(widget)
                widget.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, 'error')
            else:
                widget.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

        def update_connect(connected=None):
            on_change("connected", connected)
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

            channel_box.set_sensitive(not self.loading and not enabled)

            if enabled and not self.loading:
                if self.removed_help:
                    self.removed_help = False
                    settings_box.pack_start(helpbox, True, True, 0)
            elif not self.removed_help:
                self.removed_help = True
                settings_box.remove(helpbox)

            return connected

        def fill_account_details():
            # helpbox.set_size_request(450, -1)
            logo.set_size_request(500, -1)
            (api_id, api_hash, phone_number, connected) = account().get_secure()

            if connected:
                selected = json.loads(account().settings['channels'])
                search_list_box.set_selected(selected)

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
            account().update(api_id, api_hash, phone_number)
            clear_errors()

        def upd_spinner():
            if self.loading:
                if self.spinner is None:
                    channel_wrap.set_property('height_request', 80)
                    self.spinner = Gtk.Spinner()
                    channel_wrap.pack_start(self.spinner, True, True, 0)
                    channel_wrap.remove(channel_box)
                self.spinner.show()
                self.spinner.start()
            elif self.loading is not None:
                channel_wrap.set_property('height_request', -1)
                if self.spinner:
                    self.spinner.stop()
                    channel_wrap.remove(self.spinner)
                self.spinner = None
                if self.connected:
                    channel_wrap.pack_start(channel_box, True, True, 0)
            elif not self.connected:
                self.loading = False
                channel_wrap.set_property('height_request', 40)
                self.spinner = Gtk.Spinner()
                channel_wrap.pack_start(self.spinner, True, True, 0)
                channel_wrap.remove(channel_box)
                self.spinner.show()

        def connect_btn_clicked(event):
            print('connect_btn_clicked')
            self.loading = True
            if update_connect(not self.connected):
                connect_api()
            else:
                disconnect_api()

        def set_state(state):
            self.loading = False
            update_connect(state)
            account().set_connected(state)

            if state:
                print('set_state')
                self.loading = True
                upd_spinner()

                def _set_chats(chats):
                    search_list_box.clear_list()
                    search_list_box.set_items(list(chats.values()))
                    self.loading = False
                    upd_spinner()

                self.api.get_chats_idle(_set_chats)

            return state

        def show_error(title, description=None):
            err_dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, title)
            if description is not None:
                err_dialog.format_secondary_text(str(description))
            err_dialog.set_application(Gio.Application.get_default())
            err_dialog.run()
            err_dialog.destroy()

        def validate(api_id, api_hash, phone_number):
            errors = []
            if not api_id:
                set_error(api_id_entry)
                errors.append(_('API Id is required'))
            if not api_hash:
                set_error(api_hash_entry)
                errors.append(_('API Hash is required'))
            if safe_cast(api_id, int) is None:
                set_error(api_id_entry)
                errors.append(_('API Id must be integer'))
            if not phone_number:
                set_error(phone_entry)
                errors.append(_('The phone number is required'))
            if not re.search('^\+?\d{10,14}$', phone_number):
                set_error(phone_entry)
                errors.append(_('The phone number is invalid'))
            if errors:
                show_error(_('Validation error'), errors[0])
                return False

            return True

        def connect_api(code=None):
            (api_id, api_hash, phone_number, connected) = account().get_secure()

            if validate(api_id, api_hash, phone_number):
                self.api = TelegramApi.api(api_id, api_hash, phone_number)

                try:
                    self.api.login(code)
                except TelegramAuthStateError as e:
                    if self.api.state == AuthorizationState.WAIT_CODE:
                        def unable_to_login():
                            show_error(_("Unable to login Telegram"), _('Login code is required'))
                            set_state(False)

                        DialogCode(self, connect_api, unable_to_login)
                        return
                    else:
                        show_error(_("Unable to login Telegram"), e)
                except TelegramAuthError as e:
                    err = self.api.get_error()
                    show_error(_("Unable to login Telegram"), err if err else e)
                except RuntimeError as e:
                    show_error(_("Unable to login Telegram"), e)

                set_state(self.api.state == AuthorizationState.READY)
            else:
                set_state(False)

        def disconnect_api():
            search_list_box.reset()
            self.api.reset_chats()
            account().settings.set_string('channels', '[]')
            set_state(False)

        def get_center():
            self.parent = settings_box.get_toplevel().get_property('window')

            position = self.parent.get_position()
            geometry = self.parent.get_geometry()

            left_center = round(position.x + (geometry.width - geometry.x) / 2)
            top_center = round(position.y + (geometry.height - geometry.y) / 2)
#             print('WIN.position %s' % str(position))
#             print('WIN.geometry %s' % str(geometry))
#             print('WIN.left_center %s' % str(left_center))
#             print('WIN.top_center %s' % str(top_center))

            return {"x": left_center, "y": top_center}

        self.get_center = get_center

        configure_callback_dic = {
            "connect_btn_clicked_cb" : connect_btn_clicked,
        }
        prefs_ui.connect_signals(configure_callback_dic)

        api_id_entry.connect("focus-out-event", account_details_changed)
        api_hash_entry.connect("focus-out-event", account_details_changed)
        phone_entry.connect("focus-out-event", account_details_changed)

        fill_account_details()
        upd_spinner()

        def update_window():
            gtk_win = settings_box.get_toplevel()
            gtk_win.set_default_size(500, 800)
            gtk_win.set_resizable(False)
            donate_btn = gtk_win.add_button("Donate", Gtk.ResponseType.HELP)
            style_context = donate_btn.get_style_context()
            style_context.add_class('suggested-action')
            gtk_win.set_border_width(5)
            box = gtk_win.get_content_area()
            box.set_spacing(2)

        GLib.timeout_add(1000, update_window)

#         return settings_box
        depr_cnnct_page.add(settings_box)
#         return notebook
        return main_box
