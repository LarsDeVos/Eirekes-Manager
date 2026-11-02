"""The Qt windows, run without a screen (QT_QPA_PLATFORM=offscreen).

The main window gets its own settings file / data folder / log folder, so
the tests never touch your real app settings.
"""

import os

import pytest
from PyQt6.QtCore import QSettings, Qt

from eirekes_manager.core.metadata import read_metadata
from eirekes_manager.ui.artist_field import ArtistField, ArtistPickerDialog, _split_current_segment
from eirekes_manager.ui.csv_matcher import CsvMatcherDialog
from eirekes_manager.ui.main_window import MusicTaggerApp, image_to_jpeg
from eirekes_manager.ui.web_matcher import COL_ARTIST, WebMatcherDialog

from conftest import copy_fixture


@pytest.mark.parametrize("text, head, tail", [
    ("Den Bremt & ga", "Den Bremt & ", "ga"),
    ("Den Bremt feat. jo", "Den Bremt feat. ", "jo"),
    ("Possensje, Den", "Possensje, ", "Den"),
    ("Gary", "", "Gary"),
])
def test_split_current_segment(text, head, tail):
    assert _split_current_segment(text) == (head, tail)


@pytest.fixture
def music_folder(tmp_path):
    folder = tmp_path / "music"
    folder.mkdir()
    copy_fixture("silence.mp3", folder, "b.mp3")
    copy_fixture("silence.m4a", folder, "a.m4a")
    return str(folder)


@pytest.fixture
def window(qapp, tmp_path, music_folder):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("artist_list_auto", False)   # no network
    settings.setValue("last_folder", music_folder)
    win = MusicTaggerApp(settings=settings, data_dir=str(tmp_path / "data"),
                         log_dir=str(tmp_path / "logs"))
    yield win
    win.close()


def select(win, *rows):
    win.file_list_widget.clearSelection()
    for r in rows:
        win.file_list_widget.item(r).setSelected(True)


def test_window_restores_last_folder(window):
    assert [i.text() for i in window.list_items()] == ["a.m4a", "b.mp3"]
    assert len(window.catalog.names()) > 0


def test_language_switch_updates_texts(window):
    window.change_language("nl")
    nl = window.btn_load_folder.text()
    window.change_language("en")
    assert window.btn_load_folder.text() != nl


def test_edit_field_and_save(window, music_folder):
    select(window, 1)
    title = window.meta_fields["Title"]
    title.setText("Nieuwe Titel")
    title.textEdited.emit("Nieuwe Titel")
    path = os.path.join(music_folder, "b.mp3")
    assert window.pending_changes == {path: {"title": "Nieuwe Titel"}}
    assert window.file_list_widget.item(1).text().startswith("*")

    window.save_all_changes()
    assert window.pending_changes == {}
    assert read_metadata(path)["title"] == "Nieuwe Titel"


def test_invalid_year_stays_pending(window, music_folder):
    select(window, 1)
    year = window.meta_fields["Year"]
    year.setText("ooit")
    year.textEdited.emit("ooit")
    assert "ff6b6b" in year.styleSheet()     # red border right away

    window.save_all_changes()
    path = os.path.join(music_folder, "b.mp3")
    assert window.pending_changes == {path: {"year": "ooit"}}
    assert window.file_list_widget.item(1).text().startswith("!")


def test_multi_selection_shows_common_values(window):
    for r, title in ((0, "Zelfde"), (1, "Zelfde")):
        select(window, r)
        window.stage_value_for_selection("title", title)
    select(window, 0)
    window.stage_value_for_selection("album", "Een")
    select(window, 1)
    window.stage_value_for_selection("album", "Twee")

    select(window, 0, 1)
    assert window.meta_fields["Title"].text() == "Zelfde"
    assert window.meta_fields["Album"].text() == ""
    assert window.meta_fields["Album"].placeholderText() != ""


def test_combo_field_stages_value(window, music_folder):
    select(window, 0)
    cb = window.combo_fields["releasetype"]
    window.on_combo_edit("releasetype", cb.findData("single"))
    assert window.pending_changes[os.path.join(music_folder, "a.m4a")] == {"releasetype": "single"}


