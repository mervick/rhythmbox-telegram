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

import functools
import json
import re
import rb
from gi.repository import RB
from gi.repository import GObject, Gtk, Gio, Peas, PeasGtk
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
    def __init__(self, entry, list_box, flow_box, flex_wrap_box, list_frame, empty_label):
        self.entry = entry
        self.list_box = list_box
        self.flow_box = flow_box
        self.flex_wrap_box = flex_wrap_box
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
        self.list_frame.remove(self.flex_wrap_box)
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
            self.list_frame.add(self.flex_wrap_box)
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


class TelegramConfig(GObject.GObject, PeasGtk.Configurable):
    __gtype_name__ = 'TelegramConfig'
    object = GObject.property(type=GObject.GObject)
    loading = None
    spinner = None
    parent = None
    api = None
    removed_help = False
    _changes = {}

    def __init__(self):
        GObject.GObject.__init__(self)
        self.shell = self.object

    def do_create_configure_widget(self):
        prefs_ui = Gtk.Builder()
        popup_ui = Gtk.Builder()
        # prefs_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs4.ui"))
        prefs_ui.add_from_file(rb.find_plugin_file(self, "ui/prefs5.ui"))
        popup_ui.add_from_file(rb.find_plugin_file(self, "ui/popup.ui"))

        popover = popup_ui.get_object("main_menu_popover")
        list_box = popup_ui.get_object("list_box")
        search_entry = popup_ui.get_object("search_entry")

        list_frame = prefs_ui.get_object("list_frame")
        empty_label = prefs_ui.get_object("empty_label")
        flex_wrap_box = prefs_ui.get_object("flex_wrap_box")
        flow_box = prefs_ui.get_object("flow_box")

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

        search_list_box = SearchListBox(search_entry, list_box, flow_box, flex_wrap_box, list_frame, empty_label)
        search_list_box.connect_on_change(listbox_change)

        add_chat_btn = prefs_ui.get_object("add_chat_btn")
        add_chat_btn.set_popover(popover)

        has_errors = []

        # def menu_clicked(event):
        #     print('menu_entry_clicked_cb')
        #     print(event)
        #
        # button = Gtk.ModelButton(label="Click Me  dfg dfgfd gdfgdf gdgdf gdfg dfgdfg dfgdfgdfgdggdgdf gd gdf gdgdgf ", visible=True)
        # button.connect("clicked", menu_clicked)
        # button.set_alignment(0, 0.5)
        # list_box.pack_start(button, False, False, 0)
        #
        #
        # for i in range(0, 100):
        #     button = Gtk.ModelButton(label="Click Me", visible=True)
        #     button.connect("clicked", menu_clicked)
        #     button.set_alignment(0, 0.5)
        #     list_box.pack_start(button, False, False, 0)

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
            print('update_connect %s' % str(connected))
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

            # if not self.loading:
            if enabled and not self.loading:
                if self.removed_help:
                    self.removed_help = False
                    settings_box.pack_start(helpbox, True, True, 0)
            elif not self.removed_help:
                self.removed_help = True
                settings_box.remove(helpbox)

            return connected

        # def open_dialog(event):
        #     self.menu.popup(event)
        #     return
        #     print('add_btn_clicked_cb')
        #     d_builder = Gtk.Builder()
        #     d_builder.add_from_file(rb.find_plugin_file(self, "telegram-channels.2.ui"))
        #
        #     listbox = d_builder.get_object('listbox')
        #     listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        #     self.listbox = listbox
        #
        #     # for i in range(0, 100):
        #     #     add_item(None)
        #     #     # listbox.insert('label')
        #
        #     self.menu = d_builder.get_object("app-menu")
        #
        #     # row = Gtk.ListBoxRow()
        #     # hbox = Gtk.Box()
        #     # row.add(hbox)
        #     # # hbox.pack_start(Gtk.Label("Here is an Item"), True, True, 0)
        #     # self.listbox.add(row)
        #     #
        #     # hbox = Gtk.Box()
        #     #
        #     # button_add_item = Gtk.Button(label = "Add Item", valign = Gtk.Align.CENTER)
        #     # button_add_item.connect("clicked", add_item)
        #     # hbox.pack_start(button_add_item, True, True, 0)
        #     #
        #     # button_remove_item = Gtk.Button(label = "Remove Item", valign = Gtk.Align.CENTER)
        #     # button_remove_item.connect("clicked", remove_item)
        #     # hbox.pack_start(button_remove_item, True, True, 0)
        #
        #     # box.pack_start(hbox, False, True, 0)
        #
        #     window1 = d_builder.get_object("window")
        #     window1.show_all()
        #
        #     # /* Construct a GtkBuilder instance and load our UI description */
        #     # GtkBuilder *prefs_ui = gtk_builder_new ();
        #     # gtk_builder_add_from_file (prefs_ui, "prefs_ui.ui", NULL);
        #     #
        #     # // connect signal handlers to the constructed widgets
        #     # GObject * window = gtk_builder_get_object(prefs_ui,"MainWindow");
        #     # gtk_window_set_application(GTK_WINDOW(window), app);
        #     #
        #     #
        #     # gtk_widget_show(GTK_WIDGET(window));
        #     #
        #     # // unload the prefs_ui (destroy)
        #     # g_object_unref(prefs_ui);
        #
        #     # prefs_ui = Gtk.Builder()
        #     # prefs_ui.add_from_file("example.glade")

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

            # GLib.timeout_add(100, update_connect)

        def account_details_changed(entry, event):
            api_id = re.sub("\D", "", api_id_entry.get_text())
            api_hash = api_hash_entry.get_text().strip()
            # phone_number = re.sub("[^\+\d]", "", phone_entry.get_text())
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
                # connect_api(connect_state)
                connect_api()
            else:
                disconnect_api()
                # self.loading = False
                # update_connect(False)
                # account().set_connected(self.connected)
                # @TODO add disconnect
                # GLib.timeout_add(1000, done)

        # def on_update(chats, count, is_done=False):
        #     search_list_box.set_items(list(chats.values()))
        #     # print('TOTAL_COUNT %d of %d' % (len(chats.keys()), count))
        #
        # def _update_chats(chats):
        #     search_list_box.set_items(list(chats.values()))
        #     pass

        # def on_done_list(chats):
        #     print('+++++++++++++++++DONE+++++++++ %d' % len(chats.keys()))

        # def connect_state(state):
        def set_state(state):
            self.loading = False
            update_connect(state)
            account().set_connected(state)

            if state:
                print('set_state')
                self.loading = True
                upd_spinner()

                def _set_chats(chats):
                    # print('_set_chats')
                    # print(chats)
                    search_list_box.clear_list()
                    search_list_box.set_items(list(chats.values()))
                    self.loading = False
                    upd_spinner()

                # me = self.api.get_logged()
                # print('========ME===========')
                # print(me)
                self.api.get_chats_idle(_set_chats)

                # self.api.get_chats_idle(lambda chats: search_list_box.set_items(list(chats.values())))

                # chats = self.api.get_chats_async()
                # search_list_box.set_items(list(chats.values()))
            return state

        def show_error(title, description=None):
            # RB.error_dialog(title=title,
            #     message=str(description) if description else '')

            # win = self.shell.get_property('window')
            # win = RB.Shell.get_property('window')

            err_dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, title)
            # err_dialog = Gtk.MessageDialog(self.parent, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, title)
            if description is not None:
                err_dialog.format_secondary_text(str(description))
            err_dialog.set_application(Gio.Application.get_default())
            # center = self.get_center()
            # err_dialog.get_toplevel().move(center["x"]+200, center["y"]+300)
            # err_dialog.move(center["x"] - 150, center["y"] - 120)
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

        # def get_code():
        #     d_window = Gtk.MessageDialog(window,
        #         Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        #         Gtk.MessageType.QUESTION,
        #         Gtk.ButtonsType.OK_CANCEL,
        #         _('Enter your login code from your device'))
        #     d_window.set_title(_('Telegram Authorization'))
        #
        #     d_box = d_window.get_content_area()
        #     d_entry = Gtk.Entry()
        #     # d_entry.set_visibility(False)
        #     # d_entry.set_invisible_char("*")
        #     d_entry.set_size_request(120,0)
        #     d_box.pack_end(d_entry, False, False, 0)
        #
        #     d_window.show_all()
        #     response = d_window.run()
        #     text = d_entry.get_text()
        #     d_window.destroy()
        #     if (response == Gtk.ResponseType.OK) and text:
        #         return text
        #     else:
        #         return None

        # def on_code_ok(code):
        #     raise Exception('code %s' % code)
        #     pass
        #
        # def on_code_cancel():
        #     raise Exception('code_cancel')
        #     pass

        # def connect_api(set_state, code=None):
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
                        # code = get_code()
                        # if not code:
                        #     show_error(_("Unable to login Telegram"), _('Login code is required'))
                        #     return False
                        # else:
                        #     return connect_api(code)
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
            # self.parent = RB.Shell
            # self.parent = settings_box.get_toplevel().get_parent_window()
            # self.parent = settings_box.get_toplevel()
            self.parent = settings_box.get_toplevel().get_property('window')

            position = self.parent.get_position()
            geometry = self.parent.get_geometry()

            left_center = round(position.x + (geometry.width - geometry.x) / 2)
            top_center = round(position.y + (geometry.height - geometry.y) / 2)
            print('WIN.position %s' % str(position))
            print('WIN.geometry %s' % str(geometry))
            print('WIN.left_center %s' % str(left_center))
            print('WIN.top_center %s' % str(top_center))

            return {"x": left_center, "y": top_center}

        self.get_center = get_center

        # self.parent = settings_box.get_toplevel()

        configure_callback_dic = {
            "connect_btn_clicked_cb" : connect_btn_clicked,
            # "add_btn_clicked_cb" : open_dialog,
        }
        prefs_ui.connect_signals(configure_callback_dic)

        api_id_entry.connect("focus-out-event", account_details_changed)
        api_hash_entry.connect("focus-out-event", account_details_changed)
        phone_entry.connect("focus-out-event", account_details_changed)

        fill_account_details()
        upd_spinner()

        return settings_box
