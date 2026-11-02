# Eirekes Manager

Tag carnival music files (Oilsjterse Liekes): fetch track lists from
oilsjterseliekes.be or a CSV, clean up artist names, write tags / cover art /
lyrics and rename the files.

## Run

```bash
pip install -r requirements.txt
cd src && python main.py
```

## Project layout

```
src/
  main.py                 entry point (also used by main.spec / PyInstaller)
  artists.json            bundled artist list (the online update downloads this file - don't move it)
  eirekes_manager/
    core/                 pure Python logic, no Qt - covered by tests/
      artist_catalog.py   artist list, spelling normalisation, suggestions
      artist_review.py    ok / corrected / fuzzy / unknown status for the web matcher
      artist_sync.py      download a newer artists.json
      csv_import.py       read a "stoet" CSV
      filenames.py        "03 - Artist - Title.mp3"
      metadata.py         which fields the editor shows, reading tags
      release_type.py     RELEASETYPE tag (Album / Single / EP ...)
      staging.py          matched rows -> pending changes per file
      tag_values.py       validate / clean values, read broken tags
      tag_writer.py       save tags, artwork, rename, lyrics
    scraping/             oilsjterseliekes.be album + lyrics (parsing separate from downloading)
    ui/                   PyQt6 windows and widgets
    i18n.py               translations
    paths.py              bundled files, log folder
tests/                    pytest suite (+ tiny silent audio files in tests/fixtures)
legacy/                   the original stand-alone script, not used by the app
```

Rule of thumb: logic goes in `core/` (testable without a screen), `ui/` only
shows it and calls into `core/`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests run on real mp3 / m4a / flac / wav files (copied to a temp folder),
so tag writing is checked for every format. The UI tests run without a screen
and use their own settings file, so they never touch your app settings.
`tests/test_artists_json.py` checks `src/artists.json` - run it after editing
the list (duplicate names / aliases, unknown tags, ...).

GitHub Actions runs the tests on every push and pull request
(`.github/workflows/tests.yml`).

## Update the artist list from a Plex export

```bash
cd src && python -m eirekes_manager.core.artist_catalog <plex-export.csv>
```
