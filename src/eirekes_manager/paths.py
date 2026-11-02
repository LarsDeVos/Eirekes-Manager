# src/eirekes_manager/paths.py
"""Locations of bundled files and the log folder."""

import logging
import os
import sys

# src/ (from source) - artists.json lives there, the online update URL points at it
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_DIR = os.path.join(os.path.expanduser("~"), "EirekesManagerLogs")


def resource_path(name):
    """Path to a bundled file (works from source and from the PyInstaller app)."""
    base = getattr(sys, "_MEIPASS", SRC_DIR)
    return os.path.join(base, name)


def setup_logging(log_dir=LOG_DIR):
    """Log to <log_dir>/application.log. Returns the log folder."""
    os.makedirs(log_dir, exist_ok=True)
    # Reset handlers to avoid duplicate logs if app restarts
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        filename=os.path.join(log_dir, "application.log"),
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filemode='a'
    )
    return log_dir
