import json

import pytest

from eirekes_manager.core.artist_catalog import (
    ArtistCatalog, TAG_AKV, TAG_PRINS, artists_from_plex_csv, clean_segment,
    normalize_key, split_artists, update_catalog_file, write_catalog_data)


# ---------- pure helpers ----------
@pytest.mark.parametrize("a, b", [
    ("De Steijnzoel’n", "steijnzoeln"),
    ("Geloeif Mé Goed", "geloeif me goed"),
    ("Den Bremt", "bremt"),
    ("d'Oilsjteneirs", "oilsjteneirs"),
    ("  POSSENSJE ", "possensje"),
])
def test_normalize_key_ignores_spelling(a, b):
    assert normalize_key(a) == normalize_key(b)


def test_normalize_key_keeps_different_names_apart():
    assert normalize_key("Den Bremt") != normalize_key("Gary")


@pytest.mark.parametrize("raw, expected", [
    ("  Den   Bremt. ", "Den Bremt"),
    ("AKV Possensje", "Possensje"),
    ("Possensje 2019", "Possensje"),        # year suffix removed...
    ("Prins Ver 2019", "Prins Ver 2019"),   # ...but kept for prinsen
    ("Gary)", "Gary"),
    ("’t Es Noig", "'t Es Noig"),
])
def test_clean_segment(raw, expected):
    assert clean_segment(raw) == expected


@pytest.mark.parametrize("raw, lead, feat", [
    ("", [], []),
    ("Den Bremt & Gary", ["Den Bremt", "Gary"], []),
    ("Den Bremt, Gary en Jos", ["Den Bremt", "Gary", "Jos"], []),
    ("Den Bremt ft. Jos", ["Den Bremt"], ["Jos"]),
    ("Den Bremt feat. Gary & Jos", ["Den Bremt"], ["Gary", "Jos"]),
    ("Den Bremt featuring Jos", ["Den Bremt"], ["Jos"]),
    # protected duo names are never split
    ("Lekken en plekken & Den Bremt", ["Lekken & Plekken", "Den Bremt"], []),
    ("Verdwoldj & Verloeren", ["Verdwoldj En Verloeren"], []),
    # whole-string alias that is a duo
    ("Frank Patrick", ["Frank", "Patrick"], []),
    # values that are not artists
    ("Den Bremt & Bonustrack", ["Den Bremt"], []),
])
def test_split_artists(raw, lead, feat):
    assert split_artists(raw) == (lead, feat)


# ---------- catalog ----------
def test_catalog_loads_names_and_ignored(catalog):
    names = catalog.names()
    assert "Den Bremt" in names
    assert "Kapotte Naam" not in names
    assert catalog.names(tag=TAG_AKV) == ["Den Bremt", "Lekken & Plekken", "Possensje"]


def test_missing_files_give_empty_catalog(tmp_path):
    cat = ArtistCatalog(str(tmp_path / "nope.json"), str(tmp_path / "nope2.json"))
    assert cat.names() == []


