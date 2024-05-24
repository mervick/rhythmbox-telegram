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
import functools
from gi.repository import Gtk


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
        self.clear_selected(raise_on_change=False)
        if selected:
            for item in selected:
                self.add_selected(item, raise_on_change=False)

    def clear_selected(self, raise_on_change=True):
        if len(self.selected):
            self.selected = []
            self._remove_all_selected()
        if raise_on_change:
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
                self.flow_box.remove(widget)
            else:
                items.append(item)
        self.selected = items
        if not len(self.selected):
            self._remove_all_selected()
        self._on_change()

    def add_selected(self, selected, raise_on_change=True):
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
        if raise_on_change:
            self._on_change()

    def search(self, event=None, force=False):
        query = self.entry.get_text().strip()
        if self.query != query or force:
            self.query = query
            self.clear_list()
            if query:
                query_casefold = query.casefold()
                for item in self.items:
                    if query_casefold in item['casefold']:
                        self._add_item(item)
            else:
                for item in self.items:
                    self._add_item(item)

    def set_items(self, items):
        self.items = []
        for item in items:
            self.add(item, update=False)
        self._sort()
        self.search(force=True)

    def _sort(self):
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
        if update:
            self._sort()
            self.search()

    def select_clicked_cb(self, event, item_id):
        selected = filter(lambda i: i["id"] == item_id, self.items)
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