def test_stage_matches_and_save_renames(window, music_folder):
    files = [os.path.join(music_folder, n) for n in ("a.m4a", "b.mp3")]
    tracks = [["1", "Eerste", "den bremt", "tekst", "Orig"], ["2", "Tweede", "Gary", "", ""]]
    options = {'title': True, 'artist': True, 'track': True, 'rename': True, 'lyrics': True}
    window.stage_matches(files, tracks, ["Stoet", "", "2026", "", ""], options)

    assert window.list_items()[0].text() == "* 01 - Den Bremt - Eerste.m4a"
    window.save_all_changes()
    names = sorted(os.listdir(music_folder))
    assert names == ["01 - Den Bremt - Eerste.m4a", "01 - Den Bremt - Eerste.txt",
                     "02 - Gary - Tweede.mp3"]
    data = read_metadata(os.path.join(music_folder, "02 - Gary - Tweede.mp3"))
    assert (data["album"], data["year"], data["genre"]) == ("Stoet", "2026", "Carnaval")


def test_normalize_selected_artists(window):
    select(window, 0)
    window.stage_value_for_selection("artist", "den bremt ft. gary")
    window.normalize_selected_artists()
    path = window.list_items()[0].data(Qt.ItemDataRole.UserRole)
    assert window.pending_changes[path]["artist"] == "Den Bremt feat. Gary"


def test_image_to_jpeg(cover_jpg, tmp_path):
    assert image_to_jpeg(cover_jpg)[:2] == b"\xff\xd8"
    (tmp_path / "x.jpg").write_bytes(b"no image")
    assert image_to_jpeg(str(tmp_path / "x.jpg")) is None


# ---------- dialogs ----------
def test_web_matcher_fills_and_colours_table(qapp, catalog, monkeypatch):
    dlg = WebMatcherDialog(["/x/a.mp3", "/x/b.mp3"], catalog=catalog)
    monkeypatch.setattr(dlg.scraper, "fetch_data", lambda url: (
        ["Album", "", "2026", "", ""],
        [["1", "T1", "den bremt", "", ""], ["2", "T2", "Volledig Onbekend", "", "Orig"]]))
    dlg.url_input.setText("https://oilsjterseliekes.be/albums/x")
    dlg.run_fetch()

    assert dlg.web_table.item(0, COL_ARTIST).text() == "Den Bremt"
    assert dlg.web_table.item(0, COL_ARTIST).data(Qt.ItemDataRole.UserRole) == "corrected"
    assert dlg.web_table.item(1, COL_ARTIST).data(Qt.ItemDataRole.UserRole) == "unknown"

    got = []
    dlg.matches_confirmed.connect(lambda *args: got.append(args))
    dlg.confirm_matches()
    files, tracks, album, options = got[0]
    assert files == ["/x/a.mp3", "/x/b.mp3"]
    assert tracks[1] == ["2", "T2", "Volledig Onbekend", "", "Orig"]
    assert album[0] == "Album" and options["rename"] is True


def test_csv_matcher_link_and_apply(qapp, monkeypatch, tmp_path):
    csv_path = tmp_path / "l.csv"
    csv_path.write_text("Stoetnummer,AKV,Thema\n1,Gary,Een\n2,Jos,Twee\n", encoding="utf-8")
    from eirekes_manager.ui import csv_matcher
    monkeypatch.setattr(csv_matcher.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(csv_path), "")))
    dlg = CsvMatcherDialog(["/x/a.mp3", "/x/b.mp3"])
    dlg.load_csv()
    assert dlg.csv_table.rowCount() == 2

    got = []
    dlg.matches_confirmed.connect(lambda *args: got.append(args))
    dlg.file_list.item(1).setSelected(True)
    dlg.csv_table.selectRow(0)
    dlg.link_selected_pair()
    assert got[0] == (["/x/b.mp3"], [["1", "Een", "Gary"]], None, True)

    dlg.confirm_all_matches()
    assert got[1] == (["/x/a.mp3"], [["2", "Twee", "Jos"]], None, False)


def test_artist_field_and_picker(qapp, catalog):
    field = ArtistField(catalog)
    field.edit.setText("den bremt")
    field.refresh_hint()
    picker = ArtistPickerDialog(catalog, "Den Bremt feat. Gary")
    assert picker.result_text() == "Den Bremt feat. Gary"
