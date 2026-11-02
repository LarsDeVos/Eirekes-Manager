# main.py
import sys
from PyQt6.QtWidgets import QApplication
from eirekes_manager.ui.main_window import MusicTaggerApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MusicTaggerApp()
    window.show()
    sys.exit(app.exec())
