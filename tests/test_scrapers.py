"""Scraper parsing on saved HTML snippets (no network)."""

from eirekes_manager.scraping import album_scraper
from eirekes_manager.scraping.album_scraper import (
    AlbumScraper, ORIGINAL_TAG, extract_td_content, finalize_track, parse_album_html,
    process_string, replace_incorrect_chars, split_original_comment)
from eirekes_manager.scraping.lyrics_scraper import (
    normalize_title, parse_lyrics, parse_track_links)

ALBUM_HTML = """
<table>
<tr><td>Stoet 2026</td><td>Oilsjterse Liekes</td><td>2026</td><td>CD</td><td>Info</td></tr>
<tr><td>1</td><td>Ik Leef V&#233;r Carnaval</td><td>Den Bremt<br>Origineel nummer: Song One</td></tr>
<tr><td>2</td><td>Den Toid Vliegt</td><td><strong>Gary</strong> Origineel nummer: <span>Song Two</span></td></tr>
<tr><td>3</td><td>Zonder Origineel</td><td>Jos</td></tr>
</table>
"""


def test_extract_td_content_splits_block_tags():
    cells = extract_td_content("<td>a<br/>b</td><td><b>Label:</b> val</td><td>open")
    assert cells == ["a\nb", "Label:  val"]


def test_replace_incorrect_chars():
    assert replace_incorrect_chars("&#8217;t Es&nbsp;Noig") == "'t Es Noig"
    assert replace_incorrect_chars("Tekst: X") == "X"
    assert replace_incorrect_chars("A Origineel nummer : B") == f"A {ORIGINAL_TAG} B"
    assert replace_incorrect_chars("a\n\n  \nb") == "a\nb"


def test_process_string_needs_album_header():
    assert process_string(["a", "b"]) == ([], [])


def test_process_string_drops_invalid_year_and_empty_tracks():
    album, tracks = process_string(["Album", "x", "26", "y", "z", "1", "Titel", "2"])
    assert album[2] == ""
    assert tracks == [["1", "Titel"]]


def test_split_original_comment_same_line():
    track = ["1", "Titel", f"Den Bremt {ORIGINAL_TAG} Song"]
    assert split_original_comment(track) == "Song"
    assert track == ["1", "Titel", "Den Bremt"]


def test_split_original_comment_next_line():
    track = ["1", "Titel", "Den Bremt", ORIGINAL_TAG, "Song"]
    assert split_original_comment(track) == "Song"
    assert track == ["1", "Titel", "Den Bremt"]


def test_split_original_comment_tag_at_line_end():
    track = ["1", "Titel", f"Den Bremt {ORIGINAL_TAG}", "Song"]
    assert split_original_comment(track) == "Song"
    assert track == ["1", "Titel", "Den Bremt"]


def test_finalize_track_shape_and_lyrics():
    lyrics = {"ik leef ver carnaval": "la la"}
    assert finalize_track(["1", "Ik Leef Vér Carnaval"], lyrics) == \
        ["1", "Ik Leef Vér Carnaval", "", "la la", ""]


def test_parse_album_html():
    album, tracks = parse_album_html(ALBUM_HTML)
    assert album[0] == "Stoet 2026" and album[2] == "2026"
    for t in tracks:
        finalize_track(t, {})
    assert tracks == [
        ["1", "Ik Leef V&#233;r Carnaval", "Den Bremt", "", "Song One"],
        ["2", "Den Toid Vliegt", "Gary", "", "Song Two"],
        ["3", "Zonder Origineel", "Jos", "", ""],
    ]


def test_fetch_data_combines_tracks_and_lyrics(monkeypatch):
    class Resp:
        text = ALBUM_HTML

        def raise_for_status(self):
            pass

    monkeypatch.setattr(album_scraper.requests, "get", lambda url, timeout=None: Resp())
    scraper = AlbumScraper()
    monkeypatch.setattr(scraper.lyrics_scraper, "get_lyrics_map_from_album",
                        lambda url: {"den toid vliegt": "tekst"})
    album, tracks = scraper.fetch_data("https://oilsjterseliekes.be/albums/x")
    assert tracks[1] == ["2", "Den Toid Vliegt", "Gary", "tekst", "Song Two"]


def test_fetch_data_network_error_returns_empty(monkeypatch):
    def boom(url, timeout=None):
        raise OSError("offline")
    monkeypatch.setattr(album_scraper.requests, "get", boom)
    assert AlbumScraper().fetch_data("https://x") == ([], [])


# ---------- lyrics ----------
def test_normalize_title():
    assert normalize_title("Ik Leef V&#233;r Carnaval!") == "ik leef ver carnaval"
    assert normalize_title("’t Es  Noig") == "t es noig"


def test_parse_track_links():
    html = """<a href="https://oilsjterseliekes.be/tracks/a/">a</a>
              <a href="/tracks/b/">b</a><a href="nl/tracks/c/">c</a>
              <a href="/tracks/b/">dup</a><a href="https://elders.be/tracks/x">x</a>
              <a href="/albums/y/">y</a>"""
    assert parse_track_links(html) == [
        "https://oilsjterseliekes.be/tracks/a/",
        "https://oilsjterseliekes.be/tracks/b/",
        "https://oilsjterseliekes.be/nl/tracks/c/",
    ]


def test_parse_lyrics():
    page = "<h1>Titel</h1><div class='tekst'>" + "<p>regel</p>" * 5 + "</div>"
    lyrics, soup = parse_lyrics(page)
    assert lyrics == "\n".join(["regel"] * 5)
    assert soup.find("h1").get_text() == "Titel"


def test_parse_lyrics_too_short_or_missing():
    assert parse_lyrics("<div class='tekst'><p>kort</p></div>")[0] is None
    assert parse_lyrics("<p>geen tekst</p>")[0] is None
