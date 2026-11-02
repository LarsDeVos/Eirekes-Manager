from eirekes_manager.core.staging import CSV_OPTIONS, GENRE, build_staged_changes

ALL = {'title': True, 'artist': True, 'track': True, 'rename': True, 'lyrics': True}
NONE = dict.fromkeys(ALL, False)
ALBUM = ["Stoet 2026", "x", "2026", "", ""]


def test_full_match():
    staged = build_staged_changes(
        ["a.mp3"], [["7", "Titel", "den bremt", "lyrics", "Origineel"]], ALBUM, ALL,
        normalize_artist=str.title)
    assert staged == {"a.mp3": {
        "album": "Stoet 2026", "year": "2026", "genre": GENRE, "comment": "Origineel",
        "_rename": True, "tracknumber": "7", "title": "Titel", "artist": "Den Bremt",
        "_lyrics": "lyrics"}}


def test_options_off_only_sets_album_genre_comment():
    staged = build_staged_changes(["a.mp3"], [["7", "T", "A", "L", "C"]], None, NONE)
    assert staged == {"a.mp3": {"genre": GENRE, "comment": "C"}}


def test_more_files_than_rows_get_a_track_number():
    staged = build_staged_changes(["a", "b", "c"], [["1", "T", "A"]], None, ALL)
    assert staged["b"]["tracknumber"] == "2"
    assert staged["c"] == {"genre": GENRE, "comment": "", "_rename": True, "tracknumber": "3"}


def test_empty_track_number_uses_position():
    staged = build_staged_changes(["a", "b"], [["1", "T", "A"], ["", "T2", "B"]], None, ALL)
    assert staged["b"]["tracknumber"] == "2"


def test_artist_falls_back_to_raw_when_normalizer_returns_empty():
    staged = build_staged_changes(["a"], [["1", "T", "Bonustrack"]], None, ALL,
                                  normalize_artist=lambda s: "")
    assert staged["a"]["artist"] == "Bonustrack"


def test_append_keeps_existing_changes_without_mutating_them():
    existing = {"a": {"composer": "Jos", "title": "Oud"}}
    staged = build_staged_changes(["a"], [["1", "Nieuw", "A"]], None, CSV_OPTIONS,
                                  existing=existing)
    assert staged["a"]["composer"] == "Jos"
    assert staged["a"]["title"] == "Nieuw"
    assert existing == {"a": {"composer": "Jos", "title": "Oud"}}


def test_csv_options_do_not_write_lyrics():
    staged = build_staged_changes(["a"], [["1", "T", "A", "L"]], None, CSV_OPTIONS)
    assert "_lyrics" not in staged["a"]
