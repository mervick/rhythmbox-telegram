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

import rb
from gi.repository import RB
from gi.repository import GdkPixbuf
from gi.repository import GObject, Gtk, Gdk, Gio, GLib
from TelegramEntry import to_location
from TelegramStorage import TgLoader

import gettext
gettext.install('rhythmbox', RB.locale_dir())


# static void
# extract_cell_data_func (GtkTreeViewColumn *column,
# 			GtkCellRenderer *renderer,
# 			GtkTreeModel *tree_model,
# 			GtkTreeIter *iter,
# 			RBAudioCdSource *source)
# {
# 	RBAudioCDEntryData *extra_data;
# 	RhythmDBEntry *entry;
#
# 	entry = rhythmdb_query_model_iter_to_entry (RHYTHMDB_QUERY_MODEL (tree_model), iter);
# 	if (entry != NULL) {
# 		extra_data = RHYTHMDB_ENTRY_GET_TYPE_DATA (entry, RBAudioCDEntryData);
# 		gtk_cell_renderer_toggle_set_active (GTK_CELL_RENDERER_TOGGLE (renderer), extra_data->extract);
# 		rhythmdb_entry_unref (entry);
# 	}
# }

# 	/* create the 'extract' column */
# 	renderer = gtk_cell_renderer_toggle_new ();
# 	extract = gtk_tree_view_column_new ();
# 	gtk_tree_view_column_pack_start (extract, renderer, FALSE);
# 	gtk_tree_view_column_set_cell_data_func (extract,
# 						 renderer,
# 						 (GtkTreeCellDataFunc) extract_cell_data_func,
# 						 source,
# 						 NULL);
# 	gtk_tree_view_column_set_clickable (extract, TRUE);
# 	widget = gtk_check_button_new ();
# 	g_object_set (widget, "active", TRUE, NULL);
# 	force_no_spacing (widget);
# 	gtk_widget_show_all (widget);
# 	g_signal_connect_object (extract, "clicked", G_CALLBACK (extract_column_clicked_cb), source, 0);
# 	gtk_tree_view_column_set_widget (extract, widget);
#
# 	g_signal_connect_object (renderer, "toggled", G_CALLBACK (extract_toggled_cb), source, 0);
#
# 	/* set column width */
# 	gtk_cell_renderer_get_preferred_width (renderer, GTK_WIDGET (source->priv->entry_view), NULL, &toggle_width);
# 	gtk_tree_view_column_set_sizing (extract, GTK_TREE_VIEW_COLUMN_FIXED);
# 	gtk_tree_view_column_set_fixed_width (extract, toggle_width + 10);
#
# 	rb_entry_view_insert_column_custom (source->priv->entry_view, extract, "", "Extract", NULL, NULL, NULL, 1);
# 	gtk_widget_set_tooltip_text (gtk_tree_view_column_get_widget (extract),
# 	                             _("Select tracks to be extracted"));


class DownloadColumn():
    def __init__(self, source):
        renderer = Gtk.CellRendererToggle()
        extract = Gtk.TreeViewColumn()
        # gboolean expand, gboolean fill, glint padding
        extract.pack_start(renderer, False, False, 0)
        extract.set_cell_data_func(
            renderer, extract_cell_data_func,
            source)
        extract.set_clickable(True)


# class TestColumn():
#     _TEXT_COLUMN = 0
#     _PIXBUF_COLUMN = 1
#     _MEDIA_OBJECT_COLUMN = 2
#
#     _MEDIA_OBJECT_TYPE_ICON_MAP = {MediaServer2Service.CONTAINER_TYPE: 'folder',
#                                    MediaServer2Service.AUDIO_TYPE: 'media-audio',
#                                    MediaServer2Service.VIDEO_TYPE: 'video'}
#     def __init__(self):
# #         renderer = gtk.CellRendererPixbuf()
# #         column = gtk.TreeViewColumn('Media')
# #         column.pack_start(renderer, False)
# #         column.set_attributes(renderer, pixbuf=self._PIXBUF_COLUMN)
# #         renderer = gtk.CellRendererText()
# #         column.pack_start(renderer, True)
# #         column.set_attributes(renderer, text=self._TEXT_COLUMN)
# #         self.media_folders_view.append_column(column)
#
#         self.tree_model = Gtk.TreeStore(str,
#                                         Gtk.Gdk.Pixbuf,
#                                         gobject.TYPE_PYOBJECT)
#         self.media_folders_view = Gtk.TreeView(self.tree_model)
#         renderer = gtk.CellRendererPixbuf()
#         column = gtk.TreeViewColumn('Media')
#         column.pack_start(renderer, False)
#         column.set_attributes(renderer, pixbuf=self._PIXBUF_COLUMN)
#         renderer = gtk.CellRendererText()
#         column.pack_start(renderer, True)
#         column.set_attributes(renderer, text=self._TEXT_COLUMN)
#         self.media_folders_view.append_column(column)
# #         self.media_folders_view.connect('row-activated',
# #                                                 self._tree_row_activated_cb)

