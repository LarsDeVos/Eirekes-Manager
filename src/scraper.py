import requests
import re
from lyrics_scraper import LyricsScraper

class AlbumScraper:
    def __init__(self):
        self.lyrics_scraper = LyricsScraper()

    # =========================================================
    # PUBLIC ENTRY POINT
    # =========================================================
    def fetch_data(self, album_url):
        album_data, tracks = self.fetch_album_metadata(album_url)

        if not tracks:
            return album_data, tracks

        # --- DEBUG LOGGING START ---
        print(f"\n--- DEBUG: Fetching lyrics for {album_url} ---")
        try:
            lyrics_map = self.lyrics_scraper.get_lyrics_map_from_album(album_url)
            print(f"DEBUG: Lyrics map size: {len(lyrics_map)}")
            if len(lyrics_map) > 0:
                print(f"DEBUG: First 5 keys in map: {list(lyrics_map.keys())[:5]}")
            else:
                print("DEBUG: Lyrics map is EMPTY. This means lyrics_scraper.py found no links.")
        except Exception as e:
            print(f"DEBUG: Error fetching lyrics map: {e}")
            lyrics_map = {}
        # --- DEBUG LOGGING END ---

        for track in tracks:
            # Force structure (Track #, Title, Artist, Lyrics)
            track[:] = track[:3]
            while len(track) < 4:
                track.append("")

            if len(track) > 1:
                original_title = track[1]
                # Normalize using the SAME function as the lyrics scraper
                track_title = self.lyrics_scraper.normalize_title(original_title)
                
                lyrics = lyrics_map.get(track_title, "")
                track[3] = lyrics

                # --- DEBUG MATCHING ---
                status = "FOUND" if lyrics else "MISSING"
                # Only print missing ones to reduce noise, or all for thoroughness
                print(f"DEBUG: Track '{original_title}' -> Norm: '{track_title}' | Status: {status}")
            else:
                track[3] = ""

        return album_data, tracks

    # =========================================================
    # ALBUM METADATA
    # =========================================================
    def fetch_album_metadata(self, url):
        raw_data = self.extract_and_clean_td_content(url)
        if not raw_data:
            return [], []

        cleaned_data = []
        for content in raw_data:
            cleaned = self.replace_incorrect_chars(content)
            if cleaned:
                cleaned_data.append(cleaned)

        return self.process_string(cleaned_data)

    # =========================================================
    # HTML SCRAPING
    # =========================================================
    def extract_and_clean_td_content(self, url):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            html_content = response.text

            cleaned_content = []
            start_index = 0

            while True:
                start_index = html_content.find("<td", start_index)
                if start_index == -1:
                    break

                end_index = html_content.find("</td>", start_index)
                if end_index == -1:
                    break

                td_content = html_content[start_index:end_index + 5]
                td_content = re.sub('<[^>]+>', '\n', td_content)
                cleaned_content.append(td_content.strip())

                start_index = end_index + 5

            return cleaned_content

        except Exception as e:
            print(f"Scrape Error: {e}")
            return None

    # =========================================================
    # TEXT CLEANUP
    # =========================================================
    def replace_incorrect_chars(self, text):
        char_map = {
            "&#8217;": "'",
            "&#8220;": '"',
            "&#8221;": '"',
            "&#8211;": "-",
            "&#8212;": "—",
            "&#8230;": "...",
            # Added common missing entity if needed
            "&#8216;": "'", 
        }

        corrected = re.sub(
            r'&#(\d+);',
            lambda m: char_map.get(m.group(0), m.group(0)),
            text
        )

        corrected = corrected.replace("Tekst:", "")
        corrected = corrected.replace("Origineel nummer:", "")
        corrected = corrected.strip()

        lines = [line for line in corrected.splitlines() if line.strip()]

        if lines and lines[-1].startswith(" "):
            lines[-1] = lines[-1][1:]

        return '\n'.join(lines)

    # =========================================================
    # DATA STRUCTURING
    # =========================================================
    def process_string(self, input_string):
        all_elements = []
        for line in input_string:
            all_elements.extend(line.splitlines())

        if len(all_elements) < 5:
            return [], []

        array_1d = all_elements[:5]

        # --- FIX: YEAR VALIDATION ---
        # If the year is not a valid 4-digit number (e.g. "Unknown Year"), clear it.
        # This prevents the "Could not extract year" crash in music_tag.
        if len(array_1d) > 2:
            year_val = array_1d[2].strip()
            # Simple check: must be 4 digits
            if not re.match(r'^\d{4}$', year_val):
                print(f"DEBUG: Invalid year detected '{year_val}'. Clearing to prevent crash.")
                array_1d[2] = "" 

        array_2d = [[]]

        for element in all_elements[5:]:
            try:
                float(element)  # track number
                array_2d.append([element])
            except ValueError:
                if array_2d[-1]:
                    if len(array_2d[-1]) < 5:
                        array_2d[-1].append(element)
                    else:
                        array_2d.append([element])
                else:
                    array_2d[-1].append(element)

        # Remove incomplete rows
        array_2d = [track for track in array_2d if len(track) > 1]

        return array_1d, array_2d