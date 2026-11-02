# Eirekes Manager

Muziekbestanden van carnaval taggen (Oilsjterse Liekes): tracklijsten ophalen
van oilsjterseliekes.be of uit een CSV, artiestennamen opkuisen, tags /
albumhoes / songteksten wegschrijven en de bestanden hernoemen.

## Starten

```bash
pip install -r requirements.txt
cd src && python main.py
```

## Opbouw van het project

```
src/
  main.py                 startpunt (ook gebruikt door main.spec / PyInstaller)
  artists.json            meegeleverde artiestenlijst (de online update downloadt dit bestand - niet verplaatsen)
  eirekes_manager/
    core/                 pure Python-logica, zonder Qt - getest in tests/
      artist_catalog.py   artiestenlijst, schrijfwijze gelijktrekken, suggesties
      artist_review.py    status ok / verbeterd / twijfel / onbekend voor de web-matcher
      artist_sync.py      een nieuwere artists.json downloaden
      csv_import.py       een "stoet"-CSV inlezen
      filenames.py        "03 - Artiest - Titel.mp3"
      metadata.py         welke velden de editor toont, tags uitlezen
      release_type.py     RELEASETYPE-tag (Album / Single / EP ...)
      staging.py          gekoppelde rijen -> wijzigingen per bestand
      tag_values.py       waarden controleren / opkuisen, kapotte tags lezen
      tag_writer.py       tags, albumhoes, hernoemen en songteksten opslaan
    scraping/             album + songteksten van oilsjterseliekes.be (inlezen los van downloaden)
    ui/                   PyQt6-vensters en -widgets
    i18n.py               vertalingen
    paths.py              meegeleverde bestanden, logmap
tests/                    pytest-tests (+ kleine stille audiobestanden in tests/fixtures)
legacy/                   het oorspronkelijke losse script, niet gebruikt door de app
```

Vuistregel: logica hoort in `core/` (te testen zonder scherm), `ui/` toont
alleen en roept `core/` aan.

## Testen

```bash
pip install -r requirements-dev.txt
python -m pytest
```

De tests werken op echte mp3- / m4a- / flac- / wav-bestanden (gekopieerd naar
een tijdelijke map), zodat het wegschrijven van tags voor elk formaat
gecontroleerd wordt. De UI-tests draaien zonder scherm en gebruiken hun eigen
instellingenbestand, dus je eigen app-instellingen worden nooit aangeraakt.
`tests/test_artists_json.py` controleert `src/artists.json` - voer die uit
nadat je de lijst aangepast hebt (dubbele namen / aliassen, onbekende tags, ...).

## De app bouwen

```bash
python build.py --install
```

Dit installeert wat nodig is om te bouwen, voert de tests uit, bouwt de app
met PyInstaller en zet het resultaat als zip in `src/dist/` (een `.app` op
macOS, een map met `Eirekes-Manager.exe` op Windows, een map met
`Eirekes-Manager` op Linux). Na de eerste keer mag `--install` weg; met
`--skip-tests` gaat het sneller.

PyInstaller bouwt alleen voor het besturingssysteem waarop het draait: bouw de
Windows-versie op een Windows-pc en de Linux-versie op Linux.

## Artiestenlijst bijwerken vanuit een Plex-export

```bash
cd src && python -m eirekes_manager.core.artist_catalog <plex-export.csv>
```