class TestColumn2:

    """ tries to load icon from disk and if found it saves it in cache returns it """
    def get_icon_pixbuf(self,filepath,return_value_not_found=None):
        if os.path.exists(filepath):
            width, height = gtk.icon_size_lookup(gtk.ICON_SIZE_BUTTON)
            if filepath in self.icon_cache:
                return self.icon_cache[filepath]
            else:
                try:
                    icon = gtk.gdk.pixbuf_new_from_file_at_size(filepath,width,height)
                except:
                    icon = return_value_not_found
                self.icon_cache[filepath] = icon
            return icon
        return return_value_not_found

    """ data display function for tree view """
    def model_data_func(self,column,cell,model,iter,infostr):
        obj = model.get_value(iter,1)
        self.clef_icon = self.get_icon_pixbuf(self.plugin.find_file("download.svg"))

        if infostr == "image":
#             icon = None
            icon = self.clef_icon

#             if isinstance(obj,RadioStation):
#                 station = obj
#                 # default icon
#                 icon = self.clef_icon
#
#                 # icons for special feeds
#                 if station.type == "Shoutcast":
#                     icon = self.get_icon_pixbuf(self.plugin.find_file("shoutcast-logo.png"))
#                 if station.type == "Icecast":
#                     icon = self.get_icon_pixbuf(self.plugin.find_file("xiph-logo.png"))
#                 if station.type == "Board":
#                     icon = self.get_icon_pixbuf(self.plugin.find_file("local-logo.png"))
#
#                 # most special icons, if the station has one for itsself
#                 if station.icon_src != "":
#                     hash_src = hashlib.md5(station.icon_src).hexdigest()
#                     filepath = os.path.join(self.icon_cache_dir, hash_src)
#                     if os.path.exists(filepath):
#                         icon = self.get_icon_pixbuf(filepath,icon)
#                     else:
#                         # load icon
#                         self.icon_download_queue.put([filepath,station.icon_src])

            if icon is None:
                cell.set_property("stock-id",gtk.STOCK_DIRECTORY)
            else:
                cell.set_property("pixbuf",icon)


    def __init__(self, source):
        self.icon_cache = {}
#         ui = Gtk.Builder()
#         ui.add_from_file(rb.find_plugin_file(self.plugin,
#                                              'radio_station.ui'))

#         self.filter_entry = ui.get_object('filter_entry')
#         self.filter_entry_bitrate = ui.get_object('filter_entry_bitrate')
#         self.filter_entry_genre = ui.get_object('filter_entry_genre')

#         self.tree_store = Gtk.TreeStore(str, object)
#
#         self.sorted_list_store = Gtk.TreeModelSort(model=self.tree_store)  #Gtk.TreeModelSort(self.tree_store)
#         self.filtered_list_store = self.sorted_list_store.filter_new()
#         self.filtered_list_store.set_visible_func(self.list_store_visible_func)
#         self.filtered_icon_view_store = None

        #self.tree_view = Gtk.TreeView(self.sorted_list_store)
#         self.tree_view = ui.get_object('tree_view')
#         self.tree_view.set_model(self.sorted_list_store)
        # create the view
        column_title = Gtk.TreeViewColumn()  #"Title",Gtk.CellRendererText(),text=0)
        column_title.set_title("test")
        renderer = Gtk.CellRendererPixbuf()
        column_title.pack_start(renderer, expand=False)
        column_title.set_cell_data_func(renderer, self.model_data_func, "image")

