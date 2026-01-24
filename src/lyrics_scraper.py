import requests
import re
from bs4 import BeautifulSoup
from unidecode import unidecode
import html

BASE_URL = "https://oilsjterseliekes.be"

class LyricsScraper:
    # =========================================================
    # Get all /tracks/... links from an album page
    # =========================================================
    def get_track_links_from_album(self, album_url):
        try:
            response = requests.get(album_url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            links = []

            # Find ALL links
            for a in soup.find_all("a", href=True):
                href = a["href"]

                # FIX: Check if '/tracks/' is anywhere in the link (not just at the start)
                if "/tracks/" in href:
                    # Handle full URLs (https://...)
                    if href.startswith("http"):
                        full_url = href
                    # Handle relative URLs starting with / (/tracks/...)
                    elif href.startswith("/"):
                        full_url = BASE_URL + href
                    # Handle relative URLs without slash (tracks/...)
                    else:
                        full_url = BASE_URL + "/" + href

                    # Ensure we only keep links for this site
                    if BASE_URL in full_url:
                        if full_url not in links:
                            links.append(full_url)
            
            return links

        except Exception as e:
            print(f"Error extracting links: {e}")
            return []

    # =========================================================
    # Extract lyrics from a single track page
    # =========================================================
    def get_lyrics_from_track(self, track_url):
        try:
            response = requests.get(track_url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Lyrics live here
            body = soup.find("div", class_="tekst")
            if not body:
                return None

            lyrics = body.get_text("\n", strip=True)
            lyrics = lyrics.strip()

            # Reject pages that are too small to be lyrics
            if len(lyrics.splitlines()) < 5:
                return None

            return lyrics
        except:
            return None

    # =========================================================
    # Build {normalized_title: lyrics} map for an album
    # =========================================================
    def get_lyrics_map_from_album(self, album_url):
        track_links = self.get_track_links_from_album(album_url)
        lyrics_map = {}

        # DEBUG: Print how many links were found
        print(f"DEBUG: Found {len(track_links)} track links on page.")

        for url in track_links:
            try:
                # 1. Get Lyrics
                lyrics = self.get_lyrics_from_track(url)
                if not lyrics:
                    continue

                # 2. Get Title from the track page itself to map it correctly
                response = requests.get(url, timeout=15)
                soup = BeautifulSoup(response.text, "html.parser")

                title_tag = soup.find("h1")
                if not title_tag:
                    continue

                # Normalize title so it matches the album tracklist
                title = self.normalize_title(title_tag.get_text())
                lyrics_map[title] = lyrics
                
            except Exception as e:
                print(f"Error processing track {url}: {e}")
                continue

        return lyrics_map

    # =========================================================
    # Helpers
    # =========================================================
    def normalize_title(self, title):
        title = html.unescape(title)     # &#8216; -> '
        title = unidecode(title)         # Vér -> Ver
        title = title.lower()
        title = re.sub(r"[’'\"`]", "", title)
        title = re.sub(r"[^a-z0-9 ]+", " ", title)
        title = re.sub(r"\s+", " ", title)
        return title.strip()