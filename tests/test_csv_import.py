import os

import pytest

from eirekes_manager.core.csv_import import parse_track_csv

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write(tmp_path, text, name="list.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_stoet_list_with_header_below_empty_row(tmp_path):
    path = write(tmp_path, ",,,,\n"
                           "Stoetnummer,AKV,In plex,Playlist,Thema\n"
                           "1,Verdwoldj en verloeren,TRUE,TRUE,Den toid vliegt\n"
                           "4,n oeverschot,TRUE,TRUE,t stekt ni naas\n")
    rows, guessed = parse_track_csv(path)
    assert not guessed
    assert rows == [["1", "Den toid vliegt", "Verdwoldj en verloeren"],
                    ["4", "t stekt ni naas", "n oeverschot"]]


def test_semicolon_separated(tmp_path):
    path = write(tmp_path, "Thema;AKV;Stoetnummer\nTitel;Groep;9\n")
    assert parse_track_csv(path) == ([["9", "Titel", "Groep"]], False)


def test_header_without_thema_gives_empty_title(tmp_path):
    path = write(tmp_path, "Stoetnummer,AKV\n1,Groep\n")
    assert parse_track_csv(path) == ([["1", "", "Groep"]], False)


def test_unknown_header_wide_file_guesses_columns(tmp_path):
    path = write(tmp_path, "n,a,x,y,t\n1,Groep,_,_,Titel\n")
    assert parse_track_csv(path) == ([["1", "Titel", "Groep"]], False)


def test_unknown_header_narrow_file_is_flagged(tmp_path):
    path = write(tmp_path, "n,a\n1,Groep\n")
    assert parse_track_csv(path) == ([["1", "", "Groep"]], True)


def test_bom_is_ignored(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes("Stoetnummer,AKV,Thema\n1,G,T\n".encode("utf-8-sig"))
    assert parse_track_csv(str(path))[0] == [["1", "T", "G"]]


def test_empty_file_raises(tmp_path):
    with pytest.raises(Exception):
        parse_track_csv(write(tmp_path, ""))


def test_real_stoet_list_parses():
    path = os.path.join(REPO, "Stoetliekes loist.csv")
    if not os.path.exists(path):
        pytest.skip("no stoet list in the repo")
    rows, guessed = parse_track_csv(path)
    assert not guessed
    assert rows and all(len(r) == 3 for r in rows)
    assert rows[0][0] == "1"
