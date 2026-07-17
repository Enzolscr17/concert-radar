# Reelax Tickets — revente officielle plafonnée entre fans (reelax-tickets.com).
# API JSON publique découverte via le site :
#   GET /api/events?limit=..&offset=..&searchQuery=..   -> événements
#   GET /api/events/{id}/tickets                        -> billets en vente
import urllib.parse

from ..http_client import fetch_json
from ..matcher import matches_watch

NAME = "reelax"
LABEL = "Reelax Tickets"
BASE = "https://reelax-tickets.com"


def search(watch):
    """Retourne une liste de listings pour la watch donnée."""
    q = urllib.parse.quote(watch["artist"])
    data = fetch_json("%s/api/events?limit=50&offset=0&searchQuery=%s" % (BASE, q))
    listings = []
    for ev in data.get("rows", []):
        if ev.get("status") != "online":
            continue
        event = {
            "name": ev.get("name", ""),
            "location": "%s %s" % (ev.get("location") or "", ev.get("address") or ""),
            "date_start": ev.get("dateStart"),
        }
        if not matches_watch(watch, event):
            continue
        url = "%s/e/n/%s" % (BASE, ev.get("url"))
        try:
            tickets = fetch_json("%s/api/events/%s/tickets" % (BASE, ev["id"]))
        except Exception:
            tickets = []
        for t in tickets or []:
            if t.get("status") != "sale":
                continue
            price_cents = (t.get("price") or 0) + (t.get("fees") or 0)
            category = t.get("Category") or {}
            cat = category.get("name") or ""
            group = (category.get("CategoriesGroup") or {}).get("name") or ""
            zone = ((t.get("seatDetails") or {}).get("zone") or "").strip()
            detail = " · ".join(x for x in [group, cat, zone] if x)
            listings.append({
                "source": NAME,
                "listing_key": "reelax:%s" % t["id"],
                "event_name": ev.get("name", ""),
                "location": ev.get("location") or ev.get("address") or "",
                "date": (ev.get("dateStart") or "")[:10] or None,
                "price": round(price_cents / 100.0, 2),
                "currency": t.get("currency") or "EUR",
                "url": url,
                "detail": detail,
                # catégorie du billet (filtre + regroupement) ; la zone reste
                # dans detail pour ne pas éclater les regroupements par siège
                "category": " · ".join(x for x in [group, cat] if x) or None,
            })
    return listings
