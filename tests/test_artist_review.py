from eirekes_manager.core.artist_review import artist_status, web_row_status


def test_ok(catalog):
    assert artist_status(catalog, "Den Bremt") == ("ok", "")


def test_corrected_spelling(catalog):
    status, tip = artist_status(catalog, "den bremt")
    assert status == "corrected"
    assert "Den Bremt" in tip


def test_fuzzy_and_unknown(catalog):
    assert artist_status(catalog, "Den Brremt")[0] == "fuzzy"
    status, tip = artist_status(catalog, "Den Brremt & Volledig Onbekend")
    assert status == "unknown"
    assert "Volledig Onbekend" in tip


def test_web_row_changed_from_website_is_corrected(catalog):
    status, tip = web_row_status(catalog, "Den Bremt", "den bremt")
    assert status == "corrected"
    assert "den bremt" in tip


def test_web_row_guessed_typo_stays_fuzzy(catalog):
    # the cell holds the automatic guess for a typo -> still needs a check
    assert web_row_status(catalog, "Den Bremt", "Den Brremt")[0] == "fuzzy"


def test_web_row_same_as_website(catalog):
    assert web_row_status(catalog, "Gary", "Gary")[0] == "ok"
