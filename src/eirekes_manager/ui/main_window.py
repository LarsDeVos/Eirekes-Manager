# src/eirekes_manager/ui/main_window.py
"""Main window: file list + metadata editor. Saving etc. lives in core/."""

import os
import logging
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFileDialog,
                             QListWidget, QAbstractItemView, QGroupBox,
                             QSplitter, QFormLayout, QScrollArea,
                             QListWidgetItem, QGraphicsDropShadowEffect,
                             QComboBox, QInputDialog)
from PyQt6.QtCore import (Qt, QTimer, QSettings, QUrl, QBuffer, QIODevice, QByteArray,
                          QStandardPaths, pyqtSignal)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor, QBrush, QAction, QDesktopServices, QImage

import music_tag

from ..core.artist_catalog import ArtistCatalog, artists_from_plex_csv
from ..core.artist_sync import DEFAULT_URL, to_raw_url, pick_catalog_file, fetch_in_background
from ..core.filenames import list_audio_files, track_filename
from ..core.metadata import (TAG_MAP, ARTIST_KEYS, COMBO_OPTIONS, form_order,
                             effective_metadata, common_values)
from ..core.staging import CSV_OPTIONS, build_staged_changes
from ..core.tag_values import clean_value
from ..core.tag_writer import save_pending
from ..i18n import tr, set_language
from ..paths import resource_path, setup_logging
from .artist_field import ArtistField
from .csv_matcher import CsvMatcherDialog
from .styles import DARK_THEME
from .web_matcher import WebMatcherDialog

STAGED_COLOR = "#00ffff"
FAILED_COLOR = "#ff6b6b"


def image_to_jpeg(path):
    """Image file -> clean JPEG bytes (None when Qt can't read it)."""
    image = QImage(path)
    if image.isNull():
        return None
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "JPEG", quality=85)
    return bytes(ba)


class MusicTaggerApp(QMainWindow):
    # (status, message, manual) - emitted from the download thread
    artist_list_fetched = pyqtSignal(str, str, bool)

    def __init__(self, settings=None, data_dir=None, log_dir=None):
        """settings / data_dir / log_dir can be passed in by tests."""
        super().__init__()
        self.settings = settings or QSettings("OilsjterseLiekes", "MetadataMaster")

        # Load Language Preference
        saved_lang = self.settings.value("language", "en")
        set_language(saved_lang)

        self.setWindowTitle(tr("app_title"))
        self.resize(1200, 800)

        self.pending_changes = {}

        # --- LOGGING SETUP ---
        self.log_dir = setup_logging(log_dir) if log_dir else setup_logging()
        logging.info("Application Started")

        self.tag_map = TAG_MAP
        self.artist_keys = ARTIST_KEYS
        self.combo_options = COMBO_OPTIONS

        # --- ARTIST CATALOG ---
        data_dir = data_dir or os.path.join(
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

        label_by_key = {v: k for k, v in self.tag_map.items()}

        for tag_key in form_order():
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
        self.stage_matches(files, data, album, CSV_OPTIONS, append)

    def stage_matches(self, reordered_files, track_data, album_data, options, append=False):
        logging.info(f"Staging matches (Append={append})...")

        staged = build_staged_changes(reordered_files, track_data, album_data, options,
                                      normalize_artist=self.catalog.normalize,
                                      existing=self.pending_changes if append else None)
        if not append:
            self.pending_changes.clear()
        self.pending_changes.update(staged)

        for item in self.list_items():
            file_path = item.data(Qt.ItemDataRole.UserRole)
            if file_path not in staged:
                continue
            if options.get('rename'):
                file_data = staged[file_path]
                predicted_name = track_filename(file_data.get('tracknumber', 0),
                                                file_data.get('artist'), file_data.get('title'),
                                                os.path.splitext(file_path)[1])
                item.setText(f"* {predicted_name}")
            self.mark_staged(item)

        self.show_banner(tr("staged_count").format(len(self.pending_changes)))
        self.on_selection_changed()

    # --- SAVING ---
    def save_all_changes(self):
        if not self.pending_changes:
            self.show_banner(tr("no_changes"), is_error=True)
            return

        batch = save_pending(self.pending_changes, image_to_jpeg)

        self.pending_changes.clear()
        if batch.paths:
            self.reload_file_list(os.path.dirname(batch.paths[0]))

        # Keep what failed as pending (red in the list) so nothing typed is lost
        for path, left in batch.failed.items():
            if left and os.path.exists(path):
                self.pending_changes[path] = left
        for item in self.list_items():
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in batch.failed:
                item.setForeground(QBrush(QColor(FAILED_COLOR)))
                item.setText(f"! {item.text()}")
                item.setToolTip("\n".join(e for e in batch.errors if os.path.basename(path) in e))

        if batch.errors:
            more = f" (+{len(batch.errors) - 1})" if len(batch.errors) > 1 else ""
            self.show_banner(batch.errors[0] + more, is_error=True, duration=8000)
            if batch.count > 0:
                logging.info(tr("save_success").format(batch.count))
        elif batch.count > 0:
            self.show_banner(tr("save_success").format(batch.count))

    # --- HELPERS ---
    def list_items(self):
        return [self.file_list_widget.item(i) for i in range(self.file_list_widget.count())]

    def mark_staged(self, item):
        """Show a file as changed (cyan, with a '*')."""
        item.setForeground(QBrush(QColor(STAGED_COLOR)))
        if not item.text().startswith("*"):
            item.setText(f"* {item.text()}")

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
            common = common_values([self.get_effective_metadata(item.data(Qt.ItemDataRole.UserRole))
                                    for item in selected_items])
            for label, le in self.meta_fields.items():
                val = common.get(self.tag_map[label], "")
                if val is None:
                    le.setText("")
                    le.setPlaceholderText(tr("multiple_values"))
                else:
                    le.setPlaceholderText("")
                    le.setText(val)
            for tag_key in self.combo_fields:
                self.set_combo_value(tag_key, common.get(tag_key, ""))

        for le in self.meta_fields.values():
            le.blockSignals(False)
            le.setStyleSheet("")   # clear a red "invalid value" border from the previous file
            le.setToolTip("")
        for field in self.artist_fields: field.refresh_hint()

    def get_effective_metadata(self, path):
        return effective_metadata(path, self.pending_changes.get(path))

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

        self.stage_value_for_selection(tag_key, text)

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
            self.mark_staged(item)

    # --- ARTISTS ---
    def on_catalog_changed(self):
        for field in self.artist_fields:
            field.refresh_hint()

    def normalize_selected_artists(self):
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            selected_items = self.list_items()
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
                    self.mark_staged(item)
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
                self.mark_staged(item)

            self.show_banner(tr("staged_count").format(len(self.pending_changes)))

    def clear_fields(self):
        for le in self.meta_fields.values(): le.clear(); le.setPlaceholderText("")
        for tag_key in self.combo_fields: self.set_combo_value(tag_key, "")
        self.lbl_cover_image.setText(tr("no_art")); self.lbl_cover_image.setPixmap(QPixmap())

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
        for f in list_audio_files(folder):
            item = QListWidgetItem(f)
            item.setData(Qt.ItemDataRole.UserRole, os.path.join(folder, f))
            self.file_list_widget.addItem(item)

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