#         renderer = Gtk.CellRendererText()
#         column_title.pack_start(renderer, expand=True)
#         column_title.add_attribute(renderer, 'text', 0)
#         column_title.set_resizable(True)
#         column_title.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
#         column_title.set_fixed_width(100)
#         column_title.set_expand(True)
#         self.tree_view.append_column('TEST  title')

        def __cb(*a, **b):
            print('++++++++++++++++++++CB++++++++++++++++=')
            pass

        column_title.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column_title.set_fixed_width(80)

        entry_view = source.get_entry_view()
        print("visible-columns")
        vis = entry_view.get_property("visible-columns")
        print(vis)
        entry_view.append_column_custom(column_title,'test',"test", __cb, None, None)
        vis.append('test')
        entry_view.set_property("visible-columns", vis)

#         self.info_box_tree = ui.get_object('info_box_tree')
#         # - selection change
#         self.tree_view.connect("cursor-changed", self.treeview_cursor_changed_handler, self.info_box_tree)

        # create icon view
#         self.icon_view = ui.get_object('icon_view')
#         self.icon_view.set_text_column(0)
#         self.icon_view.set_pixbuf_column(2)
#         self.tree_view_container = ui.get_object('tree_view_container')
#         self.icon_view_container = ui.get_object('icon_view_container')
#         self.view = ui.get_object('view')
#         filterbox = ui.get_object('filterbox')
#         self.start_box = ui.get_object('start_box')


def empty_cb(*a, **b):
    pass

class ActionsColumn:
    idx = 0

    """ tries to load icon from disk and if found it saves it in cache returns it """
    def get_icon_pixbuf(self,filepath,return_value_not_found=None):
        if os.path.exists(filepath):
#             width, height = gtk.icon_size_lookup(gtk.ICON_SIZE_BUTTON)
            width, height = gtk.icon_size_lookup(Gtk.IconSize.Button)
            if filepath in self.icon_cache:
                return self.icon_cache[filepath]
            else:
                try:
                    icon = gtk.gdk.pixbuf_new_from_file_at_size(filepath,width,height)
                except:
                    icon = return_value_not_found
                self.icon_cache[filepath] = icon
            return icon
        return return_value_not_found

    icons = [
        "/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/download-dark.svg",
        "/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/empty.svg",
        "/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/error.svg",
        "/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/library-dark.svg",
    ]
    icons = [
        "/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/download-light.svg",
        "/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/empty.svg",
        "/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/error.svg",
        "/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/state/library-light.svg",
    ]

    """ data display function for tree view """
    def model_data_func(self,column,cell,model,iter,infostr):
        obj = model.get_value(iter,1)
        print(column)
        print(cell)
        print(model)
        print(iter)
        print(infostr)
        print(obj)

        filepath = self.icons[self.idx]

        self.idx = self.idx + 1
        if self.idx == len(self.icons):
            self.idx = 0
#         obj = model.get_value(iter,1)
#         self.clef_icon = self.get_icon_pixbuf(self.plugin.find_file("download.svg"))
#         icon = self.get_icon_pixbuf(self.plugin.find_file("download.svg"))

#         cell.set_property("stock-id", Gtk.STOCK_DIRECTORY)
#         cell.set_property("stock-id", Gtk.STOCK_DIALOG_WARNING)
#         cell.set_property("stock-id", Gtk.STOCK_DIALOG_ERROR)
#         cell.set_property("stock-id", 'emblem-error')


#         cell.set_property("stock-id", Gtk.Stock.Directory)
#         icon = self.get_icon_pixbuf(self.plugin.find_file("icon-16x16.png"))

#         filepath = '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/images/icon-16x16.png'
#         filepath = '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/dialog-error.svg'
#         filepath = '/home/data/projects/tg-rhythmbox/rhythmbox-telegram/icons/hicolor/scalable/realtimesync.svg'
# #         if os.path.exists(filepath):
#         width, height = gtk.icon_size_lookup(Gtk.IconSize.BUTTON)
#         icon = gtk.gdk.pixbuf_new_from_file_at_size(filepath,width,height)
        icon = GdkPixbuf.Pixbuf.new_from_file(filepath)
#         icon = self.get_icon_pixbuf(filepath)
        cell.set_property("pixbuf",icon)
