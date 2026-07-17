# Pilotage complet par Telegram : le bot écoute les messages (long polling)
# et permet de créer / lister / supprimer des recherches sans passer par le web.
#
#   "Don Toliver, paris, 25 octobre"  -> crée la recherche
#   /concert                          -> liste les recherches actives
#   /suppr 2                          -> supprime la recherche n°2
#   /scan                             -> lance un scan immédiat
#   /aide                             -> aide
import json
import os
import re
import threading
import time
import traceback
import urllib.parse
import urllib.request
from datetime import date

from . import notify, scanner, store
from .matcher import normalize

MONTHS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    "décembre": 12, "janv": 1, "fev": 2, "fév": 2, "avr": 4, "juil": 7,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12, "déc": 12,
}

HELP = (
    "🎟 <b>Concert Radar</b> — commandes :\n\n"
    "➕ Ajouter une recherche : envoie simplement\n"
    "<code>artiste, ville, date</code>\n"
    "Exemples :\n"
    "• <code>Don Toliver, Paris, 25 octobre</code>\n"
    "• <code>Don Toliver, Paris, 25 octobre, fosse</code>\n"
    "• <code>Gims, Nîmes, cat 1-2</code> (catégorie 1 ou 2)\n"
    "• <code>Justice, Lyon</code>\n"
    "• <code>Orelsan</code> (partout, toutes dates)\n"
    "• <code>SCH, Marseille, du 20 au 30 novembre</code>\n"
    "Catégories comprises : fosse, cat 1-2-3-4, carré or, pelouse, "
    "gradins, tribune, VIP, debout, assis…\n\n"
    "📋 /concert — liste des recherches\n"
    "🗑 /suppr <code>N</code> — supprime la recherche n°N\n"
    "🔄 /scan — scan immédiat\n"
    "❓ /aide — cette aide"
)


def _api(method, **params):
    token, _ = notify._conf()
    url = "https://api.telegram.org/bot%s/%s" % (token, method)
    data = json.dumps(params).encode("utf8") if params else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=70) as r:
        return json.load(r)


