# src/app_translations.py

CURRENT_LANG = "en"

TRANSLATIONS = {
    "en": {
        "app_title": "Muziek Metadata Master",
        "web_matcher": "Oilsjterseliekes",
        "import_csv": "Importeer CSV",
        "matches_hint": "Veranderingen zijn gekoleird in CYAAN. Ctrl+S om op te slaan.",
        "local_files": "Lokale Bestanden",
        "open_folder": "Open Map",
        "metadata_editor": "Metadata Editor",
        "no_art": "Giejne Cover",
        "choose_art": "Kies Cover",
        "save_all": "Alles Opslaan (Ctrl+S)",
        "save_success": "Succesvol {} bestanden verwerkt!",
        "save_error": "Fouten bij {} bestanden.",
        "staged_count": "{} bestanden klaargezet. Druk Ctrl+S.",
        "no_changes": "Geen wijzigingen om op te slaan.",
        "processing_error": "Faat boi 't verweirken {}: {}",
        "renamed_log": "Hernoemd naar {}",
        "lyrics_log": "Lyrics bestand aangemaakt: {}",
        "saved_log": "Metadata opgeslagen voor {}",
        "please_load": "Laad eerst een map met muziekbestanden.",
        "multiple_selected": "Meerdere Geselecteerd",
        "matcher_title": "Web Data Matcher & Editor",
        "fetch_group": "1. Web Data Ophalen",
        "url_placeholder": "Plak Album URL hier...",
        "fetch_btn": "Ophalen",
        "options_group": "Opties",
        "chk_title": "Titel",
        "chk_artist": "Artiest",
        "chk_track": "Track #",
        "chk_rename": "Bestand Hernoemen",
        "chk_lyrics": "Lyrics Opslaan (.lrc)",
        "align_group": "2. Data Uitlijnen & Bewerken",
        "your_files": "JOUW BESTANDEN (Sleep om te ordenen):",
        "web_tracks": "WEB TRACKS (Bewerkbaar):",
        "apply_btn": "✅ Veranderingen Toepassen",
        "cancel_btn": "Annuleren",
        "fetching_wait": "Ophalen... ressekes geduld",
        "unknown_album": "Onbekend Album",
        "csv_title": "CSV Data Matcher",
        "load_group": "1. Data Laden",
        "no_csv": "Geen CSV geloin",
        "select_csv": "📂 Selecteer CSV",
        "align_files_group": "2. Bestanden Uitlijnen",
        "remove_file": "🗑️ Verwijder Bestand",
        "csv_rows": "CSV RIJEN:",
        "remove_row": "🗑️ Verwijder Rij",
        "link_pair": "🔗 Koppel Paar",
        "apply_all": "✅ Alles Toepassen",
        "close_btn": "Sluiten",
        "csv_warning": "Waarschuwing",
        "csv_error": "Faat",
        "csv_select_pair": "Selecteer 1 Bestand (Links) en 1 Rij (Rechts).",
        "csv_guess_warning": "Kon kolommen niet identificeren. Standaard gok gebruikt.",
        "lbl_title": "Titel",
        "lbl_artist": "Artiest",
        "lbl_album": "Album",
        "lbl_year": "Joor",
        "lbl_tracknumber": "Track",
        "lbl_genre": "Genre",
        "lbl_albumartist": "Album Artiest",
        "lbl_composer": "Componist",
        "lbl_discnumber": "Discnummer",
        "lbl_comment": "Commentaar"
    }
}

def set_language(lang_code):
    global CURRENT_LANG
    if lang_code in TRANSLATIONS:
        CURRENT_LANG = lang_code

def get_current_language():
    return CURRENT_LANG

def tr(key):
    return TRANSLATIONS.get(CURRENT_LANG, {}).get(key, key)