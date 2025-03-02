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
import gi
import rb
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gio, GLib
from typing import Callable
from storage import Audio
from common import get_audio_tags, format_time, pretty_file_size, get_file_size, file_uri, move_window_center
from common import CONFLICT_ACTION_RENAME, CONFLICT_ACTION_REPLACE, CONFLICT_ACTION_IGNORE


class ConcurrentResolveError(Exception):
    pass


class FileInfo:
    @staticmethod
    def from_file(file_path):
        info = FileInfo()
        info.file_path = file_path
        info.meta_tags = get_audio_tags(file_path)
        info.file_size = get_file_size(info.file_path)
        return info

    @staticmethod
    def from_audio(audio):
        info = FileInfo()
        info.audio = audio
        info.file_path = audio.local_path
        info.meta_tags = audio.meta_tags
        info.file_size = get_file_size(info.file_path)
        return info

    def __init__(self):
        self.audio = None
        self.file_path = None
        self.file_size = 0
        self.meta_tags = {}

    def browse_in_file_manager(self):
        app_info = Gio.AppInfo.get_default_for_type('inode/directory', True)
        if app_info:
            app_info.launch_uris([file_uri(self.file_path)], None)

    def get_icon_name(self):
        file = Gio.File.new_for_path(self.file_path)
        info = file.query_info(Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE, 0, None)
        if info:
            content_type = info.get_content_type()
            icon = Gio.content_type_get_icon(content_type)
            if isinstance(icon, Gio.ThemedIcon):
                names = icon.get_names()
                return names[0] if names else "text-x-generic"
        return "text-x-generic"


def set_small_label(widget, label):
    widget.set_markup('<small>%s</small>' % label)


class ConflictDialog:
    builder: Gtk.Builder
    window: Gtk.Window | None = None
    callback: Callable[[str, Audio, str], None] | None = None
    new_file: FileInfo | None = None
    old_file: FileInfo | None = None

    def __init__(self, plugin, audio, filename, callback):
        self._running = True
        self.plugin = plugin
        self.new_file = FileInfo.from_audio(audio)
        self.old_file = FileInfo.from_file(filename)

        self.builder = Gtk.Builder()
        self.builder.add_from_file(rb.find_plugin_file(self.plugin, "ui/conflict-dialog.ui"))

        self.window = self.builder.get_object('window')
        signals = {
            "browse_new_btn_clicked_cb" : self._browse_new_btn_clicked_cb,
            "browse_old_btn_clicked_cb" : self._browse_old_btn_clicked_cb,
            "rename_btn_clicked_cb": self._rename_btn_clicked_cb,
            "replace_btn_clicked_cb": self._replace_btn_clicked_cb,
            "skip_btn_clicked_cb": self._skip_btn_clicked_cb,
            "on_window_destroy": self._on_window_destroy,
            "destroy": self._on_window_destroy,
            "delete-event": self._on_window_destroy,
        }
        self.builder.connect_signals(signals)
        self.window.set_title(_('Telegram: Download File Conflict'))

        self.callback = callback
        self.update_ui()

        self.window.set_default_size(500, 400)
        self.window.set_resizable(False)
        self.window.set_modal(True)
        self.window.set_transient_for(self.plugin.shell.props.window)
        self.window.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.window.show_all()

        # if self.plugin.shell.props.visibility:
        #     GLib.timeout_add(400, move_window_center, self.window, self.plugin.shell.props.window)

    def update_ui(self):
        basename = os.path.basename(self.old_file.file_path)
        self.builder.get_object('title').set_label(
            '<span font_desc=\'14\' weight=\'bold\'>%s</span>' % (_('Replace file "%s"?') % basename))

        self.builder.get_object('file_icon_new').set_from_icon_name(self.new_file.get_icon_name(), 6)
        set_small_label(self.builder.get_object('artist_new_lbl'), _('Artist:'))
        set_small_label(self.builder.get_object('artist_new_val'), self.new_file.meta_tags.get('artist', 'Unknown'))
        set_small_label(self.builder.get_object('title_new_lbl'), _('Title:'))
        set_small_label(self.builder.get_object('title_new_val'), self.new_file.meta_tags.get('title', 'Unknown'))
        set_small_label(self.builder.get_object('duration_new_lbl'), _('Duration:'))
        set_small_label(self.builder.get_object('duration_new_val'), format_time(int(self.new_file.meta_tags.get('duration', 0))))
        set_small_label(self.builder.get_object('filesize_new_lbl'), _('File size:'))
        set_small_label(self.builder.get_object('filesize_new_val'), pretty_file_size(self.new_file.file_size))

        self.builder.get_object('file_icon_old').set_from_icon_name(self.old_file.get_icon_name(), 6)
        set_small_label(self.builder.get_object('artist_old_lbl'), _('Artist:'))
        set_small_label(self.builder.get_object('artist_old_val'), self.old_file.meta_tags.get('artist', 'Unknown'))
        set_small_label(self.builder.get_object('title_old_lbl'), _('Title:'))
        set_small_label(self.builder.get_object('title_old_val'), self.old_file.meta_tags.get('title', 'Unknown'))
        set_small_label(self.builder.get_object('duration_old_lbl'), _('Duration:'))
        set_small_label(self.builder.get_object('duration_old_val'), format_time(int(self.old_file.meta_tags.get('duration', 0))))
        set_small_label(self.builder.get_object('filesize_old_lbl'), _('File size:'))
        set_small_label(self.builder.get_object('filesize_old_val'), pretty_file_size(self.old_file.file_size))

    def _callback_action(self, action):
        if self._running:
            self._running = False
            self.window.close()
            GLib.timeout_add(100, self.callback, action, self.new_file.audio, self.old_file.file_path)

    def _browse_new_btn_clicked_cb(self, *args):
        self.new_file.browse_in_file_manager()

    def _browse_old_btn_clicked_cb(self, *args):
        self.old_file.browse_in_file_manager()

    def _rename_btn_clicked_cb(self, *args):
        self._callback_action(CONFLICT_ACTION_RENAME)

    def _replace_btn_clicked_cb(self, *args):
        self._callback_action(CONFLICT_ACTION_REPLACE)

    def _skip_btn_clicked_cb(self, *args):
        self._callback_action(CONFLICT_ACTION_IGNORE)

    def _on_window_destroy(self, *args):
        self._callback_action(CONFLICT_ACTION_IGNORE)
