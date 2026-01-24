# main.py
import sys
from PyQt6.QtWidgets import QApplication
from mainwindow import MusicTaggerApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MusicTaggerApp()
    window.show()
    sys.exit(app.exec())