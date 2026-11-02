import music_tag
import pytest
from mutagen import File as MutagenFile

from eirekes_manager.core.tag_values import clean_value, force_remove, safe_get

from conftest import copy_fixture


@pytest.mark.parametrize("tag, value, expected", [
    ("year", "2026", ("2026", None)),
    ("year", "2026-08-25", ("2026", None)),
    ("year", "25/08/2026", ("2026", None)),
    ("year", "2026-08-2", ("2026", None)),
    ("year", "twintig", ("twintig", "err_year")),
    ("year", "1700", ("1700", "err_year")),
    ("tracknumber", "03", ("3", None)),
    ("tracknumber", "3/12", ("3", None)),
    ("discnumber", " 1 ", ("1", None)),
    ("tracknumber", "drie", ("drie", "err_number")),
    ("compilation", "1", ("1", None)),
    ("compilation", "yes", ("yes", "err_compilation")),
    ("title", "  Den Titel ", ("Den Titel", None)),
    ("title", None, ("", None)),
    ("year", "", ("", None)),
])
def test_clean_value(tag, value, expected):
    assert clean_value(tag, value) == expected


def test_safe_get_reads_normal_values(audio_file):
    f = music_tag.load_file(audio_file)
    f["title"] = "Liedje"
    f.save()
    assert safe_get(music_tag.load_file(audio_file), "title", audio_file) == ("Liedje", False)


def _write_broken_date(path):
    easy = MutagenFile(path, easy=True)
    if easy.tags is None:
        easy.add_tags()
    easy["date"] = "2026-08-2"
    easy.save()


@pytest.fixture
def broken_year_file(tmp_path):
    """M4A with date "2026-08-2" (music_tag can't parse it; mp3 parses leniently)."""
    path = copy_fixture("silence.m4a", tmp_path)
    _write_broken_date(path)
    return path


def test_safe_get_falls_back_to_raw_text_for_broken_year(broken_year_file):
    value, broken = safe_get(music_tag.load_file(broken_year_file), "year", broken_year_file)
    assert broken
    assert value == "2026-08-2"


def test_force_remove_deletes_broken_year(broken_year_file):
    force_remove(broken_year_file, "year")
    assert safe_get(music_tag.load_file(broken_year_file), "year", broken_year_file) == ("", False)
