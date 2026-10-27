# src/extra_tags.py
"""
Tags that music_tag does not support: RELEASETYPE (Album / Single / EP ...).

Plex (and MusicBrainz Picard, foobar, beets...) read the release type from:
  MP3 / WAV : TXXX:RELEASETYPE           (+ TXXX:MusicBrainz Album Type)
  FLAC/OGG  : RELEASETYPE                (+ MUSICBRAINZ_ALBUMTYPE)
  M4A / MP4 : ----:com.apple.iTunes:RELEASETYPE (+ MusicBrainz Album Type)
Values are stored lowercase, e.g. "single".
After saving, refresh the album's metadata in Plex so it moves to "Singles & EPs".
"""

import os

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TXXX, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4FreeForm
from mutagen.wave import WAVE

# (value stored in file, translation key for the UI)
RELEASE_TYPES = [
    ("album", "rt_album"),
    ("single", "rt_single"),
    ("ep", "rt_ep"),
    ("compilation", "rt_compilation"),
    ("live", "rt_live"),
    ("remix", "rt_remix"),
    ("soundtrack", "rt_soundtrack"),
    ("demo", "rt_demo"),
]

_ID3_DESCS = ("RELEASETYPE", "MusicBrainz Album Type")
_VORBIS_KEYS = ("releasetype", "musicbrainz_albumtype")
_MP4_KEYS = ("----:com.apple.iTunes:RELEASETYPE",
             "----:com.apple.iTunes:MusicBrainz Album Type")


def _ext(path):
    return os.path.splitext(path)[1].lower()


def read_release_type(path):
    """Return the release type in lowercase ('' when not set)."""
    try:
        ext = _ext(path)
        if ext in (".mp3", ".wav"):
            tags = WAVE(path).tags if ext == ".wav" else ID3(path)
            if tags:
                for desc in _ID3_DESCS:
                    frame = tags.get(f"TXXX:{desc}")
                    if frame and frame.text:
                        return str(frame.text[0]).strip().lower()
        elif ext in (".m4a", ".mp4"):
            tags = MP4(path).tags or {}
            for key in _MP4_KEYS:
                if key in tags and tags[key]:
                    return bytes(tags[key][0]).decode("utf-8", "ignore").strip().lower()
        else:
            f = MutagenFile(path)
            if f is not None and f.tags is not None:
                for key in _VORBIS_KEYS:
                    vals = f.tags.get(key)
                    if vals:
                        return str(vals[0]).strip().lower()
    except (ID3NoHeaderError, Exception):
        pass
    return ""


def write_release_type(path, value):
    """Write (or remove when value is '') the release type."""
    value = (value or "").strip().lower()
    ext = _ext(path)

    if ext in (".mp3", ".wav"):
        if ext == ".wav":
            audio = WAVE(path)
            if audio.tags is None:
                audio.add_tags()
            tags = audio.tags
        else:
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
        for desc in _ID3_DESCS:
            tags.delall(f"TXXX:{desc}")
            if value:
                tags.add(TXXX(encoding=3, desc=desc, text=[value]))
        if ext == ".wav":
            audio.save()
        else:
            tags.save(path)

    elif ext in (".m4a", ".mp4"):
        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        for key in _MP4_KEYS:
            if key in audio.tags:
                del audio.tags[key]
            if value:
                audio.tags[key] = [MP4FreeForm(value.encode("utf-8"))]
        audio.save()

    else:  # FLAC / OGG / OPUS (Vorbis comments)
        audio = MutagenFile(path)
        if audio is None:
            raise ValueError("Unsupported file type for release type")
        if audio.tags is None:
            audio.add_tags()
        for key in _VORBIS_KEYS:
            if key in audio.tags:
                del audio.tags[key]
            if value:
                audio.tags[key] = [value]
        audio.save()
