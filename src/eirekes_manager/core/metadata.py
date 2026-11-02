# src/eirekes_manager/core/metadata.py
"""Which tags the editor shows, and reading them from a file."""

import logging
import os

import music_tag

from .release_type import RELEASE_TYPES, read_release_type
from .tag_values import safe_get

# Fields read/written with music_tag (label -> tag key), in form order
TAG_MAP = {
    "Title": "title", "Artist": "artist", "Album": "album",
    "Album Artist": "albumartist", "Year": "year",
    "Track": "tracknumber", "Total Tracks": "totaltracks",
    "Discnumber": "discnumber", "Total Discs": "totaldiscs",
    "Genre": "genre", "Composer": "composer",
    "Compilation": "compilation", "Comment": "comment"
}
# Fields with an artist picker
ARTIST_KEYS = {"artist", "albumartist"}
# Drop-down fields: tag key -> list of (stored value, translation key)
COMBO_OPTIONS = {
    "releasetype": [("", "rt_none")] + RELEASE_TYPES,
    "compilation": [("", "rt_none"), ("1", "yes"), ("0", "no")],
}
# Number fields: empty value removes the tag
NUMERIC_KEYS = ['tracknumber', 'totaltracks', 'year', 'discnumber',
                'totaldiscs', 'comment', 'compilation']


def form_order():
    """Tag keys in the order of the editor form (Release Type after Album Artist)."""
    order = []
    for tag_key in TAG_MAP.values():
        order.append(tag_key)
        if tag_key == "albumartist":
            order.append("releasetype")
    return order


def read_compilation(f):
    """'1' / '0' / '' (not set) from a music_tag file."""
    try:
        raw = f.raw['compilation']
        if raw is None or raw.value is None or str(raw) == "":
            return ""
        return "1" if raw.first else "0"
    except Exception:
        return ""


def read_metadata(path):
    """{tag key: text} as stored in the file (never raises)."""
    data = {}
    try:
        f = music_tag.load_file(path)
    except Exception as e:
        logging.error(f"Cannot read {os.path.basename(path)}: {e}")
        f = None
    if f is not None:
        for tag_key in TAG_MAP.values():
            if tag_key == 'compilation':
                data[tag_key] = read_compilation(f)
                continue
            data[tag_key], _broken = safe_get(f, tag_key, path)
            if tag_key in ('totaltracks', 'totaldiscs') and data[tag_key] == "0":
                data[tag_key] = ""
    data['releasetype'] = read_release_type(path)
    return data


def effective_metadata(path, pending=None):
    """File tags with the pending (not yet saved) changes on top."""
    data = read_metadata(path)
    for key, val in (pending or {}).items():
        if not key.startswith('_'):
            data[key] = val
    return data


def common_values(items):
    """Merge several metadata dicts: a value that differs becomes None."""
    if not items:
        return {}
    common = dict(items[0])
    for other in items[1:]:
        for key in list(common.keys()):
            if common[key] != other.get(key, ""):
                common[key] = None
    return common
