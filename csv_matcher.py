import csv
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QListWidget, QAbstractItemView, QGroupBox, 
                             QSplitter, QWidget, QListWidgetItem, QApplication,
                             QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from styles import DARK_THEME

class CsvMatcherDialog(QDialog):
    """
    Dialog to Match Local Files against a CSV/Excel export.
    """
    # Signal: (List of file paths, List of track data, Album Info, Append_Flag)
    matches_confirmed = pyqtSignal(list, list, object, bool)

    def __init__(self, current_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CSV Data Matcher")
        self.resize(1100, 750)
        
        self.local_files = current_files 
        self.init_ui()
        self.setStyleSheet(DARK_THEME)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- 1. Load Section ---
        top_group = QGroupBox("1. Load Data")
        top_layout = QHBoxLayout()
        self.lbl_status = QLabel("No CSV loaded")
        btn_load = QPushButton("📂 Select CSV File")
        btn_load.clicked.connect(self.load_csv)
        
        top_layout.addWidget(btn_load)
        top_layout.addWidget(self.lbl_status)
        top_layout.addStretch()
        top_group.setLayout(top_layout)
        
        # --- 2. Match Section ---
        match_group = QGroupBox("2. Align Files")
        match_layout = QVBoxLayout()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT: Local Files
        left_container = QWidget()
        left_box = QVBoxLayout(left_container)
        left_box.addWidget(QLabel("YOUR FILES:"))
        
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        
        for f_path in self.local_files:
            item = QListWidgetItem(os.path.basename(f_path))
            item.setData(Qt.ItemDataRole.UserRole, f_path)
            self.file_list.addItem(item)
        left_box.addWidget(self.file_list)
        
        # Remove Button for Files
        btn_remove_file = QPushButton("🗑️ Remove Selected File")
        btn_remove_file.setStyleSheet("background-color: #d32f2f; color: white;")
        btn_remove_file.clicked.connect(self.remove_selected_file)
        left_box.addWidget(btn_remove_file)
        
        # RIGHT: CSV Data
        right_container = QWidget()
        right_box = QVBoxLayout(right_container)
        right_box.addWidget(QLabel("CSV ROWS:"))
        
        self.csv_table = QTableWidget()
        self.csv_table.setColumnCount(3)
        self.csv_table.setHorizontalHeaderLabels(["Track", "Title", "Artist"])
        
        header = self.csv_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        self.csv_table.verticalHeader().setVisible(False)
        self.csv_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.csv_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.csv_table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.csv_table.setDragEnabled(True)
        self.csv_table.setDropIndicatorShown(True)
        
        right_box.addWidget(self.csv_table)
        
        # Delete Button for CSV Rows
        btn_delete_row = QPushButton("🗑️ Remove Selected CSV Row")
        btn_delete_row.clicked.connect(self.delete_selected_rows)
        right_box.addWidget(btn_delete_row)
        
        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        match_layout.addWidget(splitter)
        match_group.setLayout(match_layout)
        
        # --- 3. Action Buttons ---
        btn_box = QHBoxLayout()
        
        self.btn_link = QPushButton("🔗 Link Selected Pair")
        self.btn_link.setStyleSheet("background-color: #007bff; font-weight: bold; padding: 10px;")
        self.btn_link.setEnabled(False)
        self.btn_link.clicked.connect(self.link_selected_pair)
        
        self.btn_apply = QPushButton("✅ Apply All Matches")
        self.btn_apply.setStyleSheet("background-color: #28a745; font-weight: bold; padding: 10px;")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.confirm_all_matches)
        
        btn_cancel = QPushButton("Close")
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addWidget(btn_cancel)
        btn_box.addStretch()
        btn_box.addWidget(self.btn_link)
        btn_box.addWidget(self.btn_apply)
        
        # --- LAYOUT SETUP (FIXED RESIZING) ---
        layout.addWidget(top_group)       # Stretch 0
        layout.addWidget(match_group, 1)  # Stretch 1 (Takes all space)
        layout.addLayout(btn_box)         # Stretch 0
        
        self.file_list.verticalScrollBar().valueChanged.connect(self.csv_table.verticalScrollBar().setValue)
        self.csv_table.verticalScrollBar().valueChanged.connect(self.file_list.verticalScrollBar().setValue)

    def load_csv(self):
        f_name, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv);;Text Files (*.txt)")
        if not f_name: return
        
        self.lbl_status.setText(os.path.basename(f_name))
        self.csv_table.setRowCount(0)
        
        try:
            with open(f_name, mode='r', encoding='utf-8-sig') as f:
                dialect = csv.Sniffer().sniff(f.read(1024))
                f.seek(0)
                reader = csv.reader(f, dialect)
                rows = list(reader)
                
                header_idx = -1
                col_map = {"track": -1, "artist": -1, "title": -1}
                
                for i, row in enumerate(rows):
                    row_lower = [c.lower().strip() for c in row]
                    if "stoetnummer" in row_lower and "akv" in row_lower:
                        header_idx = i
                        try:
                            col_map["track"] = row_lower.index("stoetnummer")
                            col_map["artist"] = row_lower.index("akv")
                            col_map["title"] = row_lower.index("thema")
                        except ValueError:
                            pass
                        break
                
                if header_idx == -1:
                    header_idx = 0
                    if len(rows[0]) >= 3:
                        col_map = {"track": 0, "artist": 1, "title": 4} 
                    else:
                        QMessageBox.warning(self, "Warning", "Could not identify columns. Using default guess.")
                        col_map = {"track": 0, "artist": 1, "title": 2}

                data_rows = rows[header_idx+1:]
                self.csv_table.setRowCount(len(data_rows))
                
                for i, row in enumerate(data_rows):
                    def get_col(idx):
                        return row[idx] if idx >= 0 and idx < len(row) else ""

                    track_val = get_col(col_map["track"])
                    artist_val = get_col(col_map["artist"])
                    title_val = get_col(col_map["title"])
                    
                    self.csv_table.setItem(i, 0, QTableWidgetItem(str(track_val)))
                    self.csv_table.setItem(i, 1, QTableWidgetItem(str(title_val)))
                    self.csv_table.setItem(i, 2, QTableWidgetItem(str(artist_val)))
            
            self.btn_apply.setEnabled(True)
            self.btn_link.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not parse CSV: {e}")

    def remove_selected_file(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def delete_selected_rows(self):
        rows = sorted(set(index.row() for index in self.csv_table.selectedIndexes()), reverse=True)
        for row in rows:
            self.csv_table.removeRow(row)

    def get_row_data(self, row_idx):
        t_track = self.csv_table.item(row_idx, 0).text() if self.csv_table.item(row_idx, 0) else ""
        t_title = self.csv_table.item(row_idx, 1).text() if self.csv_table.item(row_idx, 1) else ""
        t_artist = self.csv_table.item(row_idx, 2).text() if self.csv_table.item(row_idx, 2) else ""
        return [t_track, t_title, t_artist]

    def link_selected_pair(self):
        files = self.file_list.selectedItems()
        rows = self.csv_table.selectedIndexes()
        
        if not files or not rows:
            QMessageBox.warning(self, "Selection", "Please select 1 File (Left) and 1 Row (Right).")
            return
            
        file_path = files[0].data(Qt.ItemDataRole.UserRole)
        row_idx = rows[0].row()
        track_data = self.get_row_data(row_idx)
        
        self.matches_confirmed.emit([file_path], [track_data], None, True)
        
        self.file_list.takeItem(self.file_list.row(files[0]))
        self.csv_table.removeRow(row_idx)

    def confirm_all_matches(self):
        file_paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            file_paths.append(item.data(Qt.ItemDataRole.UserRole))
            
        final_data = []
        rows = self.csv_table.rowCount()
        for i in range(rows):
            final_data.append(self.get_row_data(i))
            
        self.matches_confirmed.emit(file_paths, final_data, None, False)
        self.accept()