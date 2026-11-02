import json
import os

import pytest
import requests

from eirekes_manager.core import artist_sync
from eirekes_manager.core.artist_sync import fetch, pick_catalog_file, to_raw_url, validate

VALID = {"artists": [{"name": "Den Bremt"}, "Gary"]}


@pytest.mark.parametrize("url, raw", [
    ("https://github.com/LarsDeVos/Eirekes-Manager/blob/main/src/artists.json",
     "https://raw.githubusercontent.com/LarsDeVos/Eirekes-Manager/main/src/artists.json"),
    ("https://git.example.be/o/r/src/branch/main/artists.json",
     "https://git.example.be/o/r/raw/branch/main/artists.json"),
    ("https://raw.githubusercontent.com/o/r/main/a.json",
     "https://raw.githubusercontent.com/o/r/main/a.json"),
    ("  ", ""),
])
def test_to_raw_url(url, raw):
    assert to_raw_url(url) == raw


@pytest.mark.parametrize("data, ok", [
    (VALID, True),
    ({"artists": []}, False),
    ({"artists": [{"tags": ["akv"]}]}, False),
    ({"artists": [1]}, False),
    ([], False),
    (None, False),
])
def test_validate(data, ok):
    assert validate(data) is ok


def _write(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def test_pick_catalog_file_prefers_newest_valid(tmp_path):
    bundled, cache = str(tmp_path / "bundled.json"), str(tmp_path / "cache.json")
    _write(bundled, VALID)
    assert pick_catalog_file(bundled, cache) == bundled     # no cache yet
    _write(cache, VALID)
    os.utime(bundled, (1, 1))
    assert pick_catalog_file(bundled, cache) == cache
    _write(cache, {"artists": []})                            # broken download
    assert pick_catalog_file(bundled, cache) == bundled


class FakeResponse:
    def __init__(self, status=200, data=None, headers=None, text=None):
        self.status_code = status
        self._data = data
        self.headers = headers or {}
        self._text = text

    def json(self):
        if self._text is not None:
            raise ValueError("not json")
        return self._data


@pytest.fixture
def fake_get(monkeypatch):
    calls = []

    def install(response):
        def get(url, headers=None, timeout=None):
            calls.append({"url": url, "headers": headers})
            if isinstance(response, Exception):
                raise response
            return response
        monkeypatch.setattr(artist_sync.requests, "get", get)
        return calls
    return install


def test_fetch_downloads_and_caches(tmp_path, fake_get):
    cache = str(tmp_path / "sub" / "cache.json")
    calls = fake_get(FakeResponse(200, VALID, {"ETag": "abc"}))
    status, _ = fetch("https://github.com/o/r/blob/main/a.json", cache, token="t0k")
    assert status == "updated"
    assert calls[0]["url"] == "https://raw.githubusercontent.com/o/r/main/a.json"
    assert calls[0]["headers"]["Authorization"] == "token t0k"
    with open(cache, encoding="utf-8") as fh:
        assert json.load(fh) == VALID

    # second time: conditional request, same content -> unchanged
    calls = fake_get(FakeResponse(200, VALID))
    assert fetch("https://github.com/o/r/blob/main/a.json", cache)[0] == "unchanged"
    assert calls[-1]["headers"]["If-None-Match"] == "abc"


def test_fetch_not_modified(tmp_path, fake_get):
    fake_get(FakeResponse(304))
    assert fetch("https://x/a.json", str(tmp_path / "c.json"))[0] == "unchanged"


@pytest.mark.parametrize("response, hint", [
    (FakeResponse(404), "404"),
    (FakeResponse(401), "token"),
    (FakeResponse(500), "500"),
    (FakeResponse(200, text="<html>login</html>"), "JSON"),
    (FakeResponse(200, {"artists": []}), "not a valid"),
    (requests.ConnectionError("offline"), "no connection"),
])
def test_fetch_errors_keep_old_cache(tmp_path, fake_get, response, hint):
    cache = str(tmp_path / "cache.json")
    _write(cache, VALID)
    fake_get(response)
    status, message = fetch("https://x/a.json", cache)
    assert status == "error"
    assert hint in message
    with open(cache, encoding="utf-8") as fh:
        assert json.load(fh) == VALID
