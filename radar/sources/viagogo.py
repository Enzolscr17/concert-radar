# Viagogo / StubHub — protégé par un anti-bot AWS WAF (challenge JavaScript).
# Nécessite un proxy de scraping avec rendu JS, ex. ScraperAPI :
#   SCRAPER_PROXY_PREFIX=http://api.scraperapi.com?api_key=KEY&render=true&country_code=fr&url=
#
# ⚠️ Le rendu JS coûte ~10 crédits ScraperAPI par requête. Pour préserver le
# quota gratuit (5000/mois), cette source n'est réellement interrogée que
# toutes les VIAGOGO_MIN_INTERVAL_MINUTES (120 min par défaut) par recherche ;
# entre deux, les derniers résultats sont resservis depuis un cache mémoire.
import html
import os
import re
import time
import urllib.parse
from datetime import date

from ..http_client import fetch, SCRAPER_PROXY_PREFIX
from ..matcher import matches_watch

NAME = "viagogo"
LABEL = "Viagogo"
BASE = "https://www.viagogo.fr"

MIN_INTERVAL_MIN = float(os.environ.get("VIAGOGO_MIN_INTERVAL_MINUTES", "240"))

_cache = {}  # watch_id -> (timestamp, listings)

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # français
    "janv": 1, "fevr": 2, "fév": 2, "fev": 2, "mars": 3, "avr": 4, "mai": 5,
    "juin": 6, "juil": 7, "aout": 8, "août": 8, "sept": 9, "déc": 12,
}


class BlockedError(RuntimeError):
    pass


def _month_num(tok):
    t = tok.strip(". ").lower()
    for k, v in MONTHS.items():
        if t.startswith(k):
            return v
    return None


def _next_date(month, day):
    today = date.today()
    year = today.year
    try:
        if date(year, month, day) < today:
            year += 1
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _parse_events(body):
    """Extrait (url, nom, date ISO, lieu) des blocs <a href=...E-xxxx...>."""
    events = []
    seen = set()
    for m in re.finditer(
        r'<a[^>]*href="(?P<href>[^"]*?/E-\d+[^"]*)"[^>]*>(?P<inner>.*?)</a>',
        body, re.S,
    ):
        url = html.unescape(m.group("href")).split("?")[0]
        if not url.startswith("http"):
            url = BASE + url
        if url in seen:
            continue
        seen.add(url)
        tokens = [html.unescape(t).strip()
                  for t in re.split(r"<[^>]+>", m.group("inner"))]
        tokens = [t for t in tokens if t]
        # structure observée : [Mois, Jour, JourSemaine, Nom, Heure, "Ville, Pays", Salle, ...]
        month = day = None
        name = location = venue = ""
        i = 0
        while i < len(tokens):
            if month is None and _month_num(tokens[i]):
                month = _month_num(tokens[i])
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    day = int(tokens[i + 1])
                    i += 2
                    continue
            i += 1
        rest = [t for t in tokens
                if not _month_num(t) or len(t) > 5]  # écarte les tokens de date
        for t in rest:
            if re.match(r"^\d{1,2}:\d{2}", t) or t.isdigit() or len(t) < 3:
                continue
            if re.match(r"^(mon|tue|wed|thu|fri|sat|sun|lun|mar|mer|jeu|ven|sam|dim)\.?$", t.lower()):
                continue
            if t.lower() in ("see tickets", "voir les billets"):
                continue
            if "," in t and not location:
                location = t
            elif not name:
                name = t
            elif not venue and location:
                venue = t
        d = _next_date(month, day) if (month and day) else None
        if name:
            events.append({
                "url": url, "name": name, "date": d,
                "location": ", ".join(x for x in [venue, location] if x),
            })
    return events


def search(watch):
    now = time.time()
    cached = _cache.get(watch["id"])
    if cached and now - cached[0] < MIN_INTERVAL_MIN * 60:
        return cached[1]

    if not SCRAPER_PROXY_PREFIX:
        raise BlockedError(
            "anti-bot Viagogo — définir SCRAPER_PROXY_PREFIX (proxy avec render=true)")

    q = urllib.parse.quote(watch["artist"])
    status, body = fetch("%s/secure/search?q=%s" % (BASE, q),
                         use_proxy=True, timeout=110)
    if status != 200 or "challenge-container" in body or len(body) < 20000:
        raise BlockedError("challenge anti-bot Viagogo (HTTP %s, %d octets) — "
                           "vérifier que le proxy a bien render=true" % (status, len(body)))

    listings = []
    for ev in _parse_events(body):
        event = {"name": ev["name"], "location": ev["location"],
                 "date_start": ev["date"]}
        if not matches_watch(watch, event):
            continue
        listings.append({
            "source": NAME,
            "listing_key": "vg:%s" % ev["url"],
            "event_name": ev["name"],
            "location": ev["location"],
            "date": ev["date"],
            "price": None,
            "currency": "EUR",
            "url": ev["url"],
            "detail": "annonces dispo sur Viagogo (prix sur la page)",
        })
    _cache[watch["id"]] = (now, listings)
    return listings