#         cell.set_property("gicon", icon)
#         cell.set_property("stock-size", Gtk.IconSize.BUTTON)
#         cell.set_property("stock-size", Gtk.IconSize.Button)
#         cell.set_tooltip_text('Test')
#         cell.connect("query-tooltip", lambda a,b=None: True)
#         cell.set_property("has-tooltip", True)
        return

        if infostr == "image":
#             icon = None
            icon = self.clef_icon

#             if isinstance(obj,RadioStation):
#                 station = obj
#                 # default icon
#                 icon = self.clef_icon
#
#                 # icons for special feeds
#                 if station.type == "Shoutcast":
#                     icon = self.get_icon_pixbuf(self.plugin.find_file("shoutcast-logo.png"))
#                 if station.type == "Icecast":
#                     icon = self.get_icon_pixbuf(self.plugin.find_file("xiph-logo.png"))
#                 if station.type == "Board":
#                     icon = self.get_icon_pixbuf(self.plugin.find_file("local-logo.png"))
#
#                 # most special icons, if the station has one for itsself
#                 if station.icon_src != "":
#                     hash_src = hashlib.md5(station.icon_src).hexdigest()
#                     filepath = os.path.join(self.icon_cache_dir, hash_src)
#                     if os.path.exists(filepath):
#                         icon = self.get_icon_pixbuf(filepath,icon)
#                     else:
#                         # load icon
#                         self.icon_download_queue.put([filepath,station.icon_src])

            if icon is None:
                cell.set_property("stock-id",Gtk.STOCK_DIRECTORY)
            else:
                cell.set_property("pixbuf",icon)


    def __init__(self, source):
        self.icon_cache = {}

        column_title = Gtk.TreeViewColumn()  #"Title",Gtk.CellRendererText(),text=0)
        column_title.set_title("Actions")
        renderer = Gtk.CellRendererPixbuf()
        column_title.set_cell_data_func(renderer, self.model_data_func, "image")

#         icon_size_ok, icon_w, icon_h = Gtk.icon_size_lookup(self.ICON_SIZE)
#         icon_size_ok, icon_w, icon_h = Gtk.icon_size_lookup(Gtk.IconSize.Button)
#         if icon_size_ok:
#             column_title.set_min_width(icon_w)
        column_title.set_expand(False)
        column_title.set_resizable(False)

#         renderer = Gtk.CellRendererToggle()
        column_title.pack_start(renderer, expand=False)
        column_title.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column_title.set_fixed_width(80)

        entry_view = source.get_entry_view()
        entry_view.append_column_custom(column_title,'Actions',"tg-actions", empty_cb, None, None)
        visible_columns = entry_view.get_property("visible-columns")
        visible_columns.append('tg-actions')
        entry_view.set_property("visible-columns", visible_columns)


        entry_view.connect("query-tooltip", lambda a,b=None: True)
        entry_view.set_property("has-tooltip", True)
#         print("visible-columns")
#         print(visible_columns)


class TelegramSource(RB.BrowserSource):
    def __init__(self):
        self.is_activated = False
        RB.BrowserSource.__init__(self)
        self.app = Gio.Application.get_default()
        self.initialised = False
        self.shell = None
        self.db = None
        self.player = None
        self.entry_type = None
        self.api = None
        self.storage = None
        self.chat_id = None
        self.last_track = None
        self._is_downloading = 0

#     def do_impl_activate(self):
#         if self.is_activated:
#             rb.BrowserSource.do_impl_activate(self)
#             return
#         self.is_activated = True
#         TestColumn2(self)

    def setup(self, api, chat_id):
        self.initialised = False
        shell = self.props.shell
        self.shell = shell
        self.db = shell.props.db
        self.player = shell.props.shell_player
        self.entry_type = self.props.entry_type
        self.api = api
        self.storage = api.storage
        self.chat_id = chat_id
        self.last_track = None
        self.loader = None
        ActionsColumn(self)

    def do_deselected(self):
        print('do_deselected %s' % self.chat_id)
        if self.loader is not None:
            self.loader.stop()

    def do_selected(self):
