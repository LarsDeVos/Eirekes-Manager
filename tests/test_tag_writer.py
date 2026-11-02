import os

import music_tag
import pytest
from mutagen import File as MutagenFile
from mutagen.mp4 import MP4

from eirekes_manager.core.metadata import read_metadata
from eirekes_manager.core.release_type import read_release_type
from eirekes_manager.core.tag_writer import save_file_changes, save_pending

from conftest import copy_fixture


def test_writes_text_and_number_tags(audio_file):
    result = save_file_changes(audio_file, {
        "title": "Ik Leef Vér Carnaval", "artist": "Den Bremt", "album": "Stoet 2026",
        "year": "2026-02-28", "tracknumber": "03", "genre": "Carnaval", "compilation": "1",
    })
    assert result.ok, result.errors
    data = read_metadata(audio_file)
    assert data["title"] == "Ik Leef Vér Carnaval"
    assert data["artist"] == "Den Bremt"
    assert data["year"] == "2026"          # cleaned
    assert data["tracknumber"] == "3"
    assert data["compilation"] == "1"


def test_empty_number_removes_the_tag(audio_file):
    save_file_changes(audio_file, {"tracknumber": "5", "year": "2020"})
    result = save_file_changes(audio_file, {"tracknumber": "", "year": ""})
    assert result.ok
    data = read_metadata(audio_file)
    assert data["tracknumber"] in ("", "0")   # m4a used to keep the number
    assert data["year"] == ""


def test_overwrites_existing_number(audio_file):
    save_file_changes(audio_file, {"tracknumber": "5"})
    save_file_changes(audio_file, {"tracknumber": "7"})
    assert read_metadata(audio_file)["tracknumber"] == "7"


def test_invalid_value_fails_only_that_field(mp3_file):
    result = save_file_changes(mp3_file, {"title": "Goed", "year": "twintig"})
    assert not result.ok
    assert result.failed == {mp3_file: {"year": "twintig"}}
    assert "twintig" in result.errors[0]
    assert read_metadata(mp3_file)["title"] == "Goed"


def test_broken_year_in_file_is_replaced(tmp_path):
    path = copy_fixture("silence.m4a", tmp_path)
    easy = MutagenFile(path, easy=True)
    easy["date"] = "2026-08-2"
    easy.save()
    result = save_file_changes(path, {"year": "2025"})
    assert result.ok, result.errors
    assert read_metadata(path)["year"] == "2025"


def test_release_type(audio_file):
    assert save_file_changes(audio_file, {"releasetype": "single"}).ok
    assert read_release_type(audio_file) == "single"


def test_rename(mp3_file):
    result = save_file_changes(mp3_file, {"title": "Den Titel?", "artist": "Den Bremt",
                                          "tracknumber": "4", "_rename": True})
    assert result.ok
    assert os.path.basename(result.path) == "04 - Den Bremt - Den Titel.mp3"
    assert os.path.exists(result.path) and not os.path.exists(mp3_file)


def test_rename_uses_file_values_when_not_changed(mp3_file):
    save_file_changes(mp3_file, {"title": "Oud", "artist": "Gary", "tracknumber": "2"})
    result = save_file_changes(mp3_file, {"title": "Nieuw", "_rename": True})
    assert os.path.basename(result.path) == "02 - Gary - Nieuw.mp3"


def test_no_rename_without_flag(mp3_file):
    result = save_file_changes(mp3_file, {"title": "X"})
    assert result.path == mp3_file


def test_lyrics_written_next_to_renamed_file(mp3_file):
    result = save_file_changes(mp3_file, {"title": "Liedje", "artist": "Gary", "tracknumber": "1",
                                          "_rename": True, "_lyrics": "la la\nlo lo"})
    txt = os.path.splitext(result.path)[0] + ".txt"
    with open(txt, encoding="utf-8") as fh:
        assert fh.read() == "la la\nlo lo"


@pytest.mark.parametrize("ext", ["mp3", "m4a", "flac"])
def test_artwork(tmp_path, cover_jpg, ext):
    path = copy_fixture(f"silence.{ext}", tmp_path)
    result = save_file_changes(path, {"_artwork_path": cover_jpg})
    assert result.ok, result.errors
    if ext == "m4a":
        assert MP4(path)["covr"]
    else:
        assert music_tag.load_file(path)["artwork"].first.data


def test_missing_file(tmp_path):
    path = str(tmp_path / "weg.mp3")
    result = save_file_changes(path, {"title": "x"})
    assert not result.ok
    assert result.failed == {path: {}}


def test_read_only_file_keeps_all_changes(mp3_file):
    os.chmod(mp3_file, 0o444)
    try:
        result = save_file_changes(mp3_file, {"title": "x"})
    finally:
        os.chmod(mp3_file, 0o644)
    assert result.failed == {mp3_file: {"title": "x"}}


def test_corrupt_file_keeps_all_changes(tmp_path):
    path = tmp_path / "kapot.mp3"
    path.write_bytes(b"not audio at all")
    result = save_file_changes(str(path), {"title": "x"})
    assert not result.ok
    assert result.failed == {str(path): {"title": "x"}}


def test_save_pending_counts_and_collects(tmp_path):
    good = copy_fixture("silence.mp3", tmp_path, "a.mp3")
    bad = copy_fixture("silence.mp3", tmp_path, "b.mp3")
    batch = save_pending({good: {"title": "A"}, bad: {"year": "nooit"}})
    assert batch.count == 1
    assert batch.paths == [good, bad]
    assert batch.failed == {bad: {"year": "nooit"}}
    assert len(batch.errors) == 1
