# src/eirekes_manager/core/tag_writer.py
"""
Write pending changes to the files: tags, cover art, rename, lyrics.

Every tag is written on its own, so one bad value never blocks the other
fields of the file. What could not be saved is returned in `failed`, so the
UI can keep it pending and nothing typed is lost.
"""

import logging
import os
import shutil
from dataclasses import dataclass, field

import music_tag
from mutagen.mp4 import MP4, MP4Cover

from ..i18n import tr
from .filenames import track_filename
from .metadata import NUMERIC_KEYS, read_compilation
from .release_type import read_release_type, write_release_type
from .tag_values import clean_value, safe_get, force_remove


@dataclass
class SaveResult:
    path: str                                    # file path after a possible rename
    ok: bool = True
    errors: list = field(default_factory=list)   # human readable messages
    failed: dict = field(default_factory=dict)   # path -> changes that could NOT be saved

    def fail(self, path, changes_left, message):
        logging.error(message)
        self.ok = False
        self.errors.append(message)
        self.failed.setdefault(path, {}).update(changes_left)


@dataclass
class BatchResult:
    count: int = 0                               # files saved without problems
    paths: list = field(default_factory=list)    # files that were processed
    errors: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def save_pending(pending, to_jpeg=None):
    """Save {path: changes} for all files. See save_file_changes()."""
    batch = BatchResult(paths=list(pending.keys()))
    logging.info(f"Starting Batch Save ({len(pending)} files)...")
    for file_path in batch.paths:
        result = save_file_changes(file_path, pending[file_path], to_jpeg)
        batch.errors.extend(result.errors)
        for path, left in result.failed.items():
            batch.failed.setdefault(path, {}).update(left)
        if result.ok:
            batch.count += 1
    return batch


def save_file_changes(file_path, changes, to_jpeg=None):
    """Save one file's changes. Returns a SaveResult.

    to_jpeg(image_path) -> bytes converts the chosen cover to JPEG (the UI
    uses Qt for that); without it the image file is embedded as it is.
    """
    to_jpeg = to_jpeg or _read_bytes
    name = os.path.basename(file_path)
    result = SaveResult(file_path)

    if not os.path.exists(file_path):
        result.fail(file_path, {}, tr("err_missing").format(name))
        return result
    if not os.access(file_path, os.W_OK):
        result.fail(file_path, changes, tr("err_readonly").format(name))
        return result

    # --- 1. TAGS (metadata & artwork) ---
    try:
        _write_tags(file_path, changes, result)
        if 'releasetype' in changes:
            if read_release_type(file_path) != changes['releasetype']:
                write_release_type(file_path, changes['releasetype'])
        if changes.get('_artwork_path'):
            _write_artwork(file_path, changes['_artwork_path'], to_jpeg)
        logging.info(tr("saved_log").format(name))
    except Exception as e:
        # whole file failed (corrupt file, artwork problem...): keep everything pending
        result.fail(file_path, changes, tr("err_file").format(file=name, error=e))
        return result

    # --- 2. RENAME ---
    if changes.get('_rename'):
        try:
            result.path = _rename(file_path, changes)
        except Exception as e:
            result.fail(file_path, {}, tr("err_rename").format(file=name, error=e))

    # --- 3. LYRICS ---
    if changes.get('_lyrics'):
        try:
            lrc_path = os.path.splitext(result.path)[0] + ".txt"
            with open(lrc_path, 'w', encoding='utf-8') as lrc_file:
                lrc_file.write(changes['_lyrics'])
            logging.info(tr("lyrics_log").format(lrc_path))
        except Exception as e:
            result.fail(result.path, {}, tr("err_lyrics").format(file=name, error=e))

    return result


def _write_tags(path, changes, result):
    """Text tags with music_tag, one tag at a time."""
    name = os.path.basename(path)
    f = music_tag.load_file(path)
    file_dirty = False

    for tag, new_val in changes.items():
        if tag.startswith('_') or tag == 'releasetype':
            continue
        label = tr(f"lbl_{tag}")
        new_val, problem = clean_value(tag, new_val)
        if problem:
            result.fail(path, {tag: changes[tag]},
                        tr(problem).format(file=name, field=label, value=new_val))
            continue
        try:
            current_val, broken = safe_get(f, tag, path)
            if broken:
                # value in the file can't be read (e.g. "2026-08-2"): remove it first
                logging.warning(f"{name}: invalid {tag} in file ('{current_val}') - replacing it")
                if file_dirty:
                    f.save()
                    file_dirty = False
                force_remove(path, tag)
                f = music_tag.load_file(path)
                current_val = ""

            if tag in NUMERIC_KEYS and new_val == "":
                if current_val != "":
                    del f[tag]
                    f.save()
                    file_dirty = False
                    if tag != 'comment':
                        # music_tag leaves some behind (e.g. the M4A track number)
                        force_remove(path, tag)
                        f = music_tag.load_file(path)
                continue

            if tag == 'compilation':
                if read_compilation(f) != new_val:
                    f[tag] = new_val == "1"
                    file_dirty = True
                continue

            if current_val != new_val:
                if tag in NUMERIC_KEYS and tag != 'comment' and current_val != "":
                    # clear the old value first (also when it is malformed), then write
                    if file_dirty:
                        f.save()
                        file_dirty = False
                    force_remove(path, tag)
                    f = music_tag.load_file(path)
                f[tag] = new_val
                file_dirty = True
        except Exception as e:
            result.fail(path, {tag: changes[tag]},
                        tr("err_tag").format(file=name, field=label, value=new_val, error=e))

    if file_dirty:
        f.save()


def _write_artwork(path, art_path, to_jpeg):
    if not os.path.exists(art_path):
        return
    img_data = to_jpeg(art_path)
    if not img_data:
        return
    if os.path.splitext(path)[1].lower() in ('.m4a', '.mp4'):
        # mutagen directly for M4A (music_tag gives an 'atom' error)
        m4a_file = MP4(path)
        m4a_file['covr'] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
        m4a_file.save()
    else:
        f_art = music_tag.load_file(path)
        try:
            del f_art['artwork']
        except Exception:
            pass
        f_art['artwork'] = img_data
        f_art.save()


def _rename(path, changes):
    """Rename to '03 - Artist - Title.ext' (new values first, else the file's)."""
    f = music_tag.load_file(path)
    new_filename = track_filename(changes.get('tracknumber', str(f['tracknumber'])),
                                  changes.get('artist', str(f['artist'])),
                                  changes.get('title', str(f['title'])),
                                  os.path.splitext(path)[1])
    new_full_path = os.path.join(os.path.dirname(path), new_filename)
    if path != new_full_path:
        shutil.move(path, new_full_path)
        logging.info(tr("renamed_log").format(new_filename))
    return new_full_path
