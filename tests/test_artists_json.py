"""Checks on the real artist list (src/artists.json) - run after editing it."""

import json
import os
from collections import defaultdict

import pytest

from eirekes_manager.core.artist_catalog import (
    ArtistCatalog, ENTRY_FIELDS, TAG_AKV, TAG_ARENDPRINS, TAG_PRINS, normalize_key)
from eirekes_manager.core.artist_sync import validate
from eirekes_manager.paths import resource_path

ARTISTS_JSON = resource_path("artists.json")
KNOWN_TAGS = {TAG_AKV, TAG_PRINS, TAG_ARENDPRINS}


@pytest.fixture(scope="module")
def data():
    with open(ARTISTS_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def test_file_is_valid(data):
    assert validate(data)


def test_entries_only_use_known_fields_and_tags(data):
    for entry in data["artists"]:
        assert set(entry) <= set(ENTRY_FIELDS) | {"count"}, entry
        assert set(entry.get("tags", [])) <= KNOWN_TAGS, entry


def test_prins_years_have_the_prins_tag(data):
    for entry in data["artists"]:
        if entry.get("prins"):
            assert TAG_PRINS in entry.get("tags", []), entry["name"]
        if entry.get("arendprins"):
            assert TAG_ARENDPRINS in entry.get("tags", []), entry["name"]


def test_no_duplicate_names_or_aliases(data):
    """Every name/alias points to exactly one artist."""
    owners = defaultdict(set)
    for entry in data["artists"]:
        owners[normalize_key(entry["name"])].add(entry["name"])
        for alias in entry.get("aliases", []):
            owners[normalize_key(alias)].add(entry["name"])
    clashes = {k: v for k, v in owners.items() if len(v) > 1}
    assert not clashes


def test_catalog_loads_every_entry(data):
    catalog = ArtistCatalog(ARTISTS_JSON)
    ignored = {normalize_key(n) for n in data.get("ignored", [])}
    for entry in data["artists"]:
        if normalize_key(entry["name"]) not in ignored:
            assert catalog.contains(entry["name"]), entry["name"]


def test_bundled_file_is_where_the_update_url_points():
    # DEFAULT_URL downloads src/artists.json from GitHub: don't move the file
    assert os.path.basename(os.path.dirname(ARTISTS_JSON)) == "src"
