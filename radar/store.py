# Persistance JSON sur disque (écriture atomique). DATA_DIR pointe vers un
# volume persistant en production.
import json
import os
import threading
import uuid

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(_APP_ROOT, "data"))
DB_FILE = os.path.join(DATA_DIR, "db.json")

MAX_ALERTS = 500
MAX_SEEN = 5000

_lock = threading.RLock()


def _defaults():
    return {
        # watches: {id, artist, city, date_from, date_to, active, created_at}
        "watches": [],
        # alerts: {id, watch_id, source, event_name, location, date, price,
        #          currency, url, detail, created_at}
        "alerts": [],
        # seen: "watch_id:listing_key" -> timestamp (déduplication des notifs)
        "seen": {},
        # source -> {state: ok|blocked|unconfigured|error, detail, last_check}
        "source_status": {},
        # config saisie via l'interface (les variables d'env ont priorité)
        "config": {},  # telegram_token, telegram_chat_id, telegram_chat_name
        "last_scan": None,
    }


_db = _defaults()


def load():
    global _db
    with _lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            if os.path.exists(DB_FILE):
                with open(DB_FILE, encoding="utf8") as f:
                    data = json.load(f)
                base = _defaults()
                base.update(data)
                _db = base
        except Exception as err:  # fichier corrompu -> on repart à vide
            print("[store] lecture impossible, démarrage à vide:", err)
            _db = _defaults()
    return _db


def save():
    with _lock:
        if len(_db["alerts"]) > MAX_ALERTS:
            _db["alerts"] = _db["alerts"][-MAX_ALERTS:]
        if len(_db["seen"]) > MAX_SEEN:
            oldest = sorted(_db["seen"], key=_db["seen"].get)
            for k in oldest[: len(_db["seen"]) - MAX_SEEN]:
                del _db["seen"][k]
        tmp = DB_FILE + ".tmp"
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(_db, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DB_FILE)


def get_db():
    return _db


def lock():
    return _lock


def new_id():
    return uuid.uuid4().hex[:16]
