# src/eirekes_manager/core/csv_import.py
"""Read a track list CSV (e.g. "Stoetliekes loist.csv")."""

import csv

# Header names in the "stoet" list
HEADER_TRACK, HEADER_ARTIST, HEADER_TITLE = "stoetnummer", "akv", "thema"


def parse_track_csv(path):
    """Return (rows, guessed): rows = [[track, title, artist], ...].

    The header row with "Stoetnummer" / "AKV" / "Thema" may be anywhere
    (empty lines above it are skipped). Without it the first row is the
    header and the columns are guessed; guessed=True means the file has
    fewer than 3 columns, so the result should be checked by the user.
    Raises ValueError for an empty file.
    """
    with open(path, mode='r', encoding='utf-8-sig', newline='') as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        rows = list(csv.reader(f, dialect))
    if not rows:
        raise ValueError("empty file")

    header_idx = -1
    guessed = False
    col_map = {"track": -1, "artist": -1, "title": -1}
    for i, row in enumerate(rows):
        row_lower = [c.lower().strip() for c in row]
        if HEADER_TRACK in row_lower and HEADER_ARTIST in row_lower:
            header_idx = i
            col_map["track"] = row_lower.index(HEADER_TRACK)
            col_map["artist"] = row_lower.index(HEADER_ARTIST)
            if HEADER_TITLE in row_lower:
                col_map["title"] = row_lower.index(HEADER_TITLE)
            break

    if header_idx == -1:
        header_idx = 0
        if len(rows[0]) >= 3:
            col_map = {"track": 0, "artist": 1, "title": 4}
        else:
            guessed = True
            col_map = {"track": 0, "artist": 1, "title": 2}

    def get_col(row, idx):
        return row[idx] if 0 <= idx < len(row) else ""

    data = [[get_col(row, col_map["track"]), get_col(row, col_map["title"]),
             get_col(row, col_map["artist"])]
            for row in rows[header_idx + 1:]]
    return data, guessed
