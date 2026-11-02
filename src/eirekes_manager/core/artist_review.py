# src/eirekes_manager/core/artist_review.py
"""
Status of an artist value compared to the artist list (web matcher colours).

  "ok"        exactly as in the list and as on the website
  "corrected" known artist, spelling/notation corrected
  "fuzzy"     typo -> closest artist from the list (check!)
  "unknown"   not in the list
"""

from ..i18n import tr

STATUSES = ("ok", "corrected", "fuzzy", "unknown")


def artist_status(catalog, value):
    """(status, tooltip) for an artist string."""
    suggestion, parts = catalog.suggest(value)
    lines = []
    status = "ok"
    for p in parts:
        if p["status"] == "unknown":
            status = "unknown"
            cands = ", ".join(p["candidates"][:4])
            lines.append(tr("artist_tip_unknown").format(p["input"]) +
                         (f"  {tr('artist_maybe').format(cands)}" if cands else ""))
        elif p["status"] == "fuzzy":
            if status != "unknown":
                status = "fuzzy"
            lines.append(tr("artist_tip_fuzzy").format(p["input"], p["output"]))
    if status == "ok" and suggestion != value:
        status = "corrected"
        lines.append(tr("artist_suggestion").format(suggestion))
    return status, "\n".join(lines)


def web_row_status(catalog, value, web_value):
    """(status, tooltip) for a table cell, compared to the website's value."""
    status, tip = artist_status(catalog, value)
    if status == "ok" and value != web_value:
        # fully known now, but differs from the website -> show what changed
        auto_value, web_parts = catalog.suggest(web_value)
        # a guessed typo stays yellow until you change the cell yourself
        guessed = value == auto_value and any(p["status"] == "fuzzy" for p in web_parts)
        status = "fuzzy" if guessed else "corrected"
        tip = tr("artist_tip_changed").format(web_value)
        for p in web_parts:
            if p["status"] == "fuzzy":
                tip += "\n" + tr("artist_tip_fuzzy").format(p["input"], p["output"])
    return status, tip
