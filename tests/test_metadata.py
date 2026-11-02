import music_tag

from eirekes_manager.core.metadata import (
    COMBO_OPTIONS, TAG_MAP, common_values, effective_metadata, form_order,
    read_compilation, read_metadata)
from eirekes_manager.i18n import TRANSLATIONS


def test_form_order_puts_release_type_after_album_artist():
    order = form_order()
    assert order[order.index("albumartist") + 1] == "releasetype"
    assert set(order) == set(TAG_MAP.values()) | {"releasetype"}


def test_every_field_has_a_label_in_every_language():
    keys = [f"lbl_{k}" for k in form_order()]
    keys += [t for options in COMBO_OPTIONS.values() for _, t in options]
    for lang, table in TRANSLATIONS.items():
        missing = [k for k in keys if k not in table]
        assert not missing, (lang, missing)


def test_read_metadata_empty_file(audio_file):
    data = read_metadata(audio_file)
    assert set(data) == set(TAG_MAP.values()) | {"releasetype"}
    assert data["title"] == ""
    assert data["compilation"] == ""
    assert data["totaltracks"] == ""   # "0" is shown as empty


def test_read_metadata_never_raises(tmp_path):
    bad = tmp_path / "kapot.mp3"
    bad.write_bytes(b"nope")
    assert read_metadata(str(bad)) == {"releasetype": ""}


def test_read_compilation(mp3_file):
    f = music_tag.load_file(mp3_file)
    assert read_compilation(f) == ""
    f["compilation"] = True
    f.save()
    assert read_compilation(music_tag.load_file(mp3_file)) == "1"


def test_effective_metadata_applies_pending(mp3_file):
    data = effective_metadata(mp3_file, {"title": "Nieuw", "_rename": True})
    assert data["title"] == "Nieuw"
    assert "_rename" not in data


def test_common_values():
    assert common_values([]) == {}
    assert common_values([{"a": "1", "b": "x"}, {"a": "1", "b": "y"}]) == {"a": "1", "b": None}
    assert common_values([{"a": "1"}, {}]) == {"a": None}
