# src/artist_catalog.py
"""
Artist catalog: one canonical spelling per artist.

- `normalize_key()` makes a spelling-insensitive key (case, accents,
  apostrophes, spaces, leading "De"/"Den" are ignored).
- `ALIASES` maps real spelling variants/typos to one canonical name.
- `ArtistCatalog` holds the known artists (bundled artists.json + the
  artists you add yourself) and can normalize a full artist string like
  "den bremt & gary ft. jos" -> "Den Bremt & Gary feat. Jos".

artists.json is the curated list (one artist per line, edit freely):
  {"name": "Possensje", "tags": ["akv"]}
Tags: "akv" = Aalsterse Karnavalvereniging. Names in "ignored" are never
offered or re-imported. Merge a new Plex export into it with
`python artist_catalog.py <plex-export.csv>` (keeps tags and ignored names);
the app can also import an export via the menu (Artists > Import from Plex CSV).
"""

import csv
import difflib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

# --------------------------------------------------------------------------
# Canonical name -> spelling variants that should map onto it.
# Variants are matched with normalize_key(), so case / accents / apostrophes /
# spaces / a leading "De"/"Den" never need to be listed separately.
# --------------------------------------------------------------------------
ALIASES = {
    "'t Es Om Zjiep": ["'t Es Om Zeep"],
    "'t Es Noig": ["t'es nodig"],
    "2 DJ's Van De Mert": ["De DJ's van de Mert"],
    "Andy Boeykens": ["Andy Boeykes"],
    "Prinsencaemere": ["Prinsecaemere", "Prinsencaenere", "Prinsenceamere"],
    "Bart Neirinckx": ["Bart Neirincks", "Bart Nerinckx"],
    "Porteplumboys": ["Porteplum", "Porteplumbos", "Porteplum Boys"],
    "Beschomt Ladies": ["Beschomtleediezz"],
    "Bonnaeres": ["Bonares"],
    "Kris I": ["Kris 1", "Kris One"],
    "Kris II": ["KrisII", "Kris 2"],
    "Chris II": ["Chris 2"],
    "Christophe": ["Christoph"],
    "Den Biejnaver": ["Den Bienaver", "Pascal Brewée"],
    "Den Board": ["Den Boord"],
    "Den Bremt": ["Den Bemt", "Den Brempt", "Den Bremp"],
    "Picqueur": ["Picqeur", "Picquer", "Piqcueur", "Piquer"],
    "Michel Picqueur": ["Michel Picquer", "Michel Piqueur"],
    "De Sjattrellen": ["Sjatrellen"],
    "De Steijnzoel'n": ["Steinjzoeln", "Steynzoeln", "Stijnzoeln"],
    "De Toerenbiejoekes": ["Toerenbijoekes"],
    "De Zwiejtzoel'n": ["Zwietjzoeln"],
    "De Zwiejtollekes": ["Zwietjollekes"],
    "De Schoitkitten": ["Schoitkitn"],
    "De Scha Meikes": ["Schaa Meikes", "Ska Meekes"],
    "De Salongcarnavalisten": ["Saloncarnavalisten"],
    "De Prinsengarde": ["Prinsjengarde"],
    "De Tsjoepeneizen": ["Tjoepeneizen"],
    "De Zieke Zjieratten - Twiekierenniet": ["Zieke Zjieratten Twiekierenniet"],
    "Gary": ["Garry"],
    "Mil Arys": ["Mil Arijs", "De Mil"],
    "Enrico Lecleir": ["Enciro Lecleir"],
    "Garçons Debilles": ["Garcon Debilles", "Gracons Debilles"],
    "Guy Walgraef": ["Guy Walraef"],
    "Hendrik Daelman": ["Hendrik Daeleman", "Henri Daelman"],
    "Hiette Gerrekes": ["Hiete Gerrekes"],
    "Inge Rydant": ["Inge Reydant"],
    "Baloe": ["Balou"],
    "Johny": ["Johnny"],
    "Johny Cooman": ["Johnny Cooman", "Jonhy Cooman"],
    "Johny Marcoen": ["Johnny Marcoen"],
    "Koizer Kamiel": ["Keizer Kamiel"],
    "Kjell": ["Kjel"],
    "Konterverkiert": ["KTVK"],
    "Krauker": ["Kroaker", "Koen De Krauker"],
    "Lossendeirdeveirdeirdeir": ["LDVD", "Lossendeirdeveirdeirdeir Ldvd"],
    "Michelleken": ["Michellen", "Mcihelleken", "Michellken"],
    "Minder Es Miër": ["Minder Es Miejr"],
    "Nicole Schellinck": ["Nicole Schellink", "Nicolle Schellinck"],
    "Noeit Ni Genoeg": ["Noeit Nie Genoeg"],
    "Onzjier Zèn Préférés": ["Onzjier Zen Preferees"],
    "De Salami": ["Pascal Soleme", "Pascal Salome", "Pascal Solomé"],
    "Ronny": ["Rony"],
    "Robert": ["Robbert"],
    "Schie'dj Oit": ["Schied'dj Oit"],
    "Schiefregt'oever": ["Schiefrecht'oever", "Schiefrechtoever"],
    "Tommeken": ["Tommeke"],
    "Wim Delclef": ["Wiim", "Wm"],
    "Antoine": ["Anoine", "Anotoine", "Antoin"],
    "Droiloeizen": ["Droileizen", "Droiloezen"],
    "Jean-Paul": ["Jean Paul"],
    "Prins Joeri": ["Prins Joerie"],
    "TTO De Mans": ["TTO Mans"],
    "Yordi Peirlinck": [],
    "Geloeif Mé Goed": ["GMG"],
    "De Fleksies": ["De Fleskies"],
    "Bart De Nijs": ["Bart De Nys", "Bart DN", "B. De Nijs"],
    "Frank & Patrick": ["Frank Patrick"],
    "Schiefregt’Oever": ["SRO"],
    "De Zieke Zjieratten 2x0": ["De Zieke", "De Zieke Zjieratten - Twiekierenniet", "De Zieke Zjieratten"],
    "Lekken & Plekken": ["LEP"]
}

