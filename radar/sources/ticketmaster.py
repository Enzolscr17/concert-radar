# Ticketmaster — via l'API officielle Discovery v2 (clé gratuite sur
# https://developer.ticketmaster.com). Le site ticketmaster.fr est protégé
# par DataDome, le scraping direct est donc impossible ; l'API officielle
# permet de détecter les événements disponibles à la vente (y compris les
# remises en vente : un événement "onsale" qui matche une recherche).
import os
import urllib.parse

from ..http_client import fetch_json
from ..matcher import matches_watch

NAME = "ticketmaster"
LABEL = "Ticketmaster"
API = "https://app.ticketmaster.com/discovery/v2/events.json"


def api_key():
    return os.environ.get("TICKETMASTER_API_KEY", "").strip()


def search(watch):
    key = api_key()
    if not key:
        raise LookupError(
            "TICKETMASTER_API_KEY manquante (clé gratuite sur developer.ticketmaster.com)"
        )
    params = {
        "apikey": key,
        "keyword": watch["artist"],
        "countryCode": os.environ.get("TICKETMASTER_COUNTRY", "FR"),
        "size": "40",
        "sort": "date,asc",
    }
    if watch.get("city"):
        params["city"] = watch["city"]
    if watch.get("date_from"):
        params["startDateTime"] = watch["date_from"] + "T00:00:00Z"
    if watch.get("date_to"):
        params["endDateTime"] = watch["date_to"] + "T23:59:59Z"

    data = fetch_json(API + "?" + urllib.parse.urlencode(params))
    listings = []
    for ev in (data.get("_embedded") or {}).get("events", []):
        venues = (ev.get("_embedded") or {}).get("venues") or [{}]
        venue = venues[0]
        location = ", ".join(
            x for x in [
                (venue.get("name") or ""),
                ((venue.get("city") or {}).get("name") or ""),
            ] if x
        )
        date_start = ((ev.get("dates") or {}).get("start") or {}).get("dateTime") or \
                     ((ev.get("dates") or {}).get("start") or {}).get("localDate")
        event = {"name": ev.get("name", ""), "location": location, "date_start": date_start}
        if not matches_watch(watch, event):
            continue

        status = (((ev.get("dates") or {}).get("status")) or {}).get("code") or ""
        if status in ("cancelled", "postponed"):
            continue

        price = None
        currency = "EUR"
        for pr in ev.get("priceRanges") or []:
            if pr.get("min") is not None:
                price = pr["min"]
                currency = pr.get("currency") or "EUR"
                break

        # La clé inclut le statut : si un événement complet repasse "onsale",
        # cela génère une nouvelle alerte.
        listings.append({
            "source": NAME,
            "listing_key": "tm:%s:%s" % (ev.get("id"), status or "onsale"),
            "event_name": ev.get("name", ""),
            "location": location,
            "date": (date_start or "")[:10] or None,
            "price": price,
            "currency": currency,
            "url": ev.get("url") or "https://www.ticketmaster.fr",
            "detail": "vente officielle (%s)" % (status or "onsale"),
        })
    return listings
