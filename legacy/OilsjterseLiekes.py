import os
import glob
import re
import requests
import music_tag

def extract_and_clean_td_content(url):
    """
    Fetches the content of a webpage, extracts the text within all <td> elements,
    removes HTML tags.
    """
    try:
        response = requests.get(url)
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
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
        return None

def replace_incorrect_chars(text):
    """
    Replaces incorrect character encodings and cleans the text.
    """
    char_map = {
        "&#8217;": "'",
        "&#8220;": '"',
        "&#8221;": '"',
        "&#8211;": "-",
        "&#8212;": "—",
        "&#8230;": "...",
        "&#8216;": "‘",
    }
    corrected_text = re.sub(r'&#(\d+);', lambda m: char_map.get(m.group(0), m.group(0)), text)
    corrected_text = corrected_text.replace("Tekst:", "").replace("Origineel nummer:", "")
    corrected_text = corrected_text.strip()
    corrected_text = '\n'.join([line for line in corrected_text.splitlines() if line.strip() and not line.isspace()])
    lines = corrected_text.splitlines()
    if lines and lines[-1] and lines[-1][0] == " ":
        lines[-1] = lines[-1][1:]
    corrected_text = '\n'.join(lines)
    return corrected_text

def process_string(input_string):
    """
    Processes the input string to create 1D and 2D arrays.
    """
    all_elements = []
    for line in input_string:
        all_elements.extend(line.splitlines())

    array_1d = all_elements[:5]
    array_2d = [[]]

    for element in all_elements[5:]:
        try:
            float(element)
            array_2d.append([element])
        except ValueError:
            if array_2d[-1]:
                if len(array_2d[-1]) < 5:
                    array_2d[-1].append(element)
                else:
                    array_2d.append([element])
            else:
                array_2d[-1].append(element)

    return array_1d, array_2d

import os
import glob
import music_tag  # Import the music-tag library for audio metadata handling

def add_metadata(array_1d, array_2d):
    """
    Adds metadata to music files (MP3 and M4A).
    Renames files to track[0] after processing.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    for i, track in enumerate(array_2d):
        if track and not all(element.isspace() or not element for element in track):
            file_pattern = os.path.join(script_dir, track[0] + ".*")
            file_paths = glob.glob(file_pattern)

            if file_paths:
                file_path = file_paths[0]
                print(f"Processing file {i + 1}: {file_path}")

                try:
                    # Load the audio file using music-tag
                    audio = music_tag.load_file(file_path)
                    print("File loaded successfully.")

                    # Clear existing tags to avoid duplicates (not necessary with music-tag, but updating values directly)
                    # Set metadata tags
                    audio["title"] = track[1]
                    audio["artist"] = track[2]
                    audio["album"] = array_1d[0]
                    audio["genre"] = "Carnaval"
                    audio["year"] = array_1d[2]
                    audio["tracknumber"] = i

                    # Save the metadata to the file
                    audio.save()
                    print(f"Metadata updated successfully for file {i + 1}.")

                    # Rename the file AFTER metadata update
                    temp_file_name = os.path.join(script_dir, i + track[1] + os.path.splitext(file_path)[1])
                    new_file_name = os.path.join(script_dir, str(i) + os.path.splitext(file_path)[1])
                    try:
                        os.rename(file_path, temp_file_name)
                        os.rename(temp_file_name, new_file_name)
                        print(f"File renamed to: {new_file_name}")
                    except OSError as e:
                        print(f"Error renaming file: {e}")

                except Exception as e:
                    print(f"An unexpected error occurred for file {i}: {e}")
            else:
                print(f"Warning: No file found matching pattern {file_pattern}")

# Example usage
url = str(input("Enter a webpage to scan: "))

ugly_data = extract_and_clean_td_content(url)

cleaned_data = []
if ugly_data:
    for content in ugly_data:
        cleaned_content = replace_incorrect_chars(content)
        if cleaned_content:
            cleaned_data.append(cleaned_content)

array_1d, array_2d = process_string(cleaned_data)

add_metadata(array_1d, array_2d)