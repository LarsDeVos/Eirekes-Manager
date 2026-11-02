# src/eirekes_manager/scraping/album_scraper.py
"""
Album page of oilsjterseliekes.be -> album info + track list.

The parsing functions work on HTML text (no network), AlbumScraper does the
downloading. A track is returned as [Num, Title, Artist, Lyrics, Comment].
"""

import logging
import re

import requests

from .lyrics_scraper import LyricsScraper, normalize_title

ORIGINAL_TAG = "||ORIGINAL||"

CHAR_MAP = {
    "&#8217;": "'",
    "&#8220;": '"',
    "&#8221;": '"',
    "&#8211;": "-",
    "&#8212;": "—",
    "&#8230;": "...",
    "&#8216;": "'",
}


# =========================================================
# HTML SCRAPING
# =========================================================
def extract_td_content(html_content):
    """Text of every <td> in the page (block tags become new lines)."""
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
        # 1. Replace block tags (<br>, <p>, <div>) with NEWLINE to force splitting
        td_content = re.sub(r'<(br|p|div)[^>]*>', '\n', td_content, flags=re.IGNORECASE)
        # 2. Replace inline tags (<strong>, <span>) with SPACE to keep "Label: Value" together
        td_content = re.sub(r'<[^>]+>', ' ', td_content)
        cleaned_content.append(td_content.strip())

        start_index = end_index + 5
    return cleaned_content


# =========================================================
# TEXT CLEANUP
# =========================================================
def replace_incorrect_chars(text):
    """Fix HTML entities, drop labels and mark "Origineel nummer:" with ORIGINAL_TAG."""
    corrected = re.sub(r'&#(\d+);', lambda m: CHAR_MAP.get(m.group(0), m.group(0)), text)
    corrected = corrected.replace("&nbsp;", " ")
    corrected = corrected.replace("Tekst:", "")

    # Tag insertion - Handle variations in spacing
    if "Origineel nummer:" in corrected:
        corrected = corrected.replace("Origineel nummer:", ORIGINAL_TAG)
    elif "Origineel nummer :" in corrected:
        corrected = corrected.replace("Origineel nummer :", ORIGINAL_TAG)

    corrected = corrected.strip()
    lines = [line for line in corrected.splitlines() if line.strip()]
    if lines and lines[-1].startswith(" "):
        lines[-1] = lines[-1][1:]
    return '\n'.join(lines)


# =========================================================
# DATA STRUCTURING
# =========================================================
def process_string(input_string):
    """Cell texts -> (album info [5 lines], tracks [[num, ...], ...])."""
    all_elements = []
    for line in input_string:
        all_elements.extend(line.splitlines())

    if len(all_elements) < 5:
        return [], []

    array_1d = all_elements[:5]

    # Year Validation
    year_val = array_1d[2].strip()
    if not re.match(r'^\d{4}$', year_val):
        array_1d[2] = ""

    array_2d = [[]]
    for element in all_elements[5:]:
        element = element.strip()
        if not element:
            continue
        try:
            # If it's a number, it's likely a new track index
            float(element)
            array_2d.append([element])
        except ValueError:
            array_2d[-1].append(element)

    # Remove incomplete rows
    array_2d = [track for track in array_2d if len(track) > 1]
    return array_1d, array_2d


def parse_album_html(html_content):
    """(album info, tracks) from an album page."""
    cleaned_data = []
    for content in extract_td_content(html_content):
        cleaned = replace_incorrect_chars(content)
        if cleaned:
            cleaned_data.append(cleaned)
    return process_string(cleaned_data)


def split_original_comment(track):
    """Take "Origineel nummer: ..." out of a track (in place); return the comment.

    Handles "Artist ||ORIGINAL|| Song" on one line and the tag on its own line
    with the song on the next line.
    """
    comment = ""
    # Iterate backwards to find the special tag
    for i in range(len(track) - 1, -1, -1):
        if ORIGINAL_TAG in track[i]:
            parts = track[i].split(ORIGINAL_TAG)
            # Everything AFTER the tag is the comment
            if len(parts) > 1:
                comment = parts[1].strip()
            # Everything BEFORE the tag is kept (e.g. the Artist)
            pre_content = parts[0].strip()

            if pre_content:
                track[i] = pre_content
                # tag at the end of the line: the comment is the NEXT element
                if not comment and i + 1 < len(track):
                    comment = track[i + 1].strip()
                    track.pop(i + 1)
            else:
                # nothing before the tag: remove the whole element
                track.pop(i)
                if not comment and i < len(track):
                    comment = track[i].strip()
                    track.pop(i)
            break
    return comment


def finalize_track(track, lyrics_map):
    """Force [Num, Title, Artist, Lyrics, Comment] (in place)."""
    comment = split_original_comment(track)
    lyrics = lyrics_map.get(normalize_title(track[1]), "") if len(track) > 1 else ""
    track[:] = track[:3]
    while len(track) < 3:
        track.append("")
    track.append(lyrics)
    track.append(comment)
    return track


class AlbumScraper:
    def __init__(self):
        self.lyrics_scraper = LyricsScraper()

    def fetch_data(self, album_url):
        """(album info, tracks) for an album URL; ([], []) when it fails."""
        album_data, tracks = self.fetch_album_metadata(album_url)
        if not tracks:
            return album_data, tracks

        try:
            lyrics_map = self.lyrics_scraper.get_lyrics_map_from_album(album_url)
        except Exception as e:
            logging.warning(f"Error fetching lyrics map: {e}")
            lyrics_map = {}

        for track in tracks:
            finalize_track(track, lyrics_map)
        return album_data, tracks

    def fetch_album_metadata(self, url):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
        except Exception as e:
            logging.warning(f"Scrape Error: {e}")
            return [], []
        return parse_album_html(response.text)
