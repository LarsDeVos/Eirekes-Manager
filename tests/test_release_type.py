from eirekes_manager.core.release_type import RELEASE_TYPES, read_release_type, write_release_type


def test_not_set_reads_empty(audio_file):
    assert read_release_type(audio_file) == ""


def test_write_read_and_remove(audio_file):
    write_release_type(audio_file, "Single")
    assert read_release_type(audio_file) == "single"

    write_release_type(audio_file, "ep")
    assert read_release_type(audio_file) == "ep"

    write_release_type(audio_file, "")
    assert read_release_type(audio_file) == ""


def test_unreadable_file_reads_empty(tmp_path):
    bad = tmp_path / "kapot.mp3"
    bad.write_bytes(b"not audio")
    assert read_release_type(str(bad)) == ""


def test_release_types_have_translations():
    from eirekes_manager.i18n import TRANSLATIONS
    for _, key in RELEASE_TYPES:
        for lang in TRANSLATIONS.values():
            assert key in lang