def test_broken_json_is_ignored(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert ArtistCatalog(str(bad)).names() == []


@pytest.mark.parametrize("raw, canonical", [
    ("den bremt", "Den Bremt"),
    ("Den Bemt", "Den Bremt"),           # built-in ALIASES typo
    ("prinsj alex", "Alex De Kegel"),    # alias from artists.json
    ("Den Board", "Peter Van Nuffel"),   # artists.json alias wins over ALIASES
    ("onbekende groep", "Onbekende Groep"),  # unknown: title-cased
])
def test_canonical(catalog, raw, canonical):
    assert catalog.canonical(raw) == canonical


@pytest.mark.parametrize("raw, normalized", [
    ("den bremt & gary ft. jos", "Den Bremt & Gary feat. Jos"),
    ("Den Bremt & den bremt", "Den Bremt"),            # duplicates removed
    ("LEP", "Lekken & Plekken"),
    ("AKV Possensje 2019", "Possensje"),
    ("Bonustrack", ""),
])
def test_normalize(catalog, raw, normalized):
    assert catalog.normalize(raw) == normalized


def test_tags_and_info(catalog):
    assert catalog.is_akv("den bremt")
    assert not catalog.is_akv("Gary")
    assert catalog.has_tag("Alex", TAG_PRINS)
    assert catalog.prins_years("Prinsj Alex") == [2018]
    assert catalog.arendprins_years("Peter Van Nuffel") == [1998]
    assert catalog.aliases("Alex De Kegel") == ["Prinsj Alex", "Alex"]


def test_contains_and_unknown_parts(catalog):
    assert catalog.contains("Prinsj Alex")
    assert not catalog.contains("Tim")
    assert catalog.unknown_parts("Den Bremt & Tim") == ["Tim"]


def test_suggest_statuses(catalog):
    text, parts = catalog.suggest("den bremt & Den Brremt & Tim")
    assert [p["status"] for p in parts] == ["known", "fuzzy", "unknown"]
    assert text == "Den Bremt & Tim"   # typo replaced, duplicate dropped


def test_short_names_are_never_auto_corrected(catalog):
    _, parts = catalog.suggest("Jss")
    assert parts[0]["status"] == "unknown"


def test_close_matches_also_uses_containment(catalog):
    assert catalog.close_matches("Den Brmt")[0] == "Den Bremt"
    assert "Zjieverleppen" in catalog.close_matches("De Zjieverleppen 2017")
    assert catalog.close_matches("") == []


def test_search(catalog):
    assert catalog.search("brem") == ["Den Bremt"]
    assert catalog.search("prinsj")[0] == "Alex De Kegel"   # found through alias
    assert catalog.search("", tag=TAG_AKV) == catalog.names(tag=TAG_AKV)
    assert len(catalog.search("", limit=2)) == 2


def test_join_and_replace(catalog):
    assert catalog.join_artists(["A", "B"], ["C"]) == "A & B feat. C"
    assert catalog.join_artists([], ["C"]) == "C"
    assert catalog.replace_artist("Den Bremt & Gary feat. Jos", "Gary", "Picqueur") == \
        "Den Bremt & Picqueur feat. Jos"


# ---------- user changes are saved ----------
def test_add_user_artist_persists(catalog, small_catalog_path):
    assert catalog.add_user_artist("De Nieuwe", tags=[TAG_AKV])
    assert not catalog.add_user_artist("de nieuwe")          # already there
    again = ArtistCatalog(small_catalog_path, catalog.user_path)
    assert again.contains("De Nieuwe")
    assert again.is_akv("De Nieuwe")


def test_toggle_tag_and_ignore_persist(catalog, small_catalog_path):
    assert catalog.toggle_tag("Gary", TAG_AKV) is True
    catalog.ignore("Jos")
    again = ArtistCatalog(small_catalog_path, catalog.user_path)
    assert again.is_akv("Gary")
    assert "Jos" not in again.names()


def test_reload_in_place(catalog, tmp_path):
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"artists": [{"name": "Enkel Ik"}]}))
    catalog.reload(str(other))
    assert catalog.names() == ["Enkel Ik"]


def test_merge_from_skips_known_and_ignored(catalog):
    added = catalog.merge_from({"Den Bremt": 3, "Kapotte Naam": 1,
                                "Nieuw": {"count": 2, "tags": {TAG_AKV}}})
    assert added == 1
    assert catalog.is_akv("Nieuw")


# ---------- Plex import / artists.json writing ----------
PLEX_CSV = (
    "albums.tracks.originalTitle\n"
    "AKV Possensje & Den Bremt\n"
    "den bremt ft. Nieuwe Groep\n"
    "Den Bemt\n"
)


def test_artists_from_plex_csv(tmp_path):
    path = tmp_path / "plex.csv"
    path.write_text(PLEX_CSV, encoding="utf-8")
    result = artists_from_plex_csv(str(path))
    assert result["Den Bremt"]["count"] == 3
    assert result["Possensje"]["tags"] == {TAG_AKV}
    assert "Nieuwe Groep" in result


def test_update_catalog_file_keeps_existing_data(tmp_path):
    csv_path = tmp_path / "plex.csv"
    csv_path.write_text(PLEX_CSV, encoding="utf-8")
    json_path = tmp_path / "artists.json"
    write_catalog_data({"artists": [{"name": "Den Bremt", "aliases": ["DB"]},
                                    {"name": "Possensje"}],
                        "ignored": ["Nieuwe Groep"]}, str(json_path))

    assert update_catalog_file(str(csv_path), str(json_path)) == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    by_name = {e["name"]: e for e in data["artists"]}
    assert by_name["Den Bremt"]["aliases"] == ["DB"]
    assert by_name["Possensje"]["tags"] == [TAG_AKV]
    assert data["ignored"] == ["Nieuwe Groep"]


def test_write_catalog_data_is_one_artist_per_line(tmp_path):
    out = tmp_path / "a.json"
    write_catalog_data({"artists": [{"name": "B", "tags": ["z", "a"]}, {"name": "A"}]}, str(out))
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[2] == '  {"name": "B", "tags": ["a", "z"]},'
    assert json.loads(out.read_text(encoding="utf-8"))["artists"][1] == {"name": "A"}