def _reply(text):
    try:
        _api("sendMessage", chat_id=notify._conf()[1], text=text,
             parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        print("[telegram-bot] envoi impossible:", e)


# ---------- parsing des dates en français ----------

def parse_single_date(s, default_month=None, default_year=None):
    """'25 octobre', '25/10', '25/10/2026', '2026-10-25', '25' -> ISO ou None"""
    s = s.strip().lower().replace("1er", "1")
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _iso(y, mo, d)
    m = re.match(r"^(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?$", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else None
        if y and y < 100:
            y += 2000
        return _iso(y, mo, d)
    m = re.match(r"^(\d{1,2})(?:\s+([a-zéûà]+))?(?:\s+(\d{4}))?$", s)
    if m:
        d = int(m.group(1))
        mo = MONTHS.get(m.group(2) or "") or default_month
        y = int(m.group(3)) if m.group(3) else default_year
        if mo:
            return _iso(y, mo, d)
    return None


def _iso(y, mo, d):
    today = date.today()
    if not y:  # année absente : la prochaine occurrence à venir
        y = today.year
        try:
            if date(y, mo, d) < today:
                y += 1
        except ValueError:
            return None
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_date_part(s):
    """Retourne (date_from, date_to) ou None si la chaîne n'est pas une date.
    Gère 'le 25 octobre', 'du 20 au 30 novembre', '25/10 - 27/10'…"""
    s = re.sub(r"^(le|du)\s+", "", s.strip().lower())
    parts = re.split(r"\s+au\s+|\s*->\s*|\s+-\s+", s)
    if len(parts) == 2:
        d2 = parse_single_date(parts[1])
        if not d2:
            return None
        y2, m2 = int(d2[:4]), int(d2[5:7])
        d1 = parse_single_date(parts[0], default_month=m2, default_year=y2)
        if not d1:
            return None
        if d1 > d2:
            d1, d2 = d2, d1
        return d1, d2
    d = parse_single_date(s)
    return (d, d) if d else None


_CATEGORY_RE = re.compile(
    r"^(fosse|pelouse|debout|assis|gradins?|balcons?|tribunes?|vip|"
    r"carre(\s+or)?|golden(\s+circle)?|orchestre|parterre|loges?|"
    r"cat(egories?)?\b)"
)


def looks_like_category(part):
    return bool(_CATEGORY_RE.match(normalize(part)))


def parse_watch_message(text):
    """'artiste, ville, date, catégorie' -> dict watch (sans id) ou None."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return None
    artist = parts[0]
    city, date_from, date_to, category = "", "", "", ""
    for part in parts[1:]:
        rng = parse_date_part(part)
        if rng and not date_from:
            date_from, date_to = rng
        elif looks_like_category(part) and not category:
            category = part
        elif not city:
            city = part
    return {"artist": artist, "city": city,
            "date_from": date_from, "date_to": date_to,
            "category": category}


# ---------- actions ----------

INTERVAL_MIN = float(os.environ.get("CHECK_INTERVAL_MINUTES", "5"))


def _sources_summary():
    db = store.get_db()
    with store.lock():
        status = dict(db["source_status"])
    ok = [scanner.LABELS.get(k, k) for k, v in status.items() if v.get("state") == "ok"]
    ko = [scanner.LABELS.get(k, k) for k, v in status.items() if v.get("state") != "ok"]
    parts = []
    if ok:
        parts.append("✅ scanné : " + ", ".join(ok))
    if ko:
        parts.append("⚠️ indispo : " + ", ".join(ko))
    return "\n".join(parts)


def _fmt_price(p, currency="EUR"):
    cur = "€" if (currency or "EUR") == "EUR" else currency
    return ("%.2f %s" % (p, cur)).replace(".00 ", " ")


def _alternatives_text(others):
    """Récap des billets dispo dans les autres catégories, groupé par
    événement puis catégorie, avec compte et prix minimum."""
    by_event = {}
    for l in others:
        ev_key = (l["event_name"], l.get("date"), l["url"])
        by_event.setdefault(ev_key, {}).setdefault(
            l.get("category") or "Autre", []).append(l)
    lines = ["🎫 <b>Dispo dans d'autres catégories :</b>"]
    for (name, date, url), cats in list(by_event.items())[:5]:
        lines.append("\n<b>%s</b>%s" % (name, " — %s" % date if date else ""))
        for cat, ls in sorted(cats.items()):
            prices = [l["price"] for l in ls if l.get("price") is not None]
            p = " · dès %s" % _fmt_price(min(prices), ls[0].get("currency")) if prices else ""
            lines.append("• %s : %d billet(s)%s" % (cat, len(ls), p))
        lines.append('👉 <a href="%s">Voir l\'événement</a>' % url)
    return "\n".join(lines)


def _scan_and_report(watch=None):
    """Scanne (tout ou une seule recherche) puis envoie un point à date."""
    others = []
    try:
        if watch:
            n, others = scanner.scan_watch(watch)
        else:
            n = scanner.scan_once()
    except Exception as e:
        _reply("❌ Le scan a planté : %s" % e)
        return
    label = ("pour <b>%s</b>" % _watch_label(watch)) if watch else ""
    if n:
        _reply("🎯 <b>%d place(s) trouvée(s)</b> %s — prix et liens juste au-dessus ⤴️\n"
               "Je continue de surveiller toutes les %g min." % (n, label, INTERVAL_MIN))
        return
    if watch and watch.get("category"):
        no_cat = dict(watch)
        no_cat["category"] = ""
        head = ("📭 Aucun billet « <b>%s</b> » pour <b>%s</b> pour l'instant."
                % (watch["category"], _watch_label(no_cat)))
    else:
        head = "📭 Point à date %s : <b>aucune place dispo pour l'instant</b>." % label
    parts = [head]
    if others:
        parts.append("")
        parts.append(_alternatives_text(others))
    else:
        parts.append(_sources_summary())
    parts.append("⏳ Je re-scanne toutes les %g min, tu recevras une alerte dès que ça tombe."
                 % INTERVAL_MIN)
    _reply("\n".join(parts))

def _watch_label(w):
    dates = ""
    if w.get("date_from"):
        dates = w["date_from"] if w["date_from"] == w.get("date_to") \
            else "%s → %s" % (w["date_from"], w.get("date_to") or "…")
    bits = [w["artist"]]
    bits.append(w["city"] or "partout")
    bits.append(dates or "toutes dates")
    if w.get("category"):
        bits.append("🎫 " + w["category"])
    return " · ".join(bits)


def _next_num(db):
    return max([w.get("num") or 0 for w in db["watches"]] + [0]) + 1


def create_watch(parsed):
    db = store.get_db()
    watch = {
        "id": store.new_id(),
        "num": None,
        "artist": parsed["artist"],
        "city": parsed["city"],
        "date_from": parsed["date_from"],
        "date_to": parsed["date_to"],
        "category": parsed.get("category", ""),
        "active": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with store.lock():
        watch["num"] = _next_num(db)
        db["watches"].append(watch)
        store.save()
    return watch


def handle_text(text):
    text = text.strip()
    low = text.lower()

    if low in ("/start", "/aide", "/help"):
        _reply(HELP)
        return

    if low.startswith("/concert") or low in ("/list", "/liste"):
        db = store.get_db()
        with store.lock():
            watches = list(db["watches"])
            alerts = db["alerts"]
        if not watches:
            _reply("Aucune recherche. Envoie <code>artiste, ville, date</code> pour en créer une.")
            return
        lines = ["📋 <b>Recherches :</b>"]
        for w in watches:
            n_alerts = sum(1 for a in alerts if a.get("watch_id") == w["id"])
            state = "" if w.get("active") else " ⏸"
            found = " — 🎟 %d trouvée(s)" % n_alerts if n_alerts else ""
            lines.append("<b>#%s</b> %s%s%s" % (w.get("num", "?"), _watch_label(w), state, found))
        lines.append("\n🗑 /suppr <code>N</code> pour supprimer · /scan pour scanner")
        _reply("\n".join(lines))
        return

    m = re.match(r"^/(suppr|supprimer|del|delete)\s+#?(\d+)$", low)
    if m:
        num = int(m.group(2))
        db = store.get_db()
        with store.lock():
            target = next((w for w in db["watches"] if w.get("num") == num), None)
            if target:
                db["watches"] = [w for w in db["watches"] if w["id"] != target["id"]]
                db["alerts"] = [a for a in db["alerts"] if a.get("watch_id") != target["id"]]
                db["seen"] = {k: v for k, v in db["seen"].items()
                              if not k.startswith(target["id"] + ":")}
                store.save()
        if target:
            _reply("🗑 Recherche <b>#%d</b> supprimée (%s)." % (num, _watch_label(target)))
        else:
            _reply("Aucune recherche n°%d. Tape /concert pour voir la liste." % num)
        return

    if low == "/scan":
        _reply("🔄 Scan de toutes les recherches en cours…")
        threading.Thread(target=_scan_and_report, daemon=True).start()
        return

    if low.startswith("/"):
        _reply("Commande inconnue. /aide pour la liste.")
        return

    parsed = parse_watch_message(text)
    if not parsed or not parsed["artist"]:
        _reply("Je n'ai pas compris 🤔 — envoie <code>artiste, ville, date</code>. /aide pour des exemples.")
        return
    watch = create_watch(parsed)
    _reply("✅ Recherche <b>#%d</b> créée : %s\n🔎 Premier scan en cours…"
           % (watch["num"], _watch_label(watch)))
    threading.Thread(target=_scan_and_report, args=(watch,), daemon=True).start()


# ---------- boucle de long polling ----------

def run_forever():
    if not notify.is_configured():
        print("[telegram-bot] non configuré, bot désactivé")
        return
    _, chat_id = notify._conf()
    offset = None
    try:  # ignore les messages reçus avant le démarrage
        res = _api("getUpdates", offset=-1)["result"]
        if res:
            offset = res[-1]["update_id"] + 1
    except Exception:
        pass
    print("[telegram-bot] à l'écoute des commandes")
    while True:
        try:
            params = {"timeout": 50}
            if offset is not None:
                params["offset"] = offset
            updates = _api("getUpdates", **params).get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                if str(chat.get("id")) != str(chat_id):
                    continue  # on n'obéit qu'au propriétaire
                if msg.get("text"):
                    handle_text(msg["text"])
        except Exception as e:
            print("[telegram-bot] erreur:", e)
            traceback.print_exc()
            time.sleep(5)
