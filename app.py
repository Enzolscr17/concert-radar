#!/usr/bin/env python3
# Concert Radar — surveille les plateformes de billetterie/revente et envoie
# une alerte Telegram dès qu'une place correspond à une recherche.
# 100 % bibliothèque standard Python : aucune dépendance à installer.
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from radar import notify, scanner, store, telegram_bot

PORT = int(os.environ.get("PORT", "8400"))
INTERVAL_MIN = float(os.environ.get("CHECK_INTERVAL_MINUTES", "5"))
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}

_scan_running = threading.Lock()


def _background_scan():
    if not _scan_running.acquire(blocking=False):
        return False
    def run():
        try:
            scanner.scan_once()
        finally:
            _scan_running.release()
    threading.Thread(target=run, daemon=True).start()
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "ConcertRadar/1.0"

    # ---------- helpers ----------
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf8"))
        except Exception:
            return {}

    def _serve_static(self, path):
        if path == "/":
            path = "/index.html"
        fp = os.path.normpath(os.path.join(PUBLIC_DIR, path.lstrip("/")))
        if not fp.startswith(PUBLIC_DIR) or not os.path.isfile(fp):
            self.send_error(404)
            return
        ext = os.path.splitext(fp)[1]
        with open(fp, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silence les logs d'accès

    # ---------- routes ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/state":
            db = store.get_db()
            with store.lock():
                self._json({
                    "watches": db["watches"],
                    "alerts": list(reversed(db["alerts"][-100:])),
                    "source_status": db["source_status"],
                    "last_scan": db["last_scan"],
                    "interval_minutes": INTERVAL_MIN,
                    "telegram_configured": notify.is_configured(),
                    "source_labels": scanner.LABELS,
                })
            return
        self._serve_static(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        db = store.get_db()

        if path == "/api/watches":
            data = self._read_body()
            artist = (data.get("artist") or "").strip()
            if not artist:
                self._json({"error": "artiste requis"}, 400)
                return
            watch = {
                "id": store.new_id(),
                "num": None,
                "artist": artist,
                "city": (data.get("city") or "").strip(),
                "date_from": (data.get("date_from") or "").strip(),
                "date_to": (data.get("date_to") or "").strip(),
                "category": (data.get("category") or "").strip(),
                "active": True,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            with store.lock():
                watch["num"] = telegram_bot._next_num(db)
                db["watches"].append(watch)
                store.save()
            _background_scan()
            self._json(watch, 201)
            return

        m = re.match(r"^/api/watches/([0-9a-f]+)/toggle$", path)
        if m:
            with store.lock():
                for w in db["watches"]:
                    if w["id"] == m.group(1):
                        w["active"] = not w["active"]
                        store.save()
                        self._json(w)
                        return
            self._json({"error": "introuvable"}, 404)
            return

        if path == "/api/scan":
            started = _background_scan()
            self._json({"started": started})
            return

        if path == "/api/test-telegram":
            ok, detail = notify.send(
                "✅ <b>Concert Radar</b> est bien connecté à ce canal !"
            )
            self._json({"ok": ok, "detail": detail}, 200 if ok else 502)
            return

        self.send_error(404)

    def do_DELETE(self):
        m = re.match(r"^/api/watches/([0-9a-f]+)$", self.path.split("?")[0])
        if m:
            db = store.get_db()
            with store.lock():
                before = len(db["watches"])
                db["watches"] = [w for w in db["watches"] if w["id"] != m.group(1)]
                # purge les alertes et la mémoire de déduplication associées
                db["alerts"] = [a for a in db["alerts"] if a.get("watch_id") != m.group(1)]
                db["seen"] = {k: v for k, v in db["seen"].items()
                              if not k.startswith(m.group(1) + ":")}
                store.save()
            self._json({"deleted": before - len(db["watches"])})
            return
        self.send_error(404)


def main():
    store.load()
    threading.Thread(
        target=scanner.run_forever, args=(INTERVAL_MIN,), daemon=True
    ).start()
    threading.Thread(target=telegram_bot.run_forever, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Concert Radar sur http://localhost:%d (scan toutes les %g min)"
          % (PORT, INTERVAL_MIN))
    server.serve_forever()


if __name__ == "__main__":
    main()
