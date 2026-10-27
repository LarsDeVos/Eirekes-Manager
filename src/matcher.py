import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QListWidget, QAbstractItemView, QGroupBox,
                             QSplitter, QWidget, QListWidgetItem, QApplication,
                             QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QIcon, QPixmap, QPainter
from scraper import AlbumScraper
from artist_catalog import TAG_AKV, split_artists, normalize_key
from artist_field import ArtistDelegate, ArtistPickerDialog

# Column indexes in the web table
COL_NUM, COL_TITLE, COL_ARTIST, COL_LYRICS, COL_COMMENT, COL_WEB_ARTIST = range(6)

# Colours for the artist recommendation (dot + text colour; the dark theme
# stylesheet ignores cell backgrounds)
ARTIST_COLORS = {
    "ok": None,                 # exactly as in the list and as on the website
    "corrected": "#6fdc8c",     # known artist, spelling/notation corrected
    "fuzzy": "#F5B027",         # typo -> closest artist from the list (check!)
    "unknown": "#ff6b6b",       # not in the list
}


def _dot_icon(color):
    pm = QPixmap(12, 12)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, 10, 10)
    p.end()
    return QIcon(pm)
from styles import DARK_THEME
from app_translations import tr

class WebMatcherDialog(QDialog):
    # Signal: (List of file paths, List of track data, Album Info, OptionsDict)
    matches_confirmed = pyqtSignal(list, list, list, dict)

    def __init__(self, current_files, parent=None, catalog=None):
        super().__init__(parent)
        self.catalog = catalog if catalog is not None else getattr(parent, "catalog", None)
        self.web_artists = []      # original artist strings from the website
        self._filling = False
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

        # Artist recommendations from the artist list
        self.chk_suggest = QCheckBox(tr("chk_suggest_artist"))
        self.chk_suggest.setChecked(self.catalog is not None)
        self.chk_suggest.setEnabled(self.catalog is not None)
        self.chk_suggest.toggled.connect(self.refresh_artist_suggestions)
        opt_layout.addWidget(self.chk_suggest)
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

        # TABLE COLUMNS: [#, Title, Artist, Lyrics (Hidden), Comment/Original, Web Artist]
        self.web_table = QTableWidget()
        self.web_table.setColumnCount(6)
        self.web_table.setHorizontalHeaderLabels(["#", tr("lbl_title"), tr("lbl_artist"), "Lyrics",
                                                  tr("lbl_comment"), tr("web_artist_col")])
        self.web_table.setColumnHidden(COL_LYRICS, True) # Hide Lyrics

        header = self.web_table.horizontalHeader()
        header.setSectionResizeMode(COL_NUM, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_ARTIST, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_COMMENT, QHeaderView.ResizeMode.Stretch) # Comment Column
        header.setSectionResizeMode(COL_WEB_ARTIST, QHeaderView.ResizeMode.Stretch)
        # Show "Web artist" right next to the (recommended) artist
        header.moveSection(header.visualIndex(COL_WEB_ARTIST), header.visualIndex(COL_ARTIST) + 1)

        if self.catalog is not None:
            self.web_table.setItemDelegateForColumn(COL_ARTIST, ArtistDelegate(self.catalog, self.web_table))
            self.web_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.web_table.customContextMenuRequested.connect(self.artist_context_menu)
            self.web_table.itemChanged.connect(self.on_table_item_changed)

        self.web_table.verticalHeader().setVisible(False)
        self.web_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        right_box.addWidget(self.web_table)
        self.lbl_artist_summary = QLabel()
        self.lbl_artist_summary.setWordWrap(True)
        self.lbl_artist_summary.setStyleSheet("color: #aaa; font-size: 12px;")
        right_box.addWidget(self.lbl_artist_summary)

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

        self._filling = True
        self.web_artists = []
        self.web_table.setRowCount(len(array_2d))
        for i, track in enumerate(array_2d):
            # 0: Num
            item_num = QTableWidgetItem(str(track[0]))
            item_num.setFlags(item_num.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.web_table.setItem(i, 0, item_num)

            # 1: Title
            self.web_table.setItem(i, 1, QTableWidgetItem(track[1]))

            # 2: Artist (recommendation filled in by refresh_artist_suggestions)
            self.web_table.setItem(i, COL_ARTIST, QTableWidgetItem(track[2]))
            self.web_artists.append(track[2])

            # 5: Artist exactly as on the website (read-only, for reference)
            item_web = QTableWidgetItem(track[2])
            item_web.setFlags(item_web.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_web.setForeground(QBrush(QColor("#888")))
            self.web_table.setItem(i, COL_WEB_ARTIST, item_web)

            # 3: Lyrics
            lyrics = track[3] if len(track) > 3 else ""
            self.web_table.setItem(i, 3, QTableWidgetItem(lyrics))

            # 4: Comment (Original)
            comment = track[4] if len(track) > 4 else ""
            self.web_table.setItem(i, 4, QTableWidgetItem(comment))

        self._filling = False
        self.refresh_artist_suggestions()
        self.btn_apply.setEnabled(True)

    # =========================================================
    # ARTIST RECOMMENDATIONS
    # =========================================================
    def refresh_artist_suggestions(self, *_):
        """Fill the Artist column with the recommendation (or the web value)."""
        if self.catalog is None:
            return
        self._filling = True
        for row, web_value in enumerate(self.web_artists):
            value = self.catalog.suggest(web_value)[0] if self.chk_suggest.isChecked() else web_value
            self.web_table.item(row, COL_ARTIST).setText(value or web_value)
            self.color_artist_row(row)
        self._filling = False
        self.update_artist_summary()

    def artist_status(self, value):
        """('ok'|'corrected'|'fuzzy'|'unknown', tooltip) for a cell value."""
        suggestion, parts = self.catalog.suggest(value)
        lines = []
        status = "ok"
        for p in parts:
            if p["status"] == "unknown":
                status = "unknown"
                cands = ", ".join(p["candidates"][:4])
                lines.append(tr("artist_tip_unknown").format(p["input"]) +
                             (f"  {tr('artist_maybe').format(cands)}" if cands else ""))
            elif p["status"] == "fuzzy":
                if status != "unknown":
                    status = "fuzzy"
                lines.append(tr("artist_tip_fuzzy").format(p["input"], p["output"]))
        if status == "ok" and suggestion != value:
            status = "corrected"
            lines.append(tr("artist_suggestion").format(suggestion))
        return status, "\n".join(lines)

    def color_artist_row(self, row):
        item = self.web_table.item(row, COL_ARTIST)
        if item is None or self.catalog is None:
            return
        web_value = self.web_artists[row] if row < len(self.web_artists) else ""
        status, tip = self.artist_status(item.text())
        if status == "ok" and item.text() != web_value:
            # fully known now, but differs from the website -> show what changed
            auto_value, web_parts = self.catalog.suggest(web_value)
            # a guessed typo stays yellow until you change the cell yourself
            guessed = item.text() == auto_value and any(p["status"] == "fuzzy" for p in web_parts)
            status = "fuzzy" if guessed else "corrected"
            tip = tr("artist_tip_changed").format(web_value)
            for p in web_parts:
                if p["status"] == "fuzzy":
                    tip += "\n" + tr("artist_tip_fuzzy").format(p["input"], p["output"])
        color = ARTIST_COLORS[status]
        item.setForeground(QBrush(QColor(color)) if color else QBrush())
        item.setIcon(_dot_icon(color) if color else QIcon())
        item.setToolTip(tip)
        item.setData(Qt.ItemDataRole.UserRole, status)

    def on_table_item_changed(self, item):
        if self._filling or item.column() != COL_ARTIST:
            return
        self._filling = True
        self.color_artist_row(item.row())
        self._filling = False
        self.update_artist_summary()

    def update_artist_summary(self):
        if self.catalog is None:
            return
        counts = {"ok": 0, "corrected": 0, "fuzzy": 0, "unknown": 0}
        for row in range(self.web_table.rowCount()):
            item = self.web_table.item(row, COL_ARTIST)
            if item is not None:
                counts[item.data(Qt.ItemDataRole.UserRole) or "ok"] += 1
        self.lbl_artist_summary.setText(tr("artist_summary").format(
            counts["ok"], counts["corrected"], counts["fuzzy"], counts["unknown"]))

    def artist_context_menu(self, pos):
        item = self.web_table.itemAt(pos)
        if item is None or item.column() != COL_ARTIST:
            return
        row = item.row()
        value = item.text()
        _, parts = self.catalog.suggest(value)
        menu = QMenu(self)
        actions = {}

        # Alternatives for each artist that is unknown or was guessed
        web_value = self.web_artists[row] if row < len(self.web_artists) else ""
        _, web_parts = self.catalog.suggest(web_value)
        for p in parts + [wp for wp in web_parts if wp["status"] == "fuzzy"]:
            if p["status"] in ("fuzzy", "unknown") and p["candidates"]:
                sub = menu.addMenu(tr("artist_replace").format(p["input"]))
                for cand in p["candidates"]:
                    label = cand + ("  [AKV]" if self.catalog.is_akv(cand) else "")
                    actions[sub.addAction(label)] = ("replace", p["output"], cand)
        if actions:
            menu.addSeparator()
        actions[menu.addAction(tr("artist_pick_tooltip") + "...")] = ("pick",)
        actions[menu.addAction(tr("artist_use_web").format(web_value))] = ("web",)
        unknown = [p["output"] for p in parts if p["status"] == "unknown"]
        if unknown:
            menu.addSeparator()
            names = ", ".join(unknown)
            actions[menu.addAction(tr("artist_add_named").format(names))] = ("add", False)
            actions[menu.addAction(tr("artist_add_named_akv").format(names))] = ("add", True)

        chosen = menu.exec(self.web_table.viewport().mapToGlobal(pos))
        if chosen not in actions:
            return
        act = actions[chosen]
        if act[0] == "replace":
            item.setText(self.replace_artist(value, act[1], act[2]))
        elif act[0] == "pick":
            dlg = ArtistPickerDialog(self.catalog, value, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                item.setText(dlg.result_text())
        elif act[0] == "web":
            item.setText(web_value)
        elif act[0] == "add":
            for name in unknown:
                self.catalog.add_user_artist(name, tags=[TAG_AKV] if act[1] else ())
            self._filling = True
            for r in range(self.web_table.rowCount()):
                self.color_artist_row(r)
            self._filling = False
            self.update_artist_summary()

    def replace_artist(self, value, old, new):
        """Swap one artist inside 'A & B feat. C', keeping the structure."""
        lead, feat = [], []
        l, f = split_artists(value)
        for src, dst in ((l, lead), (f, feat)):
            for part in src:
                canon = self.catalog.canonical(part)
                dst.append(new if normalize_key(canon) == normalize_key(old) or
                           normalize_key(part) == normalize_key(old) else canon)
        return self.catalog._join(lead, feat)

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