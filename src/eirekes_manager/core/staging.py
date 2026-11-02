# src/eirekes_manager/core/staging.py
"""
Turn matched web/CSV data into pending changes per file.

Pending changes are a dict {tag key: value}; keys starting with "_" are
instructions for the save step, not tags:
  _rename        rename the file to "03 - Artist - Title.ext"
  _lyrics        write the lyrics to a .txt next to the file
  _artwork_path  image to embed as cover art
"""

GENRE = "Carnaval"

# Track data rows: [number, title, artist, lyrics, comment]
ROW_NUM, ROW_TITLE, ROW_ARTIST, ROW_LYRICS, ROW_COMMENT = range(5)

# Options used for a CSV import (the CSV has no lyrics)
CSV_OPTIONS = {'title': True, 'artist': True, 'track': True, 'rename': True, 'lyrics': False}


def build_staged_changes(files, track_data, album_data, options,
                         normalize_artist=None, existing=None):
    """Return {path: changes} for `files` matched row by row to `track_data`.

    album_data  [album, ?, year, ...] from the web scraper (or None)
    options     {'title', 'artist', 'track', 'rename', 'lyrics'} -> bool
    normalize_artist  callable that cleans an artist string (artist catalog)
    existing    pending changes to add to (append mode), left unchanged
    """
    existing = existing or {}
    album_common = {}
    if album_data:
        album_common['album'] = album_data[0]
        album_common['year'] = album_data[2]

    result = {}
    for i, file_path in enumerate(files):
        file_data = dict(existing.get(file_path, {}))
        file_data.update(album_common)
        file_data['genre'] = GENRE

        track_info = track_data[i] if i < len(track_data) else None
        file_data['comment'] = (track_info[ROW_COMMENT]
                                if track_info and len(track_info) > ROW_COMMENT else "")

        if options.get('rename'):
            file_data['_rename'] = True

        if track_info is not None:
            if options.get('track'):
                file_data['tracknumber'] = track_info[ROW_NUM] if track_info and track_info[ROW_NUM] else str(i + 1)
            if options.get('title') and len(track_info) > ROW_TITLE:
                file_data['title'] = track_info[ROW_TITLE]
            if options.get('artist') and len(track_info) > ROW_ARTIST:
                raw = track_info[ROW_ARTIST]
                file_data['artist'] = (normalize_artist(raw) if normalize_artist else raw) or raw
            if options.get('lyrics') and len(track_info) > ROW_LYRICS:
                file_data['_lyrics'] = track_info[ROW_LYRICS]
        elif options.get('track'):
            file_data['tracknumber'] = str(i + 1)

        result[file_path] = file_data
    return result
