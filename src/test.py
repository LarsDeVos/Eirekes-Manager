from lyrics_scraper import LyricsScraper

ls = LyricsScraper()
print(ls.get_lyrics_from_track(
    "https://oilsjterseliekes.be/tracks/ik-leef-ver-carnaval/"
))
