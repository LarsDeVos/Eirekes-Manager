import os
import re
import logging
import music_tag
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFileDialog, 
                             QListWidget, QAbstractItemView, QGroupBox, 
                             QMessageBox, QSplitter, QFormLayout, QScrollArea, 
                             QListWidgetItem, QGraphicsDropShadowEffect, QMenuBar, QMenu)
from PyQt6.QtCore import Qt, QTimer, QSettings, QUrl, QBuffer, QIODevice
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor, QBrush, QAction, QDesktopServices, QImage

from matcher import WebMatcherDialog
from csv_matcher import CsvMatcherDialog
from styles import DARK_THEME
from app_translations import tr, set_language, get_current_language
from mutagen.mp4 import MP4, MP4Cover

class MusicTaggerApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings("OilsjterseLiekes", "MetadataMaster")
        saved_lang = self.settings.value("language", "en")
        set_language(saved_lang)

        self.setWindowTitle(tr("app_title"))
        self.resize(1200, 800)

        self.pending_changes = {}

        # --- LOGGING ---
        self.log_dir = os.path.join(os.path.expanduser("~"), "EirekesManagerLogs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "application.log")

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        logging.basicConfig(
            filename=self.log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filemode="a"
        )

        logging.info("Application Started")

        self.tag_map = {
            "Title": "title",
            "Artist": "artist",
            "Album": "album",
            "Year": "year",
            "Track": "tracknumber",
            "Genre": "genre",
            "Album Artist": "albumartist",
            "Composer": "composer",
            "Discnumber": "discnumber",
            "Comment": "comment"
        }

        self.init_ui()
        self.init_notification_system()
        self.setup_shortcuts()
        self.setStyleSheet(DARK_THEME)
        self.load_last_folder_on_startup()

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
        
        self.meta_fields = {}
        self.field_labels = {} 
        
        for label, tag_key in self.tag_map.items():
            le = QLineEdit()
            le.setMinimumHeight(30)
            le.textEdited.connect(self.on_manual_edit) 
            self.meta_fields[label] = le
            
            lbl_widget = QLabel()
            lbl_widget.setStyleSheet("font-weight: bold; color: #ddd;")
            self.field_labels[tag_key] = lbl_widget
            self.form_layout.addRow(lbl_widget, le)
            
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
        if self.lbl_cover_image.text() in ["No Art", "Geen Cover"]:
            self.lbl_cover_image.setText(tr("no_art"))
            
        for tag_key, lbl_widget in self.field_labels.items():
            trans_key = f"lbl_{tag_key}"
            lbl_widget.setText(tr(trans_key))
            lbl_widget.setStyleSheet("color: #96CBD0; font-weight: bold;")

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
                    file_data['artist'] = track_info[2]
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
                        except: t_str = "00"
                        
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

    # --- SAVING (IMPROVED ERROR HANDLING & IMAGE CONVERSION) ---
    def save_all_changes(self):
        if not self.pending_changes:
            self.show_banner(tr("no_changes"), is_error=True)
            return

        logging.info("Starting Batch Save...")
        count = 0
        errors = []

        paths = list(self.pending_changes.keys())

        for file_path in paths:
            if not os.path.exists(file_path):
                continue

            saved_something = False

            try:
                f = music_tag.load_file(file_path)
                changes = self.pending_changes[file_path]

                # -------- NORMAL TAGS --------
                for tag, value in changes.items():
                    if tag.startswith("_"):
                        continue
                    if str(f[tag] or "") != value:
                        f[tag] = value
                        saved_something = True

                if saved_something:
                    f.save()

                # -------- ARTWORK --------
                if "_artwork_path" in changes:
                    art_path = changes["_artwork_path"]
                    image = QImage(art_path)

                    if not image.isNull():
                        buf = QBuffer()
                        buf.open(QIODevice.OpenModeFlag.ReadWrite)
                        image.save(buf, "PNG")
                        img_data = bytes(buf.data())

                        ext = os.path.splitext(file_path)[1].lower()

                        if ext in (".m4a", ".mp4"):
                            mp4 = MP4(file_path)

                            if img_data.startswith(b"\x89PNG"):
                                cover = MP4Cover(img_data, MP4Cover.FORMAT_PNG)
                            else:
                                cover = MP4Cover(img_data, MP4Cover.FORMAT_JPEG)

                            mp4.tags["covr"] = [cover]
                            mp4.save()
                            saved_something = True
                        else:
                            f["artwork"] = img_data
                            f.save()
                            saved_something = True

                if saved_something:
                    count += 1

                # -------- RENAME / LYRICS --------
                f = music_tag.load_file(file_path)

                title = self.sanitize_filename(str(f["title"] or "Unknown"))
                artist = self.sanitize_filename(str(f["artist"] or "Unknown"))
                track = str(f["tracknumber"] or "0").zfill(2)

                folder = os.path.dirname(file_path)
                ext = os.path.splitext(file_path)[1]
                new_path = os.path.join(folder, f"{track} - {artist} - {title}{ext}")

                if changes.get("_rename") and file_path != new_path:
                    os.rename(file_path, new_path)

            except Exception as e:
                err = f"Tag Error ({os.path.basename(file_path)}): {e}"
                logging.error(err)
                errors.append(err)

        self.pending_changes.clear()
        self.reload_file_list(os.path.dirname(paths[0]))

        if count:
            self.show_banner(tr("save_success").format(count))
        if errors:
            self.show_banner(f"Errors: {len(errors)} – check logs", is_error=True)

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
            for label, tag_key in self.tag_map.items():
                self.meta_fields[label].setText(data.get(tag_key, ""))
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
            for label, tag_key in self.tag_map.items():
                val = common_values.get(tag_key, "")
                if val is None:
                    self.meta_fields[label].setText("")
                    self.meta_fields[label].setPlaceholderText("<Multiple Values>")
                else:
                    self.meta_fields[label].setText(val)
            
        for le in self.meta_fields.values(): le.blockSignals(False)

    def get_effective_metadata(self, path):
        disk_data = {}
        try:
            f = music_tag.load_file(path)
            for _, tag_key in self.tag_map.items():
                val = f[tag_key]
                disk_data[tag_key] = str(val) if val else ""
        except: pass 
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
        
        selected_items = self.file_list_widget.selectedItems()
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path not in self.pending_changes: self.pending_changes[path] = {}
            self.pending_changes[path][tag_key] = text
            item.setForeground(QBrush(QColor("#00ffff")))
            if not item.text().startswith("*"): item.setText(f"* {item.text()}")

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
        except: self.lbl_cover_image.setText(tr("no_art"))

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

    def show_banner(self, message, is_error=False):
        bg_color = "#d32f2f" if is_error else "#28a745"
        self.notification.setStyleSheet(f"QLabel {{ background-color: {bg_color}; color: white; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 13px; border: 1px solid #444; }}")
        self.notification.setText(message)
        self.notification.adjustSize()
        x_pos = self.width() - self.notification.width() - 25
        y_pos = 25
        self.notification.move(x_pos, y_pos)
        self.notification.show()
        self.notification.raise_()
        QTimer.singleShot(3000, self.notification.hide)

    def resizeEvent(self, event):
        if self.notification.isVisible():
            x_pos = self.width() - self.notification.width() - 25
            y_pos = 25
            self.notification.move(x_pos, y_pos)
        super().resizeEvent(event)

    def setup_shortcuts(self):
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.activated.connect(self.save_all_changes)