import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QListWidget, QAbstractItemView, QGroupBox, 
                             QSplitter, QWidget, QListWidgetItem, QApplication,
                             QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal
from scraper import AlbumScraper
from styles import DARK_THEME
from app_translations import tr

class WebMatcherDialog(QDialog):
    # Signal: (List of file paths, List of track data, Album Info, OptionsDict)
    matches_confirmed = pyqtSignal(list, list, list, dict)

    def __init__(self, current_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("matcher_title"))
        self.resize(1100, 800)
        self.scraper = AlbumScraper()
        
        self.local_files = current_files 
        self.scraped_album = []
        
        self.init_ui()
        self.setStyleSheet(DARK_THEME)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- 1. Fetch Section ---
        top_group = QGroupBox(tr("fetch_group"))
        top_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(tr("url_placeholder"))
        btn_fetch = QPushButton(tr("fetch_btn"))
        btn_fetch.clicked.connect(self.run_fetch)
        top_layout.addWidget(QLabel("URL:"))
        top_layout.addWidget(self.url_input)
        top_layout.addWidget(btn_fetch)
        top_group.setLayout(top_layout)

        # --- Options Section ---
        opt_group = QGroupBox(tr("options_group"))
        opt_layout = QHBoxLayout()
        
        self.chk_title = QCheckBox(tr("chk_title"))
        self.chk_title.setChecked(True)
        self.chk_artist = QCheckBox(tr("chk_artist"))
        self.chk_artist.setChecked(True)
        self.chk_track = QCheckBox(tr("chk_track"))
        self.chk_track.setChecked(True)
        self.chk_rename = QCheckBox(tr("chk_rename"))
        self.chk_rename.setChecked(True)
        self.chk_lyrics = QCheckBox(tr("chk_lyrics"))
        self.chk_lyrics.setChecked(True)
        
        opt_layout.addWidget(self.chk_title)
        opt_layout.addWidget(self.chk_artist)
        opt_layout.addWidget(self.chk_track)
        opt_layout.addWidget(self.chk_rename)
        opt_layout.addWidget(self.chk_lyrics)
        opt_group.setLayout(opt_layout)
        
        layout.addWidget(top_group)
        layout.addWidget(opt_group)

        # --- 2. Match Section ---
        match_group = QGroupBox(tr("align_group"))
        match_layout = QVBoxLayout()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_container = QWidget()
        left_box = QVBoxLayout(left_container)
        left_box.addWidget(QLabel(tr("your_files")))
        self.file_list = QListWidget()
        self.file_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for f_path in self.local_files:
            item = QListWidgetItem(os.path.basename(f_path))
            item.setData(Qt.ItemDataRole.UserRole, f_path)
            self.file_list.addItem(item)
        left_box.addWidget(self.file_list)
        
        right_container = QWidget()
        right_box = QVBoxLayout(right_container)
        self.lbl_web_info = QLabel(tr("web_tracks"))
        right_box.addWidget(self.lbl_web_info)
        
        # TABLE COLUMNS: [#, Title, Artist, Lyrics (Hidden), Comment/Original]
        self.web_table = QTableWidget()
        self.web_table.setColumnCount(5) 
        self.web_table.setHorizontalHeaderLabels(["#", tr("lbl_title"), tr("lbl_artist"), "Lyrics", tr("lbl_comment")])
        self.web_table.setColumnHidden(3, True) # Hide Lyrics
        
        header = self.web_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch) # Comment Column
        
        self.web_table.verticalHeader().setVisible(False)
        self.web_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        right_box.addWidget(self.web_table)
        
        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        match_layout.addWidget(splitter)
        match_group.setLayout(match_layout)
        
        self.file_list.verticalScrollBar().valueChanged.connect(self.web_table.verticalScrollBar().setValue)
        self.web_table.verticalScrollBar().valueChanged.connect(self.file_list.verticalScrollBar().setValue)

        # --- 3. Buttons ---
        btn_box = QHBoxLayout()
        self.btn_apply = QPushButton(tr("apply_btn"))
        self.btn_apply.setStyleSheet("background-color: #28a745; font-weight: bold; padding: 10px;")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.confirm_matches)
        
        btn_cancel = QPushButton(tr("cancel_btn"))
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(self.btn_apply)
        
        layout.addWidget(match_group, 1) # Stretch = 1
        layout.addLayout(btn_box)

    def run_fetch(self):
        url = self.url_input.text().strip()
        if not url: return

        self.web_table.setRowCount(0)
        self.btn_apply.setText(tr("fetching_wait"))
        self.btn_apply.setEnabled(False)
        QApplication.processEvents()
        
        # Scraper returns: [Num, Title, Artist, Lyrics, Comment]
        array_1d, array_2d = self.scraper.fetch_data(url)
        
        self.btn_apply.setText(tr("apply_btn"))
        if not array_1d: return
        
        self.scraped_album = array_1d
        info = f"{array_1d[0]} ({array_1d[2]})" if len(array_1d) > 2 else tr("unknown_album")
        self.lbl_web_info.setText(f"{tr('web_tracks')} {info}")
        
        self.web_table.setRowCount(len(array_2d))
        for i, track in enumerate(array_2d):
            print("TRACK DATA:", track)
            # 0: Num
            item_num = QTableWidgetItem(str(track[0]))
            item_num.setFlags(item_num.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.web_table.setItem(i, 0, item_num)
            
            # 1: Title
            self.web_table.setItem(i, 1, QTableWidgetItem(track[1]))
            
            # 2: Artist
            self.web_table.setItem(i, 2, QTableWidgetItem(track[2]))
            
            # 3: Lyrics
            lyrics = track[3] if len(track) > 3 else ""
            self.web_table.setItem(i, 3, QTableWidgetItem(lyrics))
            
            # 4: Comment (Original)
            comment = track[4] if len(track) > 4 else ""
            self.web_table.setItem(i, 4, QTableWidgetItem(comment))
            
        self.btn_apply.setEnabled(True)

    def confirm_matches(self):
        reordered_files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            reordered_files.append(item.data(Qt.ItemDataRole.UserRole))
            
        final_track_data = []
        rows = self.web_table.rowCount()
        for i in range(rows):
            t_num = self.web_table.item(i, 0).text()
            t_title = self.web_table.item(i, 1).text()
            t_artist = self.web_table.item(i, 2).text()
            t_lyrics = self.web_table.item(i, 3).text()
            t_comment = self.web_table.item(i, 4).text()
            
            final_track_data.append([t_num, t_title, t_artist, t_lyrics, t_comment])
            
        options = {
            'title': self.chk_title.isChecked(),
            'artist': self.chk_artist.isChecked(),
            'track': self.chk_track.isChecked(),
            'rename': self.chk_rename.isChecked(),
            'lyrics': self.chk_lyrics.isChecked()
        }
            
        self.matches_confirmed.emit(reordered_files, final_track_data, self.scraped_album, options)
        self.accept()