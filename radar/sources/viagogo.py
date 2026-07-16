# Viagogo / StubHub — protégé par un anti-bot (HUMAN/PerimeterX) : la page de
# recherche renvoie 202 vide sans navigateur réel. Ce module tente le fetch
# direct et, s'il est bloqué, remonte un statut "blocked". Pour le débloquer,
# configurer un proxy de scraping via SCRAPER_PROXY_PREFIX (ex: ScraperAPI).
import re
import urllib.parse

from ..http_client import fetch, SCRAPER_PROXY_PREFIX
from ..matcher import matches_watch

NAME = "viagogo"
LABEL = "Viagogo"
BASE = "https://www.viagogo.fr"


class BlockedError(RuntimeError):
    pass


def search(watch):
    q = urllib.parse.quote(watch["artist"])
    url = "%s/secure/search?q=%s" % (BASE, q)
    status, body = fetch(url, use_proxy=True)
    if status in (202, 403, 429) or len(body) < 2000:
        hint = "" if SCRAPER_PROXY_PREFIX else " — définir SCRAPER_PROXY_PREFIX pour contourner"
        raise BlockedError("anti-bot Viagogo (HTTP %s)%s" % (status, hint))

    listings = []
    seen_urls = set()
    # Les pages de résultats contiennent des liens événements de la forme
    # /Concerts/.../E-12345678 avec le nom en texte du lien.
    for m in re.finditer(
        r'href="(?P<href>[^"]*?/E-\d+[^"]*)"[^>]*>(?P<text>[^<]{3,120})<',
        body,
    ):
        href = m.group("href")
        text = m.group("text").strip()
        full = href if href.startswith("http") else BASE + href
        if full in seen_urls:
            continue
        seen_urls.add(full)
        event = {"name": text, "location": text, "date_start": None}
        if not matches_watch(watch, event):
            continue
        listings.append({
            "source": NAME,
            "listing_key": "vg:%s" % full,
            "event_name": text,
            "location": "",
            "date": None,
            "price": None,
            "currency": "EUR",
            "url": full,
            "detail": "annonce détectée sur Viagogo",
        })
    return listings
