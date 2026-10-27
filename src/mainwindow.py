import os
import re
import sys
import shutil
import logging
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFileDialog,
                             QListWidget, QAbstractItemView, QGroupBox,
                             QMessageBox, QSplitter, QFormLayout, QScrollArea,
                             QListWidgetItem, QGraphicsDropShadowEffect, QMenuBar, QMenu,
                             QComboBox, QInputDialog)
from PyQt6.QtCore import (Qt, QTimer, QSettings, QUrl, QBuffer, QIODevice, QByteArray,
                          QStandardPaths, pyqtSignal)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor, QBrush, QAction, QDesktopServices, QImage

import music_tag
# Voeg deze regels toe:
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC


from matcher import WebMatcherDialog
from csv_matcher import CsvMatcherDialog
from styles import DARK_THEME
from app_translations import tr, set_language, get_current_language
from artist_catalog import ArtistCatalog, artists_from_plex_csv
from artist_field import ArtistField
from extra_tags import RELEASE_TYPES, read_release_type, write_release_type
from tag_values import clean_value, safe_get, force_remove
from artist_sync import DEFAULT_URL, to_raw_url, pick_catalog_file, fetch_in_background


def resource_path(name):
    """Path to a bundled file (works from source and from the PyInstaller app)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

class MusicTaggerApp(QMainWindow):
    # (status, message, manual) - emitted from the download thread
    artist_list_fetched = pyqtSignal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("OilsjterseLiekes", "MetadataMaster")

        # Load Language Preference
        saved_lang = self.settings.value("language", "en")
        set_language(saved_lang)

        self.setWindowTitle(tr("app_title"))
        self.resize(1200, 800)

        self.pending_changes = {}

        # --- LOGGING SETUP ---
        self.log_dir = os.path.join(os.path.expanduser("~"), "EirekesManagerLogs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "application.log")

        # Reset handlers to avoid duplicate logs if app restarts
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        logging.basicConfig(
            filename=self.log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filemode='a'
        )
        logging.info("Application Started")

        # Fields read/written with music_tag (label -> tag key), in form order
        self.tag_map = {
            "Title": "title", "Artist": "artist", "Album": "album",
            "Album Artist": "albumartist", "Year": "year",
            "Track": "tracknumber", "Total Tracks": "totaltracks",
            "Discnumber": "discnumber", "Total Discs": "totaldiscs",
            "Genre": "genre", "Composer": "composer",
            "Compilation": "compilation", "Comment": "comment"
        }
        # Fields with an artist picker
        self.artist_keys = {"artist", "albumartist"}
        # Drop-down fields: tag key -> list of (stored value, translation key)
        self.combo_options = {
            "releasetype": [("", "rt_none")] + RELEASE_TYPES,
            "compilation": [("", "rt_none"), ("1", "yes"), ("0", "no")],
        }
        # Number fields: empty value removes the tag
        self.numeric_keys = ['tracknumber', 'totaltracks', 'year', 'discnumber',
                             'totaldiscs', 'comment', 'compilation']

        # --- ARTIST CATALOG ---
        data_dir = os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation),
            "EirekesManager")
        self.catalog_dir = data_dir
        self.bundled_catalog = resource_path("artists.json")
        self.cached_catalog = os.path.join(data_dir, "artists_remote.json")   # last download
        catalog_file = pick_catalog_file(self.bundled_catalog, self.cached_catalog)
        self.catalog = ArtistCatalog(catalog_file, os.path.join(data_dir, "artists_user.json"))
        logging.info(f"Artist catalog loaded: {len(self.catalog.names())} artists "
                     f"({'download' if catalog_file == self.cached_catalog else 'local file'})")
        self.artist_list_fetched.connect(self.on_artist_list_fetched)

        self.init_ui()
        self.init_notification_system()
        self.setup_shortcuts()
        self.setStyleSheet(DARK_THEME)

        self.load_last_folder_on_startup()

        # Check the server for a newer artist list (in the background)
        if self.settings.value("artist_list_auto", True, type=bool):
            QTimer.singleShot(500, lambda: self.update_artist_list(manual=False))

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # --- MENU BAR ---
        menu_bar = self.menuBar()

        # Language Menu
        lang_menu = menu_bar.addMenu("Language")
        action_en = QAction("English", self)
        action_en.triggered.connect(lambda: self.change_language("en"))
        lang_menu.addAction(action_en)
        action_nl = QAction("Nederlands", self)
        action_nl.triggered.connect(lambda: self.change_language("nl"))
        lang_menu.addAction(action_nl)

        # Artists Menu
        self.artist_menu = menu_bar.addMenu("")
        self.action_normalize = QAction(self)
        self.action_normalize.triggered.connect(self.normalize_selected_artists)
        self.artist_menu.addAction(self.action_normalize)
        self.action_import_artists = QAction(self)
        self.action_import_artists.triggered.connect(self.import_artists_from_csv)
        self.artist_menu.addAction(self.action_import_artists)
        self.action_artist_folder = QAction(self)
        self.action_artist_folder.triggered.connect(
            lambda: (os.makedirs(self.catalog_dir, exist_ok=True),
                     QDesktopServices.openUrl(QUrl.fromLocalFile(self.catalog_dir))))
        self.artist_menu.addAction(self.action_artist_folder)
        self.artist_menu.addSeparator()
        self.action_update_artists = QAction(self)
        self.action_update_artists.triggered.connect(lambda: self.update_artist_list(manual=True))
        self.artist_menu.addAction(self.action_update_artists)
        self.action_artist_source = QAction(self)
        self.action_artist_source.triggered.connect(self.edit_artist_list_source)
        self.artist_menu.addAction(self.action_artist_source)
        self.action_artist_auto = QAction(self)
        self.action_artist_auto.setCheckable(True)
        self.action_artist_auto.setChecked(self.settings.value("artist_list_auto", True, type=bool))
        self.action_artist_auto.toggled.connect(lambda on: self.settings.setValue("artist_list_auto", on))
        self.artist_menu.addAction(self.action_artist_auto)

        # Help Menu
        help_menu = menu_bar.addMenu("Help")
        action_logs = QAction("📂 Open Logs Folder", self)
        action_logs.triggered.connect(self.open_log_folder)
        help_menu.addAction(action_logs)

        # --- TOP TOOLBAR ---
        toolbar = QHBoxLayout()
        self.btn_web = QPushButton()
        self.btn_web.setStyleSheet("background-color: #F5B027; font-weight: bold; padding: 10px 15px;")
        self.btn_web.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_web.clicked.connect(self.open_matcher_dialog)

        self.btn_csv = QPushButton()
        self.btn_csv.setStyleSheet("background-color: #F5B027; font-weight: bold; padding: 10px 15px;")
        self.btn_csv.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_csv.clicked.connect(self.open_csv_dialog)

        self.lbl_hint = QLabel()
        self.lbl_hint.setStyleSheet("color: #aaa; font-style: italic; margin-left: 10px;")

        toolbar.addWidget(self.btn_web)
        toolbar.addWidget(self.btn_csv)
        toolbar.addWidget(self.lbl_hint)
        toolbar.addStretch()
        main_layout.addLayout(toolbar, 0)

        # --- MAIN SPLITTER ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)

        # 1. LEFT: File List
        self.left_group = QGroupBox()
        left_layout = QVBoxLayout()
        self.btn_load_folder = QPushButton()
        self.btn_load_folder.clicked.connect(self.open_folder_dialog)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list_widget.itemSelectionChanged.connect(self.on_selection_changed)

        left_layout.addWidget(self.btn_load_folder)
        left_layout.addWidget(self.file_list_widget)
        self.left_group.setLayout(left_layout)

        # 2. RIGHT: Manual Edit
        self.right_group = QGroupBox()
        right_layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignTop)

        form_widget = QWidget()
        form_widget.setStyleSheet("background-color: #2b2b2b;")
        self.form_layout = QFormLayout(form_widget)
        self.form_layout.setContentsMargins(25, 25, 25, 25)
        self.form_layout.setVerticalSpacing(20)
        self.form_layout.setHorizontalSpacing(15)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.meta_fields = {}    # label -> QLineEdit (text fields)
        self.combo_fields = {}   # tag key -> QComboBox
        self.artist_fields = []  # ArtistField widgets
        self.field_labels = {}

        # Release Type goes right after Album Artist
        form_order = []
        for label, tag_key in self.tag_map.items():
            form_order.append(tag_key)
            if tag_key == "albumartist":
                form_order.append("releasetype")
        label_by_key = {v: k for k, v in self.tag_map.items()}

        for tag_key in form_order:
            lbl_widget = QLabel()
            lbl_widget.setStyleSheet("font-weight: bold; color: #ddd;")
            self.field_labels[tag_key] = lbl_widget

            if tag_key in self.combo_options:
                cb = QComboBox()
                cb.setMinimumHeight(30)
                for value, _ in self.combo_options[tag_key]:
                    cb.addItem("", value)
                cb.activated.connect(lambda idx, k=tag_key: self.on_combo_edit(k, idx))
                self.combo_fields[tag_key] = cb
                self.form_layout.addRow(lbl_widget, cb)
                continue

            if tag_key in self.artist_keys:
                field = ArtistField(self.catalog)
                field.catalog_changed.connect(self.on_catalog_changed)
                self.artist_fields.append(field)
                le, row_widget = field.edit, field
            else:
                le = QLineEdit()
                le.setMinimumHeight(30)
                row_widget = le
            le.textEdited.connect(self.on_manual_edit)
            self.meta_fields[label_by_key[tag_key]] = le
            self.form_layout.addRow(lbl_widget, row_widget)

        scroll.setWidget(form_widget)
        right_layout.addWidget(scroll, stretch=1)

        # Cover Art
        cover_container = QVBoxLayout()
        self.lbl_cover_image = QLabel()
        self.lbl_cover_image.setFixedSize(180, 180)
        self.lbl_cover_image.setStyleSheet("border: 2px dashed #555; border-radius: 8px; background-color: #222;")
        self.lbl_cover_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_select_cover = QPushButton()
        self.btn_select_cover.setStyleSheet("background-color: #96CBD0; font-weight: bold; padding: 10px 15px;")
        self.btn_select_cover.clicked.connect(self.select_cover)

        cover_center = QHBoxLayout()
        cover_center.addStretch()
        cover_center.addWidget(self.lbl_cover_image)
        cover_center.addStretch()

        cover_container.addLayout(cover_center)
        cover_container.addWidget(self.btn_select_cover)
        right_layout.addLayout(cover_container)

        # Save Button
        self.btn_save_all = QPushButton()
        self.btn_save_all.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 12px; border-radius: 6px;")
        self.btn_save_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_all.clicked.connect(self.save_all_changes)

        right_layout.addSpacing(10)
        right_layout.addWidget(self.btn_save_all)
        self.right_group.setLayout(right_layout)

        splitter.addWidget(self.left_group)
        splitter.addWidget(self.right_group)
        splitter.setSizes([500, 400])
        main_layout.addWidget(splitter, 1)

        self.update_ui_texts()

    def change_language(self, lang_code):
        set_language(lang_code)
        self.settings.setValue("language", lang_code)
        self.update_ui_texts()

    def update_ui_texts(self):
        self.setWindowTitle(tr("app_title"))
        self.btn_web.setText(tr("web_matcher"))
        self.btn_csv.setText(tr("import_csv"))
        self.lbl_hint.setText(tr("matches_hint"))
        self.left_group.setTitle(tr("local_files"))
        self.btn_load_folder.setText(tr("open_folder"))
        self.right_group.setTitle(tr("metadata_editor"))
        self.btn_select_cover.setText(tr("choose_art"))
        self.btn_save_all.setText(tr("save_all"))

        self.lbl_hint.setStyleSheet("color: #96CBD0;")
        if self.lbl_cover_image.text() == tr("no_art"):
            self.lbl_cover_image.setText(tr("no_art"))

        for tag_key, lbl_widget in self.field_labels.items():
            trans_key = f"lbl_{tag_key}"
            lbl_widget.setText(tr(trans_key))
            lbl_widget.setStyleSheet("color: #96CBD0; font-weight: bold;")

        for tag_key, cb in self.combo_fields.items():
            for i, (_, trans_key) in enumerate(self.combo_options[tag_key]):
                cb.setItemText(i, tr(trans_key))
            cb.setPlaceholderText(tr("multiple_values"))
        for field in self.artist_fields:
            field.update_texts()

        self.artist_menu.setTitle(tr("menu_artists"))
        self.action_normalize.setText(tr("menu_normalize_artists"))
        self.action_import_artists.setText(tr("menu_import_artists"))
        self.action_artist_folder.setText(tr("menu_artist_folder"))
        self.action_update_artists.setText(tr("menu_update_artists"))
        self.action_artist_source.setText(tr("menu_artist_source"))
        self.action_artist_auto.setText(tr("menu_artist_auto"))

    def open_log_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_dir))

    # --- MATCHERS ---
    def open_matcher_dialog(self):
        current_files = self.get_current_files()
        if not current_files: return
        dialog = WebMatcherDialog(current_files, self)
        dialog.matches_confirmed.connect(self.stage_matches)
        dialog.exec()

    def open_csv_dialog(self):
        current_files = self.get_current_files()
        if not current_files: return
        dialog = CsvMatcherDialog(current_files, self)
        dialog.matches_confirmed.connect(self.stage_matches_csv)
        dialog.exec()

    def stage_matches_csv(self, files, data, album, append):
        default_opts = {'title': True, 'artist': True, 'track': True, 'rename': True, 'lyrics': False}
        self.stage_matches(files, data, album, default_opts, append)

    def stage_matches(self, reordered_files, track_data, album_data, options, append=False):
        logging.info(f"Staging matches (Append={append})...")

        if not append:
            self.pending_changes.clear()

        album_common = {}
        if album_data:
            album_common['album'] = album_data[0]
            album_common['year'] = album_data[2]

        for i, file_path in enumerate(reordered_files):
            file_data = self.pending_changes.get(file_path, {}) if append else {}

            if 'album' in album_common: file_data['album'] = album_common['album']
            if 'year' in album_common: file_data['year'] = album_common['year']
            file_data['genre'] = "Carnaval"

            web_comment = ""
            if i < len(track_data) and len(track_data[i]) > 4:
                web_comment = track_data[i][4]

            if web_comment:
                file_data['comment'] = web_comment
            else:
                file_data['comment'] = ""

            if options.get('rename'): file_data['_rename'] = True

            if i < len(track_data):
                track_info = track_data[i]
                if options.get('track'):
                     t_num = track_info[0] if len(track_info) > 0 and track_info[0] else str(i+1)
                     file_data['tracknumber'] = t_num
                if options.get('title') and len(track_info) > 1:
                    file_data['title'] = track_info[1]
                if options.get('artist') and len(track_info) > 2:
                    file_data['artist'] = self.catalog.normalize(track_info[2]) or track_info[2]
                if options.get('lyrics') and len(track_info) > 3:
                    file_data['_lyrics'] = track_info[3]
            else:
                if options.get('track'):
                    file_data['tracknumber'] = str(i+1)

            self.pending_changes[file_path] = file_data

            for j in range(self.file_list_widget.count()):
                item = self.file_list_widget.item(j)
                if item.data(Qt.ItemDataRole.UserRole) == file_path:
                    if options.get('rename'):
                        clean_title = self.sanitize_filename(file_data.get('title', 'Unknown'))
                        clean_artist = self.sanitize_filename(file_data.get('artist', 'Unknown'))
                        if not clean_title: clean_title = "Track"
                        try:
                            t_int = int(file_data.get('tracknumber', 0))
                            t_str = f"{t_int:02d}"
                        except (ValueError, TypeError):
                            t_str = "00"

                        ext = os.path.splitext(file_path)[1]
                        predicted_name = f"{t_str} - {clean_artist} - {clean_title}{ext}"
                        item.setText(f"* {predicted_name}")
                    else:
                        if not item.text().startswith("*"):
                            item.setText(f"* {item.text()}")

                    item.setForeground(QBrush(QColor("#00ffff")))
                    break

        self.show_banner(tr("staged_count").format(len(self.pending_changes)))
        self.on_selection_changed()

    # --- SAVING (FIXED IMAGE & LYRICS) ---
    def save_all_changes(self):
        if not self.pending_changes:
            self.show_banner(tr("no_changes"), is_error=True)
            return

        logging.info(f"Starting Batch Save ({len(self.pending_changes)} files)...")
        count = 0
        errors = []          # human readable messages (banner + log)
        failed = {}          # path -> changes that could NOT be saved (kept pending)
        paths_to_process = list(self.pending_changes.keys())

        def fail(path, changes_left, message):
            logging.error(message)
            errors.append(message)
            failed.setdefault(path, {}).update(changes_left)

        for file_path in paths_to_process:
            name = os.path.basename(file_path)
            changes = self.pending_changes[file_path]
            if not os.path.exists(file_path):
                fail(file_path, {}, tr("err_missing").format(name))
                continue

            if not os.access(file_path, os.W_OK):
                fail(file_path, changes, tr("err_readonly").format(name))
                continue

            current_path = file_path
            file_ext = os.path.splitext(current_path)[1].lower()
            file_ok = True

            # --- 1. SAVE TAGS (Metadata & Artwork) ---
            try:
                # A. Text tags with music_tag - one tag at a time, so one bad
                #    value never blocks the other fields of the file.
                f = music_tag.load_file(current_path)
                file_dirty = False

                for tag, new_val in changes.items():
                    if tag.startswith('_') or tag == 'releasetype': continue
                    label = tr(f"lbl_{tag}")
                    new_val, problem = clean_value(tag, new_val)
                    if problem:
                        fail(file_path, {tag: changes[tag]},
                             tr(problem).format(file=name, field=label, value=new_val))
                        file_ok = False
                        continue
                    try:
                        current_val, broken = safe_get(f, tag, current_path)
                        if broken:
                            # value in the file can't be read (e.g. "2026-08-2"): remove it first
                            logging.warning(f"{name}: invalid {tag} in file ('{current_val}') - replacing it")
                            if file_dirty:
                                f.save()
                                file_dirty = False
                            force_remove(current_path, tag)
                            f = music_tag.load_file(current_path)
                            current_val = ""

                        if tag in self.numeric_keys and new_val == "":
                            if current_val != "":
                                del f[tag]
                                file_dirty = True
                            continue

                        if tag == 'compilation':
                            if self.read_compilation(f) != new_val:
                                f[tag] = new_val == "1"
                                file_dirty = True
                            continue

                        if current_val != new_val:
                            if tag in self.numeric_keys and tag != 'comment' and current_val != "":
                                # clear the old value first (also when it is malformed), then write
                                if file_dirty:
                                    f.save()
                                    file_dirty = False
                                force_remove(current_path, tag)
                                f = music_tag.load_file(current_path)
                            f[tag] = new_val
                            file_dirty = True
                    except Exception as e:
                        fail(file_path, {tag: changes[tag]},
                             tr("err_tag").format(file=name, field=label, value=new_val, error=e))
                        file_ok = False

                if file_dirty:
                    f.save()

                # Release type (Album / Single / EP ...) via mutagen
                if 'releasetype' in changes:
                    if read_release_type(current_path) != changes['releasetype']:
                        write_release_type(current_path, changes['releasetype'])

                # B. Artwork Specifieke Afhandeling
                if '_artwork_path' in changes:
                    art_path = changes['_artwork_path']
                    if art_path and os.path.exists(art_path):

                        # 1. Converteer afbeelding naar cleane JPEG bytes
                        image = QImage(art_path)
                        if not image.isNull():
                            ba = QByteArray()
                            buf = QBuffer(ba)
                            buf.open(QIODevice.OpenModeFlag.WriteOnly)
                            image.save(buf, "JPEG", quality=85)
                            img_data = bytes(ba)

                            # 2. Opslaan afhankelijk van bestandsformaat
                            if file_ext in ['.m4a', '.mp4']:
                                # FIX: Gebruik DIRECT Mutagen voor M4A om 'atom' error te voorkomen
                                m4a_file = MP4(current_path)
                                # Verwijder oude cover(s) en zet nieuwe met expliciete JPEG vlag
                                m4a_file['covr'] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
                                m4a_file.save()

                            else:
                                # Voor MP3/FLAC werkt music_tag meestal wel prima,
                                # maar we herladen het bestand om zeker te zijn na de vorige save
                                f_art = music_tag.load_file(current_path)
                                try:
                                    del f_art['artwork']
                                except Exception:
                                    pass
                                f_art['artwork'] = img_data
                                f_art.save()

                    logging.info(tr("saved_log").format(os.path.basename(current_path)))

            except Exception as e:
                # whole file failed (corrupt file, artwork problem...): keep everything pending
                fail(file_path, changes, tr("err_file").format(file=name, error=e))
                continue

            # --- 2. RENAME ---
            try:
                # Metadata opnieuw laden voor correcte bestandsnaam
                f_ren = music_tag.load_file(current_path)

                # Gebruik nieuwe waardes uit changes als die er zijn, anders fallback naar bestand
                new_title = changes.get('title', str(f_ren['title']))
                new_artist = changes.get('artist', str(f_ren['artist']))
                track_num = changes.get('tracknumber', str(f_ren['tracknumber']))

                try:
                    t_int = int(track_num)
                    t_str = f"{t_int:02d}"
                except (ValueError, TypeError):
                    t_str = "00"

                clean_title = self.sanitize_filename(new_title)
                clean_artist = self.sanitize_filename(new_artist)

                if not clean_title: clean_title = "Unknown"
                if not clean_artist: clean_artist = "Unknown"

                folder = os.path.dirname(current_path)
                ext = os.path.splitext(current_path)[1]
                new_filename = f"{t_str} - {clean_artist} - {clean_title}{ext}"
                new_full_path = os.path.join(folder, new_filename)

                if changes.get('_rename'):
                    if current_path != new_full_path:
                        shutil.move(current_path, new_full_path)
                        logging.info(tr("renamed_log").format(new_filename))
                        current_path = new_full_path

            except Exception as e:
                fail(current_path, {}, tr("err_rename").format(file=name, error=e))
                file_ok = False

            # --- 3. LYRICS ---
            try:
                if '_lyrics' in changes and changes['_lyrics']:
                    lrc_path = os.path.splitext(current_path)[0] + ".txt"
                    with open(lrc_path, 'w', encoding='utf-8') as lrc_file:
                        lrc_file.write(changes['_lyrics'])
                    logging.info(tr("lyrics_log").format(lrc_path))

            except Exception as e:
                fail(current_path, {}, tr("err_lyrics").format(file=name, error=e))
                file_ok = False

            if file_ok:
                count += 1

        self.pending_changes.clear()

        if paths_to_process:
            self.reload_file_list(os.path.dirname(paths_to_process[0]))

        # Keep what failed as pending (red in the list) so nothing typed is lost
        for path, left in failed.items():
            if left and os.path.exists(path):
                self.pending_changes[path] = left
        for j in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(j)
            if item.data(Qt.ItemDataRole.UserRole) in failed:
                item.setForeground(QBrush(QColor("#ff6b6b")))
                item.setText(f"! {item.text()}")
                item.setToolTip("\n".join(e for e in errors
                                           if os.path.basename(item.data(Qt.ItemDataRole.UserRole)) in e))

        if errors:
            more = f" (+{len(errors) - 1})" if len(errors) > 1 else ""
            self.show_banner(errors[0] + more, is_error=True, duration=8000)
            if count > 0:
                logging.info(tr("save_success").format(count))
        elif count > 0:
            self.show_banner(tr("save_success").format(count))
    # --- HELPERS ---
    def get_current_files(self):
        current_files = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            current_files.append(item.data(Qt.ItemDataRole.UserRole))
        if not current_files:
            self.show_banner(tr("please_load"), is_error=True)
            return None
        return current_files

    def on_selection_changed(self):
        selected_items = self.file_list_widget.selectedItems()
        for le in self.meta_fields.values(): le.blockSignals(True)

        if len(selected_items) == 0:
            self.clear_fields()
        elif len(selected_items) == 1:
            path = selected_items[0].data(Qt.ItemDataRole.UserRole)
            data = self.get_effective_metadata(path)
            for label, le in self.meta_fields.items():
                le.setPlaceholderText("")
                le.setText(data.get(self.tag_map[label], ""))
            for tag_key in self.combo_fields:
                self.set_combo_value(tag_key, data.get(tag_key, ""))
            self.load_cover_from_file(path)
        else:
            self.lbl_cover_image.setText(tr("multiple_selected"))
            self.lbl_cover_image.setPixmap(QPixmap())
            first_path = selected_items[0].data(Qt.ItemDataRole.UserRole)
            common_values = self.get_effective_metadata(first_path)
            for i in range(1, len(selected_items)):
                path = selected_items[i].data(Qt.ItemDataRole.UserRole)
                next_values = self.get_effective_metadata(path)
                for key in list(common_values.keys()):
                    if common_values[key] != next_values.get(key, ""):
                        common_values[key] = None
            for label, le in self.meta_fields.items():
                val = common_values.get(self.tag_map[label], "")
                if val is None:
                    le.setText("")
                    le.setPlaceholderText(tr("multiple_values"))
                else:
                    le.setPlaceholderText("")
                    le.setText(val)
            for tag_key in self.combo_fields:
                self.set_combo_value(tag_key, common_values.get(tag_key, ""))

        for le in self.meta_fields.values():
            le.blockSignals(False)
            le.setStyleSheet("")   # clear a red "invalid value" border from the previous file
            le.setToolTip("")
        for field in self.artist_fields: field.refresh_hint()

    def get_effective_metadata(self, path):
        disk_data = {}
        try:
            f = music_tag.load_file(path)
        except Exception as e:
            logging.error(f"Cannot read {os.path.basename(path)}: {e}")
            f = None
        if f is not None:
            for _, tag_key in self.tag_map.items():
                if tag_key == 'compilation':
                    disk_data[tag_key] = self.read_compilation(f)
                    continue
                disk_data[tag_key], _broken = safe_get(f, tag_key, path)
                if tag_key in ('totaltracks', 'totaldiscs') and disk_data[tag_key] == "0":
                    disk_data[tag_key] = ""
        disk_data['releasetype'] = read_release_type(path)
        if path in self.pending_changes:
            pending = self.pending_changes[path]
            for key, val in pending.items():
                if not key.startswith('_'): disk_data[key] = val
        return disk_data

    def on_manual_edit(self, text):
        sender = self.sender()
        target_label = None
        for label, le in self.meta_fields.items():
            if le == sender: target_label = label; break
        if not target_label: return
        tag_key = self.tag_map[target_label]

        # Show right away when a number/year field can't be saved
        _, problem = clean_value(tag_key, text)
        if problem:
            sender.setStyleSheet("border: 1px solid #ff6b6b;")
            sender.setToolTip(tr(f"{problem}_hint"))
        else:
            sender.setStyleSheet("")
            sender.setToolTip("")

        selected_items = self.file_list_widget.selectedItems()
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path not in self.pending_changes: self.pending_changes[path] = {}
            self.pending_changes[path][tag_key] = text
            item.setForeground(QBrush(QColor("#00ffff")))
            if not item.text().startswith("*"): item.setText(f"* {item.text()}")

    def read_compilation(self, f):
        """'1' / '0' / '' (not set) from a music_tag file."""
        try:
            raw = f.raw['compilation']
            if raw is None or raw.value is None or str(raw) == "":
                return ""
            return "1" if raw.first else "0"
        except Exception:
            return ""

    def set_combo_value(self, tag_key, value):
        """Select value in a drop-down; None = multiple different values."""
        cb = self.combo_fields[tag_key]
        cb.blockSignals(True)
        if value is None:
            cb.setCurrentIndex(-1)  # shows the "<Multiple Values>" placeholder
        else:
            idx = cb.findData(value)
            if idx < 0:  # unknown value in the file, e.g. "mixtape"
                cb.addItem(value, value)
                idx = cb.count() - 1
            cb.setCurrentIndex(idx)
        cb.blockSignals(False)

    def on_combo_edit(self, tag_key, index):
        value = self.combo_fields[tag_key].itemData(index)
        if value is None:
            return
        self.stage_value_for_selection(tag_key, value)

    def stage_value_for_selection(self, tag_key, value):
        for item in self.file_list_widget.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            self.pending_changes.setdefault(path, {})[tag_key] = value
            item.setForeground(QBrush(QColor("#00ffff")))
            if not item.text().startswith("*"): item.setText(f"* {item.text()}")

    # --- ARTISTS ---
    def on_catalog_changed(self):
        for field in self.artist_fields:
            field.refresh_hint()

    def normalize_selected_artists(self):
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            selected_items = [self.file_list_widget.item(i) for i in range(self.file_list_widget.count())]
        if not selected_items:
            self.show_banner(tr("please_load"), is_error=True)
            return
        changed = 0
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            data = self.get_effective_metadata(path)
            for key in self.artist_keys:
                current = data.get(key, "")
                fixed = self.catalog.normalize(current)
                if current and fixed and fixed != current:
                    self.pending_changes.setdefault(path, {})[key] = fixed
                    item.setForeground(QBrush(QColor("#00ffff")))
                    if not item.text().startswith("*"): item.setText(f"* {item.text()}")
                    changed += 1
                    logging.info(f"Artist normalized: '{current}' -> '{fixed}' ({os.path.basename(path)})")
        self.show_banner(tr("artists_normalized").format(changed))
        self.on_selection_changed()

    # --- ONLINE ARTIST LIST ---
    def artist_list_url(self):
        return to_raw_url(self.settings.value("artist_list_url", DEFAULT_URL) or DEFAULT_URL)

    def update_artist_list(self, manual=False):
        url = self.artist_list_url()
        token = self.settings.value("artist_list_token", "") or None
        if manual:
            self.show_banner(tr("artists_checking"))
        fetch_in_background(url, self.cached_catalog, token,
                            lambda status, msg: self.artist_list_fetched.emit(status, msg, manual))

    def on_artist_list_fetched(self, status, message, manual):
        if status == "updated":
            self.catalog.reload(self.cached_catalog)
            self.on_catalog_changed()
            self.on_selection_changed()
            self.show_banner(tr("artists_updated").format(len(self.catalog.names())))
        elif status == "unchanged":
            if manual:
                self.show_banner(tr("artists_uptodate"))
        else:
            # offline / server down: keep using the local copy, only bother the user on request
            logging.warning(f"Artist list not updated: {message}")
            if manual:
                self.show_banner(tr("artists_update_error").format(message), is_error=True, duration=8000)

    def edit_artist_list_source(self):
        url, ok = QInputDialog.getText(self, tr("artist_source_title"), tr("artist_source_url"),
                                       text=self.settings.value("artist_list_url", DEFAULT_URL) or DEFAULT_URL)
        if not ok:
            return
        token, ok = QInputDialog.getText(self, tr("artist_source_title"), tr("artist_source_token"),
                                         QLineEdit.EchoMode.Password,
                                         self.settings.value("artist_list_token", "") or "")
        if not ok:
            return
        self.settings.setValue("artist_list_url", url.strip() or DEFAULT_URL)
        self.settings.setValue("artist_list_token", token.strip())
        self.update_artist_list(manual=True)

    def import_artists_from_csv(self):
        start_dir = self.settings.value("last_folder", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, tr("menu_import_artists"), start_dir, "CSV (*.csv)")
        if not path:
            return
        try:
            found = artists_from_plex_csv(path)
            added = self.catalog.merge_from(found)
            self.show_banner(tr("artists_imported").format(added))
            self.on_catalog_changed()
        except Exception as e:
            logging.error(f"Artist import failed: {e}")
            self.show_banner(f"{tr('csv_error')}: {e}", is_error=True)

    def load_cover_from_file(self, path, f=None):
        try:
            if not f: f = music_tag.load_file(path)
            art = f['artwork']
            if art:
                img_data = art.first.data
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)
                self.lbl_cover_image.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.lbl_cover_image.setText(tr("no_art"))
                self.lbl_cover_image.setPixmap(QPixmap())
        except Exception:
            self.lbl_cover_image.setText(tr("no_art"))

    def select_cover(self):
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            self.show_banner(tr("please_load"), is_error=True)
            return

        start_dir = self.settings.value("last_folder", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, "Select Image", start_dir, "Images (*.jpg *.png)")

        if path:
            pixmap = QPixmap(path)
            self.lbl_cover_image.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

            for item in selected_items:
                f_path = item.data(Qt.ItemDataRole.UserRole)
                if f_path not in self.pending_changes:
                    self.pending_changes[f_path] = {}
                self.pending_changes[f_path]['_artwork_path'] = path

                item.setForeground(QBrush(QColor("#00ffff")))
                if not item.text().startswith("*"):
                    item.setText(f"* {item.text()}")

            self.show_banner(tr("staged_count").format(len(self.pending_changes)))

    def clear_fields(self):
        for le in self.meta_fields.values(): le.clear(); le.setPlaceholderText("")
        for tag_key in self.combo_fields: self.set_combo_value(tag_key, "")
        self.lbl_cover_image.setText(tr("no_art")); self.lbl_cover_image.setPixmap(QPixmap())

    def sanitize_filename(self, name):
        return re.sub(r'[<>:"/\\|?*]', '', name).strip()

    def load_last_folder_on_startup(self):
        last_folder = self.settings.value("last_folder", "")
        if last_folder and os.path.exists(last_folder):
            self.reload_file_list(last_folder)
            self.show_banner(f"Restored folder: {os.path.basename(last_folder)}")

    def open_folder_dialog(self):
        start_dir = self.settings.value("last_folder", os.path.expanduser("~"))
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder", start_dir)
        if folder:
            self.settings.setValue("last_folder", folder)
            self.reload_file_list(folder)

    def reload_file_list(self, folder):
        self.file_list_widget.clear()
        self.pending_changes.clear()
        try:
            files = sorted([f for f in os.listdir(folder) if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav'))])
            for f in files:
                full_path = os.path.join(folder, f)
                item = QListWidgetItem(f)
                item.setData(Qt.ItemDataRole.UserRole, full_path)
                self.file_list_widget.addItem(item)
        except OSError: pass

    def init_notification_system(self):
        self.notification = QLabel(self)
        self.notification.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification.hide()
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.notification.setGraphicsEffect(shadow)

    def show_banner(self, message, is_error=False, duration=3000):
        bg_color = "#d32f2f" if is_error else "#28a745"
        self.notification.setStyleSheet(f"QLabel {{ background-color: {bg_color}; color: white; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 13px; border: 1px solid #444; }}")
        self.notification.setWordWrap(True)
        self.notification.setMaximumWidth(max(300, min(700, self.width() - 50)))
        self.notification.setText(message)
        self.notification.adjustSize()
        x_pos = self.width() - self.notification.width() - 25
        y_pos = 25
        self.notification.move(x_pos, y_pos)
        self.notification.show()
        self.notification.raise_()
        # one timer, so an older banner's timer can't hide a newer (error) banner early
        if not hasattr(self, "_banner_timer"):
            self._banner_timer = QTimer(self)
            self._banner_timer.setSingleShot(True)
            self._banner_timer.timeout.connect(self.notification.hide)
        self._banner_timer.start(duration)

    def resizeEvent(self, event):
        if self.notification.isVisible():
            x_pos = self.width() - self.notification.width() - 25
            y_pos = 25
            self.notification.move(x_pos, y_pos)
        super().resizeEvent(event)

    def setup_shortcuts(self):
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.activated.connect(self.save_all_changes)