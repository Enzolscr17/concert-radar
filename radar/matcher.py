# Correspondance entre une "watch" (artiste / ville / dates) et un événement.
import re
import unicodedata


def normalize(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")  # accents
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def contains_all_tokens(target, query):
    """Tous les mots de `query` doivent apparaître dans `target`."""
    t = " " + normalize(target) + " "
    tokens = [tok for tok in normalize(query).split(" ") if tok]
    if not tokens:
        return False
    return all(tok in t for tok in tokens)


def matches_category(spec, text):
    """spec: 'fosse', 'cat 1-2-3', 'carré or'… / text: catégorie du billet.
    Les mots matchent en sous-chaîne ('cat' -> 'catégorie'), les nombres en
    entier exact (pour que 'cat 2' ne matche pas la zone '209')."""
    t = normalize(text)
    spec_n = normalize(spec)
    nums = re.findall(r"\d+", spec_n)
    words = [w for w in spec_n.split()
             if not w.isdigit() and w not in ("ou", "et", "-")]
    for w in words:
        if w not in t:
            return False
    if nums:
        tnums = set(re.findall(r"\d+", t))
        if not any(n in tnums for n in nums):
            return False
    return True


def matches_watch(watch, event):
    """event: {name, location, date_start (ISO ou None)}"""
    haystack = "%s %s" % (event.get("name", ""), event.get("location") or "")
    if not contains_all_tokens(haystack, watch["artist"]):
        return False

    if watch.get("city"):
        loc = event.get("location") or event.get("name", "")
        if not contains_all_tokens(loc, watch["city"]):
            return False

    date_start = event.get("date_start")
    if (watch.get("date_from") or watch.get("date_to")) and date_start:
        d = date_start[:10]
        if watch.get("date_from") and d < watch["date_from"]:
            return False
        if watch.get("date_to") and d > watch["date_to"]:
            return False
    return True