#         TestColumn2(self)
        # GTK_SORT_ASCENDING = 0, GTK_SORT_DESCENDING = 1
        self.get_entry_view().set_sorting_order("Location", 1)
        print('do_selected %s' % self.chat_id)

        if not self.initialised:
            self.initialised = True
            self.add_entries()

        self.loader = TgLoader(self.chat_id, self.add_entry)
        self.loader.start()

    def add_entries(self):
        all_audio = self.storage.get_chat_audio(self.chat_id)
        for audio in all_audio:
            self.add_entry(audio)

    def add_entry(self, track, pref=''):
        location = '%s%s' % (to_location(self.api.hash, track.date, self.chat_id, track.message_id), pref)
        entry = self.db.entry_lookup_by_location(location)

        #  * RBEntryViewColumn:
        #  * @RB_ENTRY_VIEW_COL_TRACK_NUMBER: the track number column
        #  * @RB_ENTRY_VIEW_COL_TITLE: the title column
        #  * @RB_ENTRY_VIEW_COL_ARTIST: the artist column
        #  * @RB_ENTRY_VIEW_COL_COMPOSER: the composer column
        #  * @RB_ENTRY_VIEW_COL_ALBUM: the album column
        #  * @RB_ENTRY_VIEW_COL_GENRE: the genre column
        #  * @RB_ENTRY_VIEW_COL_DURATION: the duration column
        #  * @RB_ENTRY_VIEW_COL_QUALITY: the quality (bitrate) column
        #  * @RB_ENTRY_VIEW_COL_RATING: the rating column
        #  * @RB_ENTRY_VIEW_COL_PLAY_COUNT: the play count column
        #  * @RB_ENTRY_VIEW_COL_YEAR: the year (release date) column
        #  * @RB_ENTRY_VIEW_COL_LAST_PLAYED: the last played time column
        #  * @RB_ENTRY_VIEW_COL_FIRST_SEEN: the first seen (imported) column
        #  * @RB_ENTRY_VIEW_COL_LAST_SEEN: the last seen column
        #  * @RB_ENTRY_VIEW_COL_LOCATION: the location column
        #  * @RB_ENTRY_VIEW_COL_BPM: the BPM column
        #  * @RB_ENTRY_VIEW_COL_COMMENT: the comment column

        if not entry:
            entry = RB.RhythmDBEntry.new(self.db, self.entry_type, location)
            self.db.entry_set(entry, RB.RhythmDBPropType.TITLE, track.title)
            self.db.entry_set(entry, RB.RhythmDBPropType.ARTIST, track.artist)
#             self.db.entry_set(entry, RB.RhythmDBPropType.ALBUM, track.artist)
            self.db.entry_set(entry, RB.RhythmDBPropType.DURATION, track.duration)
#             self.db.entry_set(entry, RB.RhythmDBPropType.RATING, 0)

#             if item['artwork_url'] is not None:
#               db.entry_set(entry, RB.RhythmDBPropType.MB_ALBUMID, item['artwork_url'])

#             dt = datetime.strptime(item['created_at'], '%Y/%m/%d %H:%M:%S %z')
#             db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(dt.timestamp()))

            self.db.entry_set(entry, RB.RhythmDBPropType.FIRST_SEEN, int(track.date))
            dt = GLib.DateTime.new_from_unix_local(int(track.date))
            date = GLib.Date.new_dmy(dt.get_day_of_month(), GLib.DateMonth(dt.get_month()), dt.get_year())

            self.db.entry_set(entry, RB.RhythmDBPropType.DATE, date.get_julian())
            self.db.commit()

    def playing_entry_changed_cb(self, player, entry):
        '''
        playing_entry_changed_cb changes the album artwork on every
        track change.
        '''
        if not entry:
            return
        if entry.get_entry_type() != self.props.entry_type:
            return

        au = entry.get_string(RB.RhythmDBPropType.MB_ALBUMID)
        if au:
            key = RB.ExtDBKey.create_storage(
                "title", entry.get_string(RB.RhythmDBPropType.TITLE))
            key.add_field("artist", entry.get_string(
                RB.RhythmDBPropType.ARTIST))
            key.add_field("album", entry.get_string(
                RB.RhythmDBPropType.ALBUM))
            self.art_store.store_uri(key, RB.ExtDBSourceType.EMBEDDED, au)

    def do_can_delete(self):
        return True

    def do_can_copy(self):
        return False

    def do_can_pause(self):
        return True

    def do_can_add_to_queue(self):
        return True


GObject.type_register(TelegramSource)
