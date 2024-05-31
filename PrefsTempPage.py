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
import os
import math
import subprocess
from gi.repository import RB
from gi.repository import Gtk, Gio, GLib, Gdk
from common import file_uri
from PrefsPage import PrefsPage

import gettext
gettext.install('rhythmbox', RB.locale_dir())


def delete_files_recursively(directory, progress_callback=None):
    for root, dirs, files in os.walk(directory, topdown=False):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                os.remove(file_path)
                if progress_callback:
                    progress_callback(file_path)
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")
            yield True

        for name in dirs:
            dir_path = os.path.join(root, name)
            try:
                os.rmdir(dir_path)
                if progress_callback:
                    progress_callback(dir_path)
            except Exception as e:
                print(f"Error deleting directory {dir_path}: {e}")
            yield True

    yield False

def start_deletion(directory, progress_callback=None, completion_callback=None):
    deletion_generator = delete_files_recursively(directory, progress_callback)

    def idle_deletion_task():
        try:
            if next(deletion_generator):
                return True
        except StopIteration:
            pass

        if completion_callback:
            completion_callback()

        return False

    GLib.idle_add(idle_deletion_task)


class PrefsTempPage(PrefsPage):
    name = _('Temporary Files')
    main_box = 'temp_vbox'
    ui_file = 'ui/prefs/temp.ui'
    _is_calculating = False

    def _create_widget(self):
        self._is_calculating = False
        self.temp_usage_label = self.ui.get_object('temp_usage_label')
        self.temp_path_entry = self.ui.get_object('temp_path_entry')
        self.usage_refresh_btn = self.ui.get_object('usage_refresh_btn')
        self.clear_tmp_btn = self.ui.get_object('clear_tmp_btn')
        self.clear_tmp_btn_label = self.ui.get_object('clear_tmp_btn_label')
        self.view_dir_btn = self.ui.get_object('view_dir_btn')
        # self.progress_label = self.ui.get_object('deleting_progress_label')

        self.temp_dir = self.plugin.api.temp_dir
        self.temp_path_entry.set_text(self.temp_dir)
        # self.progress_label.set_text('')

        self.usage_refresh_btn.connect('clicked', self._refresh_btn_clicked)
        self.clear_tmp_btn.connect('clicked', self._clear_tmp_btn_clicked)
        self.view_dir_btn.connect('clicked', self._view_dir_btn_clicked)

        self.calculate_size()

    def calculate_size(self):
        if self._is_calculating:
            return
        self._is_calculating = True

        self.usage_refresh_btn.set_sensitive(False)
        self.temp_usage_label.set_text(_("Calculating..."))
        try:
            result = subprocess.Popen(['du', '-sb', self.temp_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            GLib.io_add_watch(result.stdout, GLib.IO_IN, self.on_subprocess_output, result)
        except Exception as e:
            self.temp_usage_label.set_text(f"Error: {e}")
            self.usage_refresh_btn.set_sensitive(True)
        return False

    def convert_size(self, size_bytes):
        if size_bytes == 0:
            return "0 bytes"
        size_name = ("bytes", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1000)))
        p = math.pow(1000, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"

    def on_subprocess_output(self, source, condition, process):
        if condition == GLib.IO_IN:
            output = source.read()
            size = output.split()[0] if output else "Error"
            readable_size = self.convert_size(int(size)) if size.isdigit() else size
            self.temp_usage_label.set_text(readable_size)
            process.stdout.close()
            process.stderr.close()
            process.terminate()
            self.usage_refresh_btn.set_sensitive(True)
            self._is_calculating = False
            return False
        return True

    def _refresh_btn_clicked(self, widget):
        self.usage_refresh_btn.set_sensitive(False)
        self.temp_usage_label.set_text(_("Calculating..."))
        GLib.idle_add(self.calculate_size)

    def _delete_temp_files_dialog(self, widget=None):
        self.clear_tmp_btn.set_sensitive(False)
        msg = _('Are you sure you want to delete temporary files?')
        dialog = Gtk.MessageDialog(
            parent=self.box.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            message_format=msg)
        dialog.set_application(Gio.Application.get_default())
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            label = self.clear_tmp_btn_label.get_label()
            self.clear_tmp_btn_label.set_label(_('Deleting...'))

            def on_done():
                self.plugin.storage.update('audio',
                                           {'is_downloaded': 0, 'local_path': ''},
                                           {'is_downloaded': 1, 'is_moved': 0})
                self.clear_tmp_btn_label.set_label(label)
                # self.progress_label.set_text('')
                self.clear_tmp_btn.set_sensitive(True)
                self.calculate_size()

            # def on_progress(path):
            #     self.progress_label.set_text(path)

            start_deletion(self.temp_dir, completion_callback=on_done)
        else:
            self.clear_tmp_btn.set_sensitive(True)

    def _clear_tmp_btn_clicked(self, widget):
        self._delete_temp_files_dialog()

    def _view_dir_btn_clicked(self, widget):
        screen = self.plugin.shell.props.window.get_screen()
        Gtk.show_uri(screen, file_uri(self.temp_dir), Gdk.CURRENT_TIME)
