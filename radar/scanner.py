# Boucle de scan : interroge chaque source pour chaque watch active,
# déduplique et notifie sur Telegram.
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


def scan_once(only_watches=None):
    """Un cycle de scan. `only_watches` permet de ne scanner que certaines
    recherches (ex: celle qui vient d'être créée). Retourne le nombre de
    nouvelles alertes."""
    db = store.get_db()
    if only_watches is not None:
        watches = [w for w in only_watches if w.get("active")]
    else:
        with store.lock():
            watches = [w for w in db["watches"] if w.get("active")]
    new_alerts = 0

    for src in SOURCES:
        had_error = False
        for watch in watches:
            try:
                listings = src.search(watch)
            except LookupError as e:          # source non configurée
                _set_status(db, src.NAME, "unconfigured", str(e))
                had_error = True
                break
            except viagogo.BlockedError as e:
                _set_status(db, src.NAME, "blocked", str(e))
                had_error = True
                break
            except Exception as e:
                _set_status(db, src.NAME, "error", str(e))
                print("[scanner] %s: %s" % (src.NAME, e))
                traceback.print_exc()
                had_error = True
                continue

            for listing in listings:
                # Filtre par catégorie demandée (fosse, cat 1-2…) quand la
                # source fournit l'info ; sinon on alerte quand même en le
                # signalant, plutôt que de rater une place.
                if watch.get("category"):
                    cat_txt = listing.get("category")
                    if cat_txt:
                        if not matches_category(watch["category"], cat_txt):
                            continue
                    else:
                        listing = dict(listing)
                        extra = "⚠️ catégorie non vérifiable (demande : %s)" % watch["category"]
                        listing["detail"] = " · ".join(
                            x for x in [listing.get("detail"), extra] if x)
                key = "%s:%s" % (watch["id"], listing["listing_key"])
                with store.lock():
                    if key in db["seen"]:
                        continue
                    db["seen"][key] = time.time()
                    alert = dict(listing)
                    alert["id"] = store.new_id()
                    alert["watch_id"] = watch["id"]
                    alert["created_at"] = _now_iso()
                    db["alerts"].append(alert)
                new_alerts += 1
                ok, detail = notify.send(
                    notify.format_alert(alert, LABELS[listing["source"]])
                )
                if not ok:
                    print("[notify] échec Telegram:", detail)

        if not had_error:
            _set_status(db, src.NAME, "ok")

    with store.lock():
        db["last_scan"] = _now_iso()
        store.save()
    return new_alerts


def run_forever(interval_minutes):
    while True:
        try:
            n = scan_once()
            if n:
                print("[scanner] %d nouvelle(s) alerte(s)" % n)
        except Exception:
            traceback.print_exc()
        time.sleep(max(60, int(interval_minutes * 60)))
