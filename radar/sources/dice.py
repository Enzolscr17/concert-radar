# DICE (dice.fm) — billetterie très utilisée en France (concerts, clubs).
# API de recherche publique découverte via le site :
#   POST https://api.dice.fm/unified_search  {"q": "..."}
# Les événements complets repassent "on-sale" quand des billets sont remis en
# vente via leur liste d'attente : la clé de déduplication inclut le statut,
# donc ce retour en vente redéclenche une alerte.
import json
import os
import urllib.request

from ..http_client import USER_AGENT
from ..matcher import matches_watch

NAME = "dice"
LABEL = "DICE"
API = "https://api.dice.fm/unified_search"

COUNTRY = os.environ.get("DICE_COUNTRY", "FR")  # vide = monde entier


def _post_json(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def search(watch):
    data = _post_json(API, {"q": watch["artist"]})
    listings = []
    for sec in data.get("sections", []):
        for item in sec.get("items", []):
            if item.get("type") != "event":
                continue
            ev = item.get("event") or {}
            venues = ev.get("venues") or [{}]
            venue = venues[0]
            city = venue.get("city") or {}
            if COUNTRY and (city.get("country_code") or "") != COUNTRY:
                continue

            location = ", ".join(
                x for x in [venue.get("name") or "", city.get("name") or ""] if x
            )
            date_start = (ev.get("dates") or {}).get("event_start_date")
            event = {
                "name": ev.get("name", ""),
                "location": location,
                "date_start": date_start,
            }
            if not matches_watch(watch, event):
                continue

            status = ev.get("status") or ""
            if status != "on-sale":  # sold-out / off-sale / announced…
                continue

            price = None
            pr = ev.get("price") or {}
            amount = pr.get("amount") or pr.get("amount_from")
            if amount:
                price = round(amount / 100.0, 2)

            perm = ev.get("perm_name") or ""
            url = "https://dice.fm/event/%s" % perm if perm else "https://dice.fm"
            listings.append({
                "source": NAME,
                "listing_key": "dice:%s:%s" % (ev.get("id") or perm, status),
                "event_name": ev.get("name", ""),
                "location": location,
                "date": (date_start or "")[:10] or None,
                "price": price,
                "currency": pr.get("currency") or "EUR",
                "url": url,
                "detail": "en vente sur DICE",
            })
    return listings
