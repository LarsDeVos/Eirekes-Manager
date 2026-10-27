# src/tag_values.py
"""
Validation / cleaning of tag values before they are written, and safe
reading of tags that are broken in the file (e.g. a date "2026-08-2").

clean_value(tag, value) -> (clean_value, error)
    error is None when the value is OK, otherwise a short reason that is
    shown to the user (translation key + the value).
"""

import re

from mutagen import File as MutagenFile

YEAR_RE = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")
NUMBER_KEYS = ("tracknumber", "totaltracks", "discnumber", "totaldiscs")


def clean_value(tag, value):
    """Return (cleaned value, error-or-None) for one tag."""
    value = "" if value is None else str(value).strip()
    if value == "":
        return "", None

    if tag == "year":
        # accepts 2026, 2026-08-25, 25/08/2026, "2026-08-2" (half typed date)...
        m = YEAR_RE.search(value)
        if m:
            return m.group(1), None
        return value, "err_year"

    if tag in NUMBER_KEYS:
        # accepts 3, 03, "3/12" (track 3 of 12)
        m = re.match(r"^\s*0*(\d{1,3})\s*(?:/\s*\d+)?\s*$", value)
        if m:
            return m.group(1), None
        return value, "err_number"

    if tag == "compilation":
        if value in ("0", "1"):
            return value, None
        return value, "err_compilation"

    return value, None


def safe_get(f, tag, path=None):
    """Read a tag with music_tag; never raises.

    When music_tag cannot parse the value (broken year/number in the file),
    fall back to the raw text from mutagen so the user can see and fix it.
    Returns (text, broken) where broken=True means the file value is invalid.
    """
    try:
        val = f[tag]
        return ("" if val is None else str(val)), False
    except Exception:
        pass
    raw = ""
    if path:
        raw_keys = {"year": ("date", "year", "originaldate"),
                    "tracknumber": ("tracknumber",), "discnumber": ("discnumber",),
                    "totaltracks": ("tracktotal", "totaltracks"),
                    "totaldiscs": ("disctotal", "totaldiscs")}.get(tag, (tag,))
        try:
            easy = MutagenFile(path, easy=True)
            if easy is not None and easy.tags is not None:
                for k in raw_keys:
                    if k in easy.tags and easy.tags[k]:
                        raw = str(easy.tags[k][0])
                        break
        except Exception:
            pass
    return raw, True


def force_remove(path, tag):
    """Remove a broken tag directly with mutagen (music_tag can't read it)."""
    keys = {"year": ("date", "originaldate", "year"),
            "tracknumber": ("tracknumber",), "discnumber": ("discnumber",),
            "totaltracks": ("tracktotal", "totaltracks"),
            "totaldiscs": ("disctotal", "totaldiscs")}.get(tag, (tag,))
    easy = MutagenFile(path, easy=True)
    if easy is None or easy.tags is None:
        return
    changed = False
    for k in keys:
        try:
            if k in easy.tags:
                del easy.tags[k]
                changed = True
        except (KeyError, ValueError):
            pass
    if changed:
        easy.save()
