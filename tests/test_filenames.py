import pytest

from eirekes_manager.core.filenames import list_audio_files, sanitize_filename, track_filename


@pytest.mark.parametrize("raw, clean", [
    ('Wa?t <is> "dat"', "Wat is dat"),
    ("a/b\\c|d*e:f", "abcdef"),
    ("  gewoon  ", "gewoon"),
    (None, ""),
])
def test_sanitize_filename(raw, clean):
    assert sanitize_filename(raw) == clean


@pytest.mark.parametrize("track, artist, title, expected", [
    ("3", "Den Bremt", "Titel", "03 - Den Bremt - Titel.mp3"),
    (12, "A", "B", "12 - A - B.mp3"),
    ("3/12", "A", "B", "00 - A - B.mp3"),
    ("", "", "", "00 - Unknown - Unknown.mp3"),
    (None, None, "???", "00 - Unknown - Unknown.mp3"),
])
def test_track_filename(track, artist, title, expected):
    assert track_filename(track, artist, title, ".mp3") == expected


def test_list_audio_files(tmp_path):
    for name in ["b.MP3", "a.flac", "c.m4a", "d.wav", "cover.jpg", "notes.txt"]:
        (tmp_path / name).write_bytes(b"")
    assert list_audio_files(str(tmp_path)) == ["a.flac", "b.MP3", "c.m4a", "d.wav"]
    assert list_audio_files(str(tmp_path / "missing")) == []
