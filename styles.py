# styles.py

DARK_THEME = """
QMainWindow { background-color: #2b2b2b; color: #ffffff; }
QDialog { background-color: #2b2b2b; color: #ffffff; }
QWidget { color: #f0f0f0; font-family: 'Segoe UI', sans-serif; font-size: 14px; }

QGroupBox { 
    border: 1px solid #444; 
    border-radius: 6px; 
    margin-top: 20px; 
    font-weight: bold; 
    color: #4da6ff;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }

QLineEdit { 
    background-color: #3b3b3b; 
    border: 1px solid #555; 
    border-radius: 4px; 
    padding: 5px; 
    color: white; 
}
QLineEdit:focus { border: 1px solid #4da6ff; }

QPushButton { 
    background-color: #3e3e42; 
    border: 1px solid #555; 
    border-radius: 5px; 
    padding: 6px 12px; 
    color: white; 
}
QPushButton:hover { background-color: #4da6ff; color: white; border: 1px solid #4da6ff; }
QPushButton:pressed { background-color: #0056b3; }
QPushButton:disabled { background-color: #2a2a2a; color: #555; border: 1px solid #333; }

QListWidget { 
    background-color: #1e1e1e; 
    border: 1px solid #444; 
    border-radius: 4px; 
    outline: none;
}
QListWidget::item { 
    height: 28px; 
    padding-left: 5px; 
    border-bottom: 1px solid #2a2a2a; 
}
QListWidget::item:selected { 
    background-color: #007bff; 
    color: white; 
}

/* --- TABLE WIDGET STYLING (Fixes White Text Issue) --- */
QTableWidget {
    background-color: #1e1e1e;
    gridline-color: #444;
    color: #f0f0f0;
    border: 1px solid #444;
}
QTableWidget::item {
    border-bottom: 1px solid #333;
    padding: 5px;
}
QTableWidget::item:selected {
    background-color: #007bff;
    color: white;
}
QHeaderView::section {
    background-color: #3e3e42;
    color: white;
    border: 1px solid #444;
    padding: 4px;
}
QTableCornerButton::section {
    background-color: #3e3e42;
    border: 1px solid #444;
}

QLabel { color: #cccccc; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #2b2b2b; width: 10px; }
QScrollBar::handle:vertical { background: #555; border-radius: 5px; }
"""