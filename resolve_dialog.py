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
from common import get_audio_tags, format_time, pretty_file_size, get_file_size, file_uri
from common import CONFLICT_ACTION_RENAME, CONFLICT_ACTION_REPLACE, CONFLICT_ACTION_IGNORE

# def parse_stream_info(data):
#     result = {}
#     for line in data.strip().splitlines():
#         line = line.strip()
#         if '=' in line:
#             key, value = line.split('=', 1)
#             if key not in result:
#                 result[key] = value.strip()
#     return result


class ConcurrentResolveError(Exception):
    pass


class FileInfo:
    @staticmethod
    def from_file(file_path):
        info = FileInfo()
        info.file_path = file_path
        info.meta_tags = get_audio_tags(file_path)
        info.file_size = get_file_size(info.file_path )
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

        # self.file_path = file_path
        # self.meta_tags = get_audio_tags(file_path)
        # self.stream_info = {}
        # self._update
    #     try:
    #         args = ['ffprobe', '-v', 'quiet', '-show_streams', '-select_streams', 'a', file_path]
    #         result = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    #         GLib.io_add_watch(result.stdout, GLib.IO_IN, self._subprocess_out_cb, result)
    #     except:
    #         pass
    #
    # def _subprocess_out_cb(self, source, condition, process):
    #     if condition == GLib.IO_IN:
    #         output = source.read()
    #         process.stdout.close()
    #         process.stderr.close()
    #         process.terminate()
    #         info = parse_stream_info(output)
    #         if info:
    #             self.stream_info = info
    #             self._update()
    #         return False
    #     return True

    def browse_in_file_manager(self):
        app_info = Gio.AppInfo.get_default_for_type('inode/directory', True)
        if app_info:
            app_info.launch_uris([file_uri(self.file_path)], None)


def set_small_label(widget, label):
    widget.set_markup('<small>%s</small>' % label)


class ResolveDialog:
    builder: Gtk.Builder
    window: Gtk.Window | None = None
    callback: Callable[[str, Audio, str], None] | None = None
    new_file: FileInfo | None = None
    old_file: FileInfo | None = None

    def __init__(self, plugin):
        self._running = False
        self.plugin = plugin

    def ask_resolve_action(self, audio, filename, callback):
        if self._running:
            raise ConcurrentResolveError("Cannot invoke resolve: a previous operation is still running.")

        self._running = True

        self.new_file = FileInfo.from_audio(audio)
        self.old_file = FileInfo.from_file(filename)

        self.builder = Gtk.Builder()
        self.builder.add_from_file(rb.find_plugin_file(self.plugin, "ui/resolve-dialog.ui"))

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
        self.window.set_title(_('Telegram Download File'))

        self.callback = callback
        self.update_window()

        self.window.set_resizable(False)
        self.window.set_modal(True)
        self.window.set_transient_for(self.plugin.shell.props.window)
        self.window.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)

        self.window.show_all()

    def update_window(self):
        basename = os.path.basename(self.old_file.file_path)
        name_len = len(basename)

        if name_len > 40:
            set_small_label(self.builder.get_object('filename_new_val'), basename)
            set_small_label(self.builder.get_object('filename_old_val'), basename)
        else:
            self.builder.get_object('filename_new_val').set_label(basename)
            self.builder.get_object('filename_old_val').set_label(basename)

        set_small_label(self.builder.get_object('artist_new_lbl'), _('Artist:'))
        set_small_label(self.builder.get_object('artist_new_val'), self.new_file.meta_tags.get('artist', 'Unknown'))
        set_small_label(self.builder.get_object('title_new_lbl'), _('Title:'))
        set_small_label(self.builder.get_object('title_new_val'), self.new_file.meta_tags.get('title', 'Unknown'))
        set_small_label(self.builder.get_object('duration_new_lbl'), _('Duration:'))
        set_small_label(self.builder.get_object('duration_new_val'), format_time(int(self.new_file.meta_tags.get('duration', 0))))
        set_small_label(self.builder.get_object('filesize_new_lbl'), _('File size:'))
        set_small_label(self.builder.get_object('filesize_new_val'), pretty_file_size(self.new_file.file_size))

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
