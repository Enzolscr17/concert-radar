# Boucle de scan : interroge chaque source pour chaque watch active,
# filtre par catégorie, déduplique et notifie sur Telegram.
import time
import traceback

from . import notify, store
from .matcher import matches_category
from .sources import dice, reelax, ticketmaster, viagogo

SOURCES = [reelax, dice, ticketmaster, viagogo]
LABELS = {s.NAME: s.LABEL for s in SOURCES}


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _set_status(db, name, state, detail=""):
    db["source_status"][name] = {
        "state": state,
        "detail": detail[:300],
        "last_check": _now_iso(),
    }


def fetch_listings(watch):
    """Interroge toutes les sources pour une watch (sans filtre catégorie).
    Met à jour le statut de chaque source."""
    db = store.get_db()
    out = []
    for src in SOURCES:
        try:
            out.extend(src.search(watch))
            _set_status(db, src.NAME, "ok")
        except LookupError as e:            # source non configurée
            _set_status(db, src.NAME, "unconfigured", str(e))
        except viagogo.BlockedError as e:
            _set_status(db, src.NAME, "blocked", str(e))
        except Exception as e:
            _set_status(db, src.NAME, "error", str(e))
            print("[scanner] %s: %s" % (src.NAME, e))
    return out


def split_by_category(watch, listings):
    """Sépare (billets qui matchent la catégorie demandée, les autres).
    Sans catégorie demandée : tout matche. Les billets dont la source ne
    fournit pas la catégorie passent avec un avertissement plutôt que d'être
    perdus."""
    if not watch.get("category"):
        return list(listings), []
    matching, others = [], []
    for listing in listings:
        cat = listing.get("category")
        if cat is None:
            listing = dict(listing)
            extra = "⚠️ catégorie non vérifiable (demande : %s)" % watch["category"]
            listing["detail"] = " · ".join(
                x for x in [listing.get("detail"), extra] if x)
            matching.append(listing)
        elif matches_category(watch["category"], cat):
            matching.append(listing)
        else:
            others.append(listing)
    return matching, others


def _process_listing(watch, listing):
    """Déduplique, enregistre l'alerte et notifie. True si nouvelle."""
    db = store.get_db()
    key = "%s:%s" % (watch["id"], listing["listing_key"])
    with store.lock():
        if key in db["seen"]:
            return False
        db["seen"][key] = time.time()
        alert = dict(listing)
        alert["id"] = store.new_id()
        alert["watch_id"] = watch["id"]
        alert["created_at"] = _now_iso()
        db["alerts"].append(alert)
    ok, detail = notify.send(
        notify.format_alert(alert, LABELS[listing["source"]]))
    if not ok:
        print("[notify] échec Telegram:", detail)
    return True


def scan_watch(watch):
    """Scanne une seule recherche. Retourne (nb nouvelles alertes,
    billets disponibles dans d'autres catégories)."""
    listings = fetch_listings(watch)
    matching, others = split_by_category(watch, listings)
    n = 0
    for listing in matching:
        if _process_listing(watch, listing):
            n += 1
    db = store.get_db()
    with store.lock():
        db["last_scan"] = _now_iso()
        store.save()
    return n, others


def scan_once(only_watches=None):
    """Un cycle complet. Retourne le nombre de nouvelles alertes."""
    db = store.get_db()
    if only_watches is not None:
        watches = [w for w in only_watches if w.get("active")]
    else:
        with store.lock():
            watches = [w for w in db["watches"] if w.get("active")]
    total = 0
    for watch in watches:
        total += scan_watch(watch)[0]
    with store.lock():
        db["last_scan"] = _now_iso()
        store.save()
    return total


def run_forever(interval_minutes):
    while True:
        try:
            n = scan_once()
            if n:
                print("[scanner] %d nouvelle(s) alerte(s)" % n)
        except Exception:
            traceback.print_exc()
        time.sleep(max(60, int(interval_minutes * 60)))
