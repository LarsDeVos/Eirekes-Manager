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
        print(f"--- DEBUG: Starting fetch_data for {album_url} ---")
        album_data, tracks = self.fetch_album_metadata(album_url)

        if not tracks:
            print("--- DEBUG: No tracks found in metadata ---")
            return album_data, tracks

        # Fetch track URLs/Lyrics map
        try:
            lyrics_map = self.lyrics_scraper.get_lyrics_map_from_album(album_url)
        except Exception as e:
            print(f"DEBUG: Error fetching lyrics map: {e}")
            lyrics_map = {}

        for track in tracks:
            comment = ""
            
            # Iterate backwards to find the special tag
            for i in range(len(track) - 1, -1, -1):
                if "||ORIGINAL||" in track[i]:
                    # FIX: Split the string instead of replacing/popping blindly.
                    # This handles cases where Artist and Tag are on the same line.
                    # e.g. "Artist Name ||ORIGINAL|| Song Name"
                    parts = track[i].split("||ORIGINAL||")
                    
                    # Everything AFTER the tag is the comment
                    if len(parts) > 1:
                        comment = parts[1].strip()
                    
                    # Everything BEFORE the tag is kept (e.g. the Artist)
                    pre_content = parts[0].strip()
                    
                    if pre_content:
                        # Update the list element to just the pre-content
                        track[i] = pre_content
                        # If the comment was empty in the split (e.g. tag at end of line), 
                        # check the NEXT element in the list
                        if not comment and i + 1 < len(track):
                            comment = track[i+1].strip()
                            track.pop(i+1)
                    else:
                        # If nothing before the tag, remove the whole element
                        track.pop(i)
                        # If comment still empty, check next element
                        if not comment and i < len(track):
                            comment = track[i].strip()
                            track.pop(i)
                            
                    break
            
            # --- Normalize & Match Lyrics ---
            if len(track) > 1:
                original_title = track[1]
                track_title = self.lyrics_scraper.normalize_title(original_title)
                lyrics = lyrics_map.get(track_title, "")
            else:
                lyrics = ""

            # --- Force Structure: [Num, Title, Artist, Lyrics, Comment] ---
            # 1. Ensure we have at least 3 elements (Num, Title, Artist)
            track[:] = track[:3]
            while len(track) < 3:
                track.append("")
            
            # 2. Add Lyrics and Comment
            track.append(lyrics)
            track.append(comment)

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
                
                # FIX: 
                # 1. Replace block tags (<br>, <p>, <div>) with NEWLINE to force splitting
                td_content = re.sub(r'<(br|p|div)[^>]*>', '\n', td_content, flags=re.IGNORECASE)
                # 2. Replace inline tags (<strong>, <span>) with SPACE to keep "Label: Value" together
                td_content = re.sub(r'<[^>]+>', ' ', td_content)
                
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
            "&#8216;": "'",
            "&nbsp;": " " 
        }

        corrected = re.sub(
            r'&#(\d+);',
            lambda m: char_map.get(m.group(0), m.group(0)),
            text
        )
        
        corrected = corrected.replace("&nbsp;", " ")
        corrected = corrected.replace("Tekst:", "")
        
        # Tag insertion - Handle variations in spacing
        if "Origineel nummer:" in corrected:
            corrected = corrected.replace("Origineel nummer:", "||ORIGINAL||")
        elif "Origineel nummer :" in corrected:
            corrected = corrected.replace("Origineel nummer :", "||ORIGINAL||")
        
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

        # Year Validation
        if len(array_1d) > 2:
            year_val = array_1d[2].strip()
            if not re.match(r'^\d{4}$', year_val):
                array_1d[2] = "" 

        array_2d = [[]]

        for element in all_elements[5:]:
            element = element.strip()
            if not element: continue

            try:
                # If it's a number, it's likely a new track index
                float(element) 
                array_2d.append([element])
            except ValueError:
                if array_2d[-1]:
                    array_2d[-1].append(element)
                else:
                    array_2d[-1].append(element)

        # Remove incomplete rows
        array_2d = [track for track in array_2d if len(track) > 1]

        return array_1d, array_2d