# Names that contain "&" / "en" but are ONE artist (must not be split).
# (regex on the raw string, canonical display name)
PROTECTED = [
    (r"beplekt\s*(?:&|\ben\b)\s*bespoeten", "Beplekt En Bespoeten"),
    (r"lekken\s*(?:&|\ben\b)\s*plekken", "Lekken & Plekken"),
    (r"\bom\s*(?:&|\ben\b)\s*vedrom", "Om En Vedrom"),
    (r"oepen\s*(?:&|\ben\b)\s*toepen", "Oepen & Toepen"),
    (r"\bdom\s*(?:&|\ben\b)\s*domper", "Dom & Domper"),
    (r"noig\s*g\W*\s*ambeteird\s*(?:&|\ben\b)\s*vrie?j?t\s*gezjeneird",
     "Noig G'ambeteird & Vriejt Gezjeneird"),
    (r"tiejn\s*(?:&|\ben\b)\s*tander", "Tiejn En Tander"),
    (r"daven\s*(?:&|\ben\b)\s*trekken", "Daven En Trekken"),
    (r"verdwoldj\s*(?:&|\ben\b)\s*verloeren", "Verdwoldj En Verloeren"),
    (r"keizer\s*kamiel\s*(?:&|\ben\b)\s*de\s*kamillekes", "Keizer Kamiel En De Kamillekes"),
    (r"sompi\s*(?:&|\ben\b)\s*the\s*(?:leediezz+|ladies)", "Sompi & The Leediezzz"),
    (r"bargamezz\s*(?:&|\ben\b)\s*fiesta\s*alosta", "Bargamezz & Fiesta Alosta"),
    (r"lal-,\s*lol-\s*&\s*papsmurf[^,&]*", "Lal-, Lol- & Papsmurf Met PP Smurfen"),
]

# Values that are not artists at all.
EXCLUDED_KEYS = {"", "co", "bonustrack", "thebonustrack", "vlaamseversie", "akv",
                 "ladies", "kids", "kleine", "vrienden", "junior"}

LEAD_SEP = re.compile(r"\s*(?:,|;|&|\+|\s\ben\b\s|\s\band\b\s)\s*", re.IGNORECASE)
FEAT_SEP = re.compile(r"\s+(?:ft\.?|feat\.?|featuring)\s+", re.IGNORECASE)
YEAR_SUFFIX = re.compile(r"\s+(?:19|20)\d{2}$")
KEEP_YEAR = re.compile(r"v[eéèê]r\b|orend|arend|prins", re.IGNORECASE)


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def normalize_key(name):
    """Spelling-insensitive key, e.g. 'De Steijnzoel’n' == 'steijnzoeln'
    and 'Geloeif Mé Goed' == 'geloeif me goed'."""
    s = strip_accents(name or "").lower().replace("’", "'").strip()
    s = re.sub(r"^(?:den|de|d')\s*(?=\w)", "", s)  # leading article
    return re.sub(r"[^0-9a-z]", "", s)


def _smart_title(name):
    """Title-case an all-lowercase name without breaking "'t" / "d'"."""
    if name != name.lower():
        if name[:1].islower() and not name.startswith(("d'", "d’")):
            return name[0].upper() + name[1:]
        return name
    out = []
    for w in name.split(" "):
        if not w or w.startswith("'") or w in ("&",):
            out.append(w)
        elif w.startswith("d'") and len(w) > 2:
            out.append("d'" + w[2:3].upper() + w[3:])
        else:
            out.append(w[0].upper() + w[1:])
    return " ".join(out)


_ALIAS_INDEX = {}
for _canon, _variants in ALIASES.items():
    _ALIAS_INDEX[normalize_key(_canon)] = _canon
    for _v in _variants:
        _ALIAS_INDEX[normalize_key(_v)] = _canon


def clean_segment(seg):
    """Clean ONE artist name (no separators)."""
    s = (seg or "").replace("’", "'").replace("‘", "'")
    s = re.sub(r"\s+", " ", s).strip(" .-")
    s = re.sub(r"^(?:AKV|en)\s+(?=\S)", "", s, flags=re.IGNORECASE)
    if s.endswith(")") and "(" not in s:
        s = s[:-1].strip()
    if YEAR_SUFFIX.search(s) and not KEEP_YEAR.search(s):
        s = YEAR_SUFFIX.sub("", s).strip()
    return s


def split_artists(value):
    """Split a raw artist string into (lead_artists, featured_artists)."""
    if not value:
        return [], []
    s = value.replace("’", "'")
    # whole-string alias that is itself a duo, e.g. "Frank Patrick" / "LEP"
    whole_key = normalize_key(s)
    if whole_key in _ALIAS_INDEX and "&" in _ALIAS_INDEX[whole_key]:
        s = _ALIAS_INDEX[whole_key]
    placeholders = {}
    for i, (pattern, canon) in enumerate(PROTECTED):
        token = f"__P{i}__"
        if re.search(pattern, s, re.IGNORECASE):
            s = re.sub(pattern, token, s, flags=re.IGNORECASE)
            placeholders[token] = canon


    parts = FEAT_SEP.split(s, maxsplit=1)
    lead_raw = parts[0]
    feat_raw = parts[1] if len(parts) > 1 else ""

    def _split(chunk):
        result = []
        for seg in LEAD_SEP.split(chunk):
            for tok, canon in placeholders.items():
                seg = seg.replace(tok, canon)
            seg = clean_segment(seg)
            if normalize_key(seg) in EXCLUDED_KEYS:
                continue
            result.append(seg)
        return result

    return _split(lead_raw), (_split(feat_raw) if feat_raw else [])


TAG_AKV = "akv"     # Aalsterse Karnavalvereniging
TAG_PRINS = "prins"            # (ex-)Prins Carnaval van Aalst
TAG_ARENDPRINS = "arendprins"  # (ex-)Prins van 't Orend (Arendcarnaval)

# Fields an artist entry in artists.json may have (in this order when saving)
ENTRY_FIELDS = ("name", "tags", "aliases", "prins", "prinsennaam",
                "arendprins", "arendprinsennaam")
INFO_FIELDS = ENTRY_FIELDS[3:]


class ArtistCatalog:
    """Known artists + tags + normalisation. Pure Python (no Qt).

    artists.json format:
      {"artists": [{"name": "Possensje", "tags": ["akv"]},
                   {"name": "Jean-Pierre Timmermans", "tags": ["prins"],
                    "aliases": ["Jempi", "Jempi Timmermans"],
                    "prins": [1982], "prinsennaam": "Jempi"},
                   {"name": "Peter Van Nuffel", "tags": ["arendprins", "prins"],
                    "aliases": ["Den Board"], "prins": [2013],
                    "arendprins": [1998], "arendprinsennaam": "Den Board"}, ...],
       "ignored": ["LEP", ...]}          # names never offered / imported
    "aliases" are other names for the same artist: they are converted to
    "name". Rename "name" (e.g. to the prinsennaam) and keep the old name in
    "aliases" - everything keeps working.
    The user file (artists_user.json) has the same format plus
      "tag_overrides": {"Name": ["akv"]} # tags changed in the app
    """

    def __init__(self, bundled_path=None, user_path=None):
        self.reload(bundled_path, user_path)

    def reload(self, bundled_path=None, user_path=None):
        """(Re)load everything in place - widgets keep their reference to
        this object, so they see a downloaded update immediately."""
        bundled_path = bundled_path or getattr(self, "bundled_path", None)
        user_path = user_path or getattr(self, "user_path", None)
        self.bundled_path = bundled_path
        self.user_path = user_path
        self.by_key = {}         # key -> canonical name
        self.counts = Counter()
        self.tags = defaultdict(set)   # canonical name -> {"akv", ...}
        self.tag_overrides = {}        # canonical name -> list of tags (user)
        self.ignored_keys = set()
        self.alias_index = {}          # key of name/alias -> canonical name
        self.entry_aliases = defaultdict(list)   # canonical name -> aliases
        self.info = {}                 # canonical name -> {"prins": [...], ...}
        self.user_names = set()
        self.user_ignored = set()
        if bundled_path and os.path.exists(bundled_path):
            self._load_file(bundled_path)
        if user_path and os.path.exists(user_path):
            self._load_file(user_path, user=True)
        for name, tags in self.tag_overrides.items():
            self.tags[self.canonical(name)] = set(tags)

    # ---------- loading / saving ----------
    def _load_file(self, path, user=False):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        for name in data.get("ignored", []):
            self.ignored_keys.add(normalize_key(name))
            if user:
                self.user_ignored.add(name)
        entries = [{"name": e} if isinstance(e, str) else e for e in data.get("artists", [])]
        # 1) names + aliases from the file win over the built-in ALIASES
        for entry in entries:
            name = entry["name"]
            self.alias_index[normalize_key(name)] = name
            for alias in entry.get("aliases", []):
                self.alias_index[normalize_key(alias)] = name
                if alias not in self.entry_aliases[name]:
                    self.entry_aliases[name].append(alias)
        # 2) add the artists
        for entry in entries:
            name = self._add(entry["name"], entry.get("count", 0))
            if name and entry.get("tags"):
                self.tags[name].update(entry["tags"])
            if name:
                extra = {k: entry[k] for k in INFO_FIELDS if entry.get(k)}
                if extra:
                    self.info.setdefault(name, {}).update(extra)
            if name and user:
                self.user_names.add(name)
        if user:
            self.tag_overrides.update(data.get("tag_overrides", {}))

    def _resolve_key(self, key):
        """Follow aliases (artists.json first, then ALIASES) to a canonical name."""
        seen, found = set(), None
        while key not in seen:
            seen.add(key)
            if key in self.alias_index:
                return self.alias_index[key]
            if key in _ALIAS_INDEX:
                found = _ALIAS_INDEX[key]
                key = normalize_key(found)
                continue
            break
        return found

    def _add(self, name, count=0):
        key = normalize_key(name)
        if key in EXCLUDED_KEYS or (key in self.ignored_keys and key not in self.alias_index):
            return None
        name = self._resolve_key(key) or self.by_key.get(key, name)
        self.by_key[key] = name
        self.by_key[normalize_key(name)] = name
        self.counts[name] += count
        return name

    def add_user_artist(self, name, tags=()):
        name = clean_segment(name)
        if not name or self.contains(name):
            return False
        name = self._add(name)
        if not name:
            return False
        self.user_names.add(name)
        if tags:
            self.set_tags(name, tags, save=False)
        self.save_user()
        return True

    def save_user(self):
        if not self.user_path:
            return
        os.makedirs(os.path.dirname(self.user_path), exist_ok=True)
        payload = {
            "artists": [{"name": n, "tags": sorted(self.tags.get(n, ()))}
                        for n in sorted(self.user_names, key=str.lower)],
            "tag_overrides": self.tag_overrides,
            "ignored": sorted(self.user_ignored, key=str.lower),
        }
        with open(self.user_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)

    def merge_from(self, names_with_counts):
        """Add names (e.g. from a new Plex export) to the user list."""
        added = 0
        for name, info in names_with_counts.items():
            count = info["count"] if isinstance(info, dict) else info
            tags = info.get("tags", set()) if isinstance(info, dict) else set()
            if normalize_key(name) in self.ignored_keys:
                continue
            if not self.contains(name):
                canon = self._add(name, count)
                if canon:
                    self.user_names.add(canon)
                    if tags:
                        self.tags[canon].update(tags)
                    added += 1
        if added:
            self.save_user()
        return added

    # ---------- tags ----------
    def has_tag(self, name, tag):
        return tag in self.tags.get(self.canonical(name), ())

    def is_akv(self, name):
        return self.has_tag(name, TAG_AKV)

    def set_tags(self, name, tags, save=True):
        canon = self.canonical(name)
        self.tags[canon] = set(tags)
        self.tag_overrides[canon] = sorted(tags)
        if save:
            self.save_user()

    def toggle_tag(self, name, tag):
        tags = set(self.tags.get(self.canonical(name), ()))
        tags ^= {tag}
        self.set_tags(name, tags)
        return tag in tags

    def ignore(self, name):
        """Remove an artist from the list (and skip it in future imports)."""
        canon = self.canonical(name)
        key = normalize_key(canon)
        self.ignored_keys.add(key)
        self.user_ignored.add(canon)
        self.by_key.pop(key, None)
        self.user_names.discard(canon)
        self.save_user()

    # ---------- lookups ----------
    def names(self, tag=None):
        names = set(self.by_key.values())
        if tag:
            names = {n for n in names if tag in self.tags.get(n, ())}
        return sorted(names, key=lambda n: strip_accents(n).lower())

    def contains(self, name):
        key = normalize_key(name)
        return key in self.by_key or key in self.alias_index

    def canonical(self, name):
        """Canonical spelling of ONE artist (or the cleaned input if unknown)."""
        cleaned = clean_segment(name)
        key = normalize_key(cleaned)
        resolved = self._resolve_key(key)
        if resolved:
            return resolved
        return self.by_key.get(key, _smart_title(cleaned))

    def aliases(self, name):
        return self.entry_aliases.get(self.canonical(name), [])

    def prins_years(self, name):
        return self.info.get(self.canonical(name), {}).get("prins", [])

    def arendprins_years(self, name):
        return self.info.get(self.canonical(name), {}).get("arendprins", [])

    @staticmethod
    def _join(lead, feat):
        result = " & ".join(lead)
        if feat:
            result = f"{result} feat. {' & '.join(feat)}" if result else " & ".join(feat)
        return result

    def normalize(self, value):
        """'den bremt & gary ft. jos' -> 'Den Bremt & Gary feat. Jos'."""
        lead, feat = split_artists(value)

        def _canon_list(items):
            seen, out = set(), []
            for item in items:
                c = self.canonical(item)
                if normalize_key(c) not in seen:
                    seen.add(normalize_key(c))
                    out.append(c)
            return out

        return self._join(_canon_list(lead), _canon_list(feat))

    def unknown_parts(self, value):
        """Artists in `value` that are not in the catalog."""
        lead, feat = split_artists(value)
        return [p for p in lead + feat if not self.contains(self.canonical(p))]

    def close_matches(self, name, limit=5, cutoff=0.6):
        """Known artists that look like `name` (typo tolerant), best first."""
        key = normalize_key(clean_segment(name))
        if not key:
            return []
        scored = []
        for k, canon in self.by_key.items():
            ratio = difflib.SequenceMatcher(None, key, k).ratio()
            # "zjieverleppen" vs "dezjieverleppen2017": also try containment
            if len(key) >= 5 and (key in k or k in key) and len(k) >= 5:
                ratio = max(ratio, 0.85 * min(len(key), len(k)) / max(len(key), len(k)) + 0.15)
            if ratio >= cutoff:
                scored.append((ratio, self.counts.get(canon, 0), canon))
        scored.sort(key=lambda t: (-t[0], -t[1]))
        out = []
        for _, _, canon in scored:
            if canon not in out:
                out.append(canon)
        return out[:limit]

    def suggest(self, value, auto_cutoff=0.86):
        """Recommendation for a (web) artist string.

        Returns (suggested_text, parts) where parts is a list of dicts:
          {"input", "output", "status", "candidates"}
        status: "known"   - in the list (maybe respelled)
                "fuzzy"   - typo, replaced by the closest known artist
                "unknown" - not in the list; candidates may help
        """
        lead, feat = split_artists(value)
        parts_out = []

        def _resolve(items):
            out = []
            for item in items:
                canon = self.canonical(item)
                if self.contains(canon):
                    info = {"input": item, "output": canon, "status": "known", "candidates": []}
                else:
                    cands = self.close_matches(item)
                    best_ratio = 0.0
                    if cands:
                        best_ratio = difflib.SequenceMatcher(
                            None, normalize_key(item), normalize_key(cands[0])).ratio()
                    # only auto-correct longer names; short ones (Tim/Tom) stay a question
                    if cands and best_ratio >= auto_cutoff and len(normalize_key(item)) >= 5:
                        info = {"input": item, "output": cands[0], "status": "fuzzy",
                                "candidates": cands}
                    else:
                        info = {"input": item, "output": canon, "status": "unknown",
                                "candidates": cands}
                parts_out.append(info)
                if normalize_key(info["output"]) not in {normalize_key(o) for o in out}:
                    out.append(info["output"])
            return out

        text = self._join(_resolve(lead), _resolve(feat))
        return text, parts_out

    def search(self, text, limit=50, tag=None):
        """Names containing `text` (accent/case-insensitive), popular first."""
        needle = strip_accents(text or "").lower().strip()
        names = self.names(tag)
        if needle:
            def _texts(n):
                return [n] + self.entry_aliases.get(n, [])
            names = [n for n in names
                     if any(needle in strip_accents(t).lower() for t in _texts(n))]

            def rank(n):
                low = strip_accents(n).lower()
                if any(strip_accents(a).lower().startswith(needle) for a in self.entry_aliases.get(n, [])):
                    low = needle + low
                if low.startswith(needle):
                    return 0
                if any(w.startswith(needle) for w in re.split(r"[\s'-]+", low)):
                    return 1
                return 2
            names.sort(key=lambda n: (rank(n), -self.counts.get(n, 0)))
        return names[:limit] if limit else names


# --------------------------------------------------------------------------
# Building the catalog from a Plex CSV export
# --------------------------------------------------------------------------
ARTIST_COLUMNS = ("albums.tracks.originalTitle",)


def artists_from_plex_csv(csv_path):
    """Return {canonical_name: track_count} from a Plex library export."""
    variants = defaultdict(Counter)   # key -> Counter(display variant)
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            for col in ARTIST_COLUMNS:
                raw = row.get(col, "") or ""
                akv_prefixed = {normalize_key(clean_segment(m))
                                for m in re.findall(r"\bAKV\s+([^,&]+)", raw, re.IGNORECASE)}
                lead, feat = split_artists(raw)
                for seg in lead + feat:
                    key = normalize_key(seg)
                    if key not in EXCLUDED_KEYS:
                        variants[key][seg] += 1
                        if key in akv_prefixed:
                            variants[key]["__akv__"] += 1

    result = {}
    for key, counter in variants.items():
        is_akv = counter.pop("__akv__", 0) > 0
        if key in _ALIAS_INDEX:
            name = _ALIAS_INDEX[key]
        else:
            # most frequent spelling, prefer not-all-lowercase
            name = max(counter.items(), key=lambda kv: (kv[0] != kv[0].lower(), kv[1]))[0]
            name = _smart_title(name)
        entry = result.setdefault(name, {"count": 0, "tags": set()})
        entry["count"] += sum(counter.values())
        if is_akv:
            entry["tags"].add(TAG_AKV)
    return result


