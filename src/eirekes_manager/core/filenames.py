# src/eirekes_manager/core/filenames.py
"""File names for renamed tracks: "03 - Artist - Title.mp3"."""

import os
import re

AUDIO_EXTENSIONS = ('.mp3', '.m4a', '.flac', '.wav')


def sanitize_filename(name):
    """Remove characters that are not allowed in file names."""
    return re.sub(r'[<>:"/\\|?*]', '', name or "").strip()


def track_filename(tracknumber, artist, title, ext):
    """'03 - Artist - Title.mp3' (track "00" / "Unknown" when missing)."""
    try:
        t_str = f"{int(tracknumber):02d}"
    except (ValueError, TypeError):
        t_str = "00"
    clean_title = sanitize_filename(title) or "Unknown"
    clean_artist = sanitize_filename(artist) or "Unknown"
    return f"{t_str} - {clean_artist} - {clean_title}{ext}"


def list_audio_files(folder):
    """Sorted audio file names in `folder` ([] when it can't be read)."""
    try:
        return sorted(f for f in os.listdir(folder) if f.lower().endswith(AUDIO_EXTENSIONS))
    except OSError:
        return []
