# src/eirekes_manager/scraping/lyrics_scraper.py
"""Lyrics from the track pages of oilsjterseliekes.be."""

import html
import logging
import re

import requests
from bs4 import BeautifulSoup
from unidecode import unidecode

BASE_URL = "https://oilsjterseliekes.be"
MIN_LYRICS_LINES = 5


def normalize_title(title):
    """Title key to match tracks with their lyrics page."""
    title = html.unescape(title)     # &#8216; -> '
    title = unidecode(title)         # Vér -> Ver
    title = title.lower()
    title = re.sub(r"[’'\"`]", "", title)
    title = re.sub(r"[^a-z0-9 ]+", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def parse_track_links(html_content):
    """All /tracks/... links of this site in an album page (no duplicates)."""
    soup = BeautifulSoup(html_content, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/tracks/" not in href:
            continue
        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = BASE_URL + href
        else:
            full_url = BASE_URL + "/" + href
        # Ensure we only keep links for this site
        if BASE_URL in full_url and full_url not in links:
            links.append(full_url)
    return links


def parse_lyrics(html_content):
    """(lyrics or None, soup) from a track page; short texts are not lyrics."""
    soup = BeautifulSoup(html_content, "html.parser")
    body = soup.find("div", class_="tekst")
    if not body:
        return None, soup
    lyrics = body.get_text("\n", strip=True).strip()
    if len(lyrics.splitlines()) < MIN_LYRICS_LINES:
        return None, soup
    return lyrics, soup


class LyricsScraper:
    normalize_title = staticmethod(normalize_title)

    def get_track_links_from_album(self, album_url):
        try:
            response = requests.get(album_url, timeout=15)
            response.raise_for_status()
            return parse_track_links(response.text)
        except Exception as e:
            logging.warning(f"Error extracting links: {e}")
            return []

    def get_lyrics_from_track(self, track_url):
        """Returns (lyrics, soup) so the caller can reuse the parsed page."""
        try:
            response = requests.get(track_url, timeout=15)
            response.raise_for_status()
            return parse_lyrics(response.text)
        except Exception:
            return None, None

    def get_lyrics_map_from_album(self, album_url):
        """{normalized_title: lyrics} for an album."""
        lyrics_map = {}
        for url in self.get_track_links_from_album(album_url):
            try:
                lyrics, soup = self.get_lyrics_from_track(url)
                if not lyrics or soup is None:
                    continue
                title_tag = soup.find("h1")
                if not title_tag:
                    continue
                lyrics_map[normalize_title(title_tag.get_text())] = lyrics
            except Exception as e:
                logging.warning(f"Error processing track {url}: {e}")
        return lyrics_map