def update_catalog_file(csv_path, json_path):
    """Merge a Plex export into artists.json (adds new artists, AKV tags),
    keeping aliases, prins info and the 'ignored' list. Returns number added."""
    try:
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {"artists": [], "ignored": []}
    ignored = {normalize_key(n) for n in data.get("ignored", [])}
    existing = {normalize_key(e["name"]): e for e in data.get("artists", [])}
    alias_of = {}
    for e in data.get("artists", []):
        for a in e.get("aliases", []):
            alias_of[normalize_key(a)] = normalize_key(e["name"])
    added = 0
    for name, info in artists_from_plex_csv(csv_path).items():
        key = normalize_key(name)
        key = alias_of.get(key, key)
        if key in ignored:
            continue
        if key in existing:
            if info["tags"]:
                existing[key]["tags"] = sorted(set(existing[key].get("tags", [])) | info["tags"])
        else:
            existing[key] = {"name": name, "tags": sorted(info["tags"])}
            added += 1
    data["artists"] = sorted(existing.values(), key=lambda e: strip_accents(e["name"]).lower())
    write_catalog_data(data, json_path)
    return added


def write_catalog_data(data, out_path):
    """Write artists.json with one artist per line (easy to edit by hand)."""
    lines = ["{", ' "artists": [']
    arts = data.get("artists", [])
    for i, e in enumerate(arts):
        entry = {"name": e["name"]}
        for k in ENTRY_FIELDS[1:]:
            if e.get(k):
                entry[k] = sorted(e[k]) if k == "tags" else e[k]
        lines.append("  " + json.dumps(entry, ensure_ascii=False) + ("," if i < len(arts) - 1 else ""))
    lines.append(" ],")
    lines.append(' "ignored": ' + json.dumps(sorted(data.get("ignored", []), key=str.lower),
                                             ensure_ascii=False))
    lines.append("}")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python artist_catalog.py <plex-export.csv> [artists.json]")
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "artists.json")
    n = update_catalog_file(sys.argv[1], out)
    print(f"{n} new artists merged into {out}")
