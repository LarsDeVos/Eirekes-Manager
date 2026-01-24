import requests
import re
from bs4 import BeautifulSoup
from unidecode import unidecode
import html
import re

BASE_URL = "https://oilsjterseliekes.be"


class LyricsScraper:
    # =========================================================
    # Get all /tracks/... links from an album page
    # =========================================================
    def get_track_links_from_album(self, album_url):
        response = requests.get(album_url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]

            if href.startswith("/tracks/"):
                full_url = BASE_URL + href
                if full_url not in links:
                    links.append(full_url)

        return links

    # =========================================================
    # Extract lyrics from a single track page
    # =========================================================
    def get_lyrics_from_track(self, track_url):
        response = requests.get(track_url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Lyrics live here (confirmed by you)
        body = soup.find("div", class_="tekst")
        if not body:
            return None

        lyrics = body.get_text("\n", strip=True)
        lyrics = lyrics.strip()

        # Reject pages that are too small to be lyrics
        if len(lyrics.splitlines()) < 5:
            return None

        return lyrics

    # =========================================================
    # Build {normalized_title: lyrics} map for an album
    # =========================================================
    def get_lyrics_map_from_album(self, album_url):
        track_links = self.get_track_links_from_album(album_url)
        lyrics_map = {}

        for url in track_links:
            lyrics = self.get_lyrics_from_track(url)
            if not lyrics:
                continue

            # Fetch title from the track page
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")

            title_tag = soup.find("h1")
            if not title_tag:
                continue

            title = self.normalize_title(title_tag.get_text())
            lyrics_map[title] = lyrics

        return lyrics_map

    # =========================================================
    # Helpers
    # =========================================================
    def normalize_title(self, title):
        title = html.unescape(title)     # &#8216; → '
        title = unidecode(title)         # Vér → Ver
        title = title.lower()
        title = re.sub(r"[’'\"`]", "", title)
        title = re.sub(r"[^a-z0-9 ]+", " ", title)
        title = re.sub(r"\s+", " ", title)
        return title.strip()
