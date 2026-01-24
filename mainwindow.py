import os
import re
import logging
import music_tag
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFileDialog, 
                             QListWidget, QAbstractItemView, QGroupBox, 
                             QMessageBox, QSplitter, QFormLayout, QScrollArea, 
                             QListWidgetItem, QGraphicsDropShadowEffect)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor, QBrush

from matcher import WebMatcherDialog
from csv_matcher import CsvMatcherDialog
from styles import DARK_THEME

class MusicTaggerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Metadata Master")
        self.resize(1200, 800)
        self.cover_image_path = None
        self.pending_changes = {} 

        logging.basicConfig(
            filename='application.log', 
            level=logging.INFO, 
            format='%(asctime)s - %(levelname)s - %(message)s',
            filemode='a'
        )
        logging.info("Application Started")

        self.settings = QSettings("OilsjterseLiekes", "MetadataMaster")

        self.tag_map = {
            "Title": "title", "Artist": "artist", "Album": "album",
            "Year": "year", "Track": "tracknumber", "Genre": "genre",
            "Album Artist": "albumartist", "Composer": "composer",
            "Discnumber": "discnumber", "Comment": "comment"
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

        # --- TOP TOOLBAR ---
        toolbar = QHBoxLayout()
        
        btn_web = QPushButton("🌍 Web Matcher")
        btn_web.setStyleSheet("background-color: #007bff; font-weight: bold; padding: 10px 15px;")
        btn_web.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_web.clicked.connect(self.open_matcher_dialog)

        btn_csv = QPushButton("📊 Import CSV")
        btn_csv.setStyleSheet("background-color: #6f42c1; font-weight: bold; padding: 10px 15px;")
        btn_csv.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_csv.clicked.connect(self.open_csv_dialog)
        
        lbl_hint = QLabel("Matches are staged in CYAN. Ctrl+S to Commit.")
        lbl_hint.setStyleSheet("color: #aaa; font-style: italic; margin-left: 10px;")

        toolbar.addWidget(btn_web)
        toolbar.addWidget(btn_csv)
        toolbar.addWidget(lbl_hint)
        toolbar.addStretch()
        main_layout.addLayout(toolbar, 0)

        # --- MAIN SPLITTER ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        
        # 1. LEFT: File List
        left_group = QGroupBox("Local Files")
        left_layout = QVBoxLayout()
        btn_load_folder = QPushButton("📂 Open Folder")
        btn_load_folder.clicked.connect(self.open_folder_dialog)
        
        self.file_list_widget = QListWidget()
        self.file_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        
        left_layout.addWidget(btn_load_folder)
        left_layout.addWidget(self.file_list_widget)
        left_group.setLayout(left_layout)
        
        # 2. RIGHT: Manual Edit
        right_group = QGroupBox("Metadata Editor")
        right_layout = QVBoxLayout()
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form_widget.setStyleSheet("background-color: #2b2b2b;")
        self.form_layout = QFormLayout(form_widget)
        
        self.meta_fields = {}
        for label, tag_key in self.tag_map.items():
            le = QLineEdit()
            le.textEdited.connect(self.on_manual_edit) 
            self.meta_fields[label] = le
            self.form_layout.addRow(label, le)
            
        scroll.setWidget(form_widget)
        right_layout.addWidget(scroll, stretch=1)

        # Cover Art
        cover_container = QVBoxLayout()
        self.lbl_cover_image = QLabel("No Art")
        self.lbl_cover_image.setFixedSize(180, 180)
        self.lbl_cover_image.setStyleSheet("border: 2px dashed #555; border-radius: 8px; background-color: #222;")
        self.lbl_cover_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn_select_cover = QPushButton("🖼️ Choose Art")
        btn_select_cover.clicked.connect(self.select_cover)
        
        cover_center = QHBoxLayout()
        cover_center.addStretch()
        cover_center.addWidget(self.lbl_cover_image)
        cover_center.addStretch()
        
        cover_container.addLayout(cover_center)
        cover_container.addWidget(btn_select_cover)
        right_layout.addLayout(cover_container)

        # Save Button
        self.btn_save_all = QPushButton("💾 Save ALL Pending Changes (Ctrl+S)")
        self.btn_save_all.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 12px; border-radius: 6px;")
        self.btn_save_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_all.clicked.connect(self.save_all_changes)
        
        right_layout.addSpacing(10)
        right_layout.addWidget(self.btn_save_all)
        right_group.setLayout(right_layout)

        splitter.addWidget(left_group)
        splitter.addWidget(right_group)
        splitter.setSizes([500, 400])
        main_layout.addWidget(splitter, 1)

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
        # Default options for CSV (Enable everything)
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
            
            # Store special options
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

                if options.get('lyrics'):
                    print("LYRICS STAGED:", bool(track_info[3]))
            else:
                if options.get('track'):
                    file_data['tracknumber'] = str(i+1)
            
            self.pending_changes[file_path] = file_data
            
            # Update Visuals
            for j in range(self.file_list_widget.count()):
                item = self.file_list_widget.item(j)
                if item.data(Qt.ItemDataRole.UserRole) == file_path:
                    # Rename Preview
                    if options.get('rename'):
                        clean_title = self.sanitize_filename(file_data.get('title', 'Unknown'))
                        if not clean_title: clean_title = "Track"
                        try:
                            t_int = int(file_data.get('tracknumber', 0))
                            t_str = f"{t_int:02d}"
                        except: t_str = "00"
                        
                        ext = os.path.splitext(file_path)[1]
                        predicted_name = f"{t_str} - {clean_title}{ext}"
                        item.setText(f"* {predicted_name}")
                    else:
                        if not item.text().startswith("*"):
                            item.setText(f"* {item.text()}")
                            
                    item.setForeground(QBrush(QColor("#00ffff")))
                    break

        self.show_banner(f"Staged {len(self.pending_changes)} files. Press Ctrl+S to Commit.")

    # --- SAVING ---
    def save_all_changes(self):
        if not self.pending_changes:
            self.show_banner("No changes staged to save.", is_error=True)
            return

        logging.info("Starting Batch Save...")
        count = 0
        errors = []
        paths_to_process = list(self.pending_changes.keys())

        for file_path in paths_to_process:
            if not os.path.exists(file_path): continue
            
            changes = self.pending_changes[file_path]
            try:
                f = music_tag.load_file(file_path)
                file_dirty = False
                
                for tag, new_val in changes.items():
                    if tag.startswith('_'): continue 
                    
                    if tag in ['tracknumber', 'year', 'discnumber']:
                        if new_val == "": 
                            if f[tag] is not None and str(f[tag]) != "":
                                f[tag] = None
                                file_dirty = True
                            continue
                    
                    current_val = str(f[tag]) if f[tag] else ""
                    if current_val != new_val:
                        f[tag] = new_val
                        file_dirty = True

                if self.cover_image_path:
                    with open(self.cover_image_path, 'rb') as img:
                        f['artwork'] = img.read()
                    file_dirty = True
                
                if file_dirty:
                    f.save()
                    logging.info(f"Saved metadata for {os.path.basename(file_path)}")

                new_title = str(f['title'])
                track_num = str(f['tracknumber'])
                try: 
                    t_int = int(track_num) 
                    t_str = f"{t_int:02d}"
                except: t_str = "00"
                clean_title = self.sanitize_filename(new_title)
                if not clean_title: clean_title = "Unknown"
                
                folder = os.path.dirname(file_path)
                ext = os.path.splitext(file_path)[1]
                new_filename = f"{t_str} - {clean_title}{ext}"
                new_path = os.path.join(folder, new_filename)
                
                # Rename if requested
                if changes.get('_rename'):
                    if file_path != new_path:
                        os.rename(file_path, new_path)
                        logging.info(f"Renamed to {new_filename}")
                        file_path = new_path 
                
                # Save Lyrics
                if '_lyrics' in changes and changes['_lyrics']:
                    lrc_path = os.path.splitext(file_path)[0] + ".lrc"
                    with open(lrc_path, 'w', encoding='utf-8') as lrc_file:
                        lrc_file.write(changes['_lyrics'])
                    logging.info(f"Created lyrics file: {lrc_path}")

                count += 1
            except Exception as e:
                err_msg = f"Error processing {os.path.basename(file_path)}: {e}"
                logging.error(err_msg)
                errors.append(err_msg)

        self.pending_changes.clear()
        if paths_to_process:
            self.reload_file_list(os.path.dirname(paths_to_process[0]))

        if count > 0:
            self.show_banner(f"Processed {count} files successfully!")
        if errors:
            self.show_banner(f"Errors with {len(errors)} files.", is_error=True)

    # --- HELPERS ---
    def get_current_files(self):
        current_files = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            current_files.append(item.data(Qt.ItemDataRole.UserRole))
        if not current_files:
            self.show_banner("Please load a folder with music files first.", is_error=True)
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
            self.lbl_cover_image.setText("Multiple Selected")
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
                self.lbl_cover_image.setText("No Art")
                self.lbl_cover_image.setPixmap(QPixmap())
        except: self.lbl_cover_image.setText("No Art")

    def select_cover(self):
        start_dir = self.settings.value("last_folder", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, "Select Image", start_dir, "Images (*.jpg *.png)")
        if path:
            self.cover_image_path = path
            pixmap = QPixmap(path)
            self.lbl_cover_image.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def clear_fields(self):
        for le in self.meta_fields.values(): le.clear(); le.setPlaceholderText("")
        self.lbl_cover_image.setText("No Art"); self.lbl_cover_image.setPixmap(QPixmap())
        
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