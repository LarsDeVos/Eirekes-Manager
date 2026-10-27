# src/artist_sync.py
"""
Keep the artist list up to date from the internet.

The app downloads artists.json from your git server (Forgejo/Gitea raw URL)
and keeps a local copy ("cache"), so it also works offline:

  1. at start the newest local copy is used immediately
     (downloaded cache, or the artists.json next to the app - whichever is newer)
  2. in the background the server is asked for a newer version
     (ETag / Last-Modified: nothing is downloaded when it did not change)
  3. a valid new version replaces the cache and the list is reloaded

Your own additions in the app stay in artists_user.json and are never
overwritten by a download.
"""

import json
import logging
import os
import re
import threading

import requests

DEFAULT_URL = "https://git.triskelion.be/larsdevos/eirekesmanager/raw/branch/main/src/artists.json"
TIMEOUT = 10  # seconds


def to_raw_url(url):
    """Accept the normal web URL too and turn it into the raw-file URL.

    Forgejo/Gitea: /owner/repo/src/branch/main/x.json -> /owner/repo/raw/branch/main/x.json
    GitHub:        github.com/o/r/blob/main/x.json    -> raw.githubusercontent.com/o/r/main/x.json
    """
    url = (url or "").strip()
    m = re.match(r"^https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return re.sub(r"/src/(branch|tag|commit)/", r"/raw/\1/", url, count=1)


def validate(data):
    """True when `data` looks like a usable artists.json."""
    return (isinstance(data, dict) and isinstance(data.get("artists"), list)
            and len(data["artists"]) > 0
            and all(isinstance(e, (dict, str)) for e in data["artists"])
            and all(("name" in e) if isinstance(e, dict) else True for e in data["artists"]))


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if validate(data) else None
    except (OSError, ValueError):
        return None


def pick_catalog_file(bundled_path, cache_path):
    """Newest valid local copy: the downloaded cache or the bundled file."""
    candidates = [p for p in (cache_path, bundled_path)
                  if p and os.path.exists(p) and _read_json(p) is not None]
    if not candidates:
        return bundled_path
    return max(candidates, key=os.path.getmtime)


def fetch(url, cache_path, token=None):
    """Download the artist list. Returns (status, message).

    status: "updated" | "unchanged" | "error"
    """
    url = to_raw_url(url)
    meta_path = cache_path + ".meta"
    meta = {}
    try:
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        pass

    headers = {"Accept": "application/json, text/plain, */*"}
    if token:
        headers["Authorization"] = f"token {token}"   # Forgejo/Gitea access token
    if os.path.exists(cache_path) and meta.get("url") == url:
        if meta.get("etag"):
            headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified"):
            headers["If-Modified-Since"] = meta["last_modified"]

    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        return "error", f"no connection ({e.__class__.__name__})"

    if resp.status_code == 304:
        return "unchanged", "not modified"
    if resp.status_code in (401, 403, 404):
        hint = {401: "login required - add an access token",
                403: "no access - check the access token",
                404: "file not found - check the URL / is it pushed?"}[resp.status_code]
        return "error", f"HTTP {resp.status_code}: {hint}"
    if resp.status_code != 200:
        return "error", f"HTTP {resp.status_code}"

    try:
        data = resp.json()
    except ValueError:
        return "error", "the server did not return JSON (wrong URL? a login page?)"
    if not validate(data):
        return "error", "downloaded file is not a valid artist list - kept the old one"

    old = _read_json(cache_path)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp = cache_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, cache_path)   # atomic: never a half-written list
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump({"url": url, "etag": resp.headers.get("ETag", ""),
                   "last_modified": resp.headers.get("Last-Modified", "")}, fh)

    if old == data:
        return "unchanged", "same content"
    return "updated", f"{len(data['artists'])} artists"


def fetch_in_background(url, cache_path, token, callback):
    """Run fetch() in a thread; callback(status, message) is called afterwards
    (from that thread - use a Qt signal to get back to the GUI)."""
    def run():
        try:
            status, message = fetch(url, cache_path, token)
        except Exception as e:  # never crash the app because of the update
            status, message = "error", str(e)
        logging.info(f"Artist list update: {status} ({message})")
        callback(status, message)
    threading.Thread(target=run, daemon=True).start()
