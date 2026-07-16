# Envoi des alertes Telegram (bot créé via @BotFather).
import json
import os
import urllib.parse
import urllib.request


def _conf():
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
    )


def is_configured():
    token, chat = _conf()
    return bool(token and chat)


def send(text):
    """Envoie un message HTML sur Telegram. Retourne (ok, detail)."""
    token, chat = _conf()
    if not token or not chat:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID non configurés"
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    payload = json.dumps({
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.load(r)
        return bool(body.get("ok")), json.dumps(body.get("result", body))[:200]
    except urllib.error.HTTPError as e:
        return False, "HTTP %s: %s" % (e.code, e.read().decode("utf8", "replace")[:200])
    except Exception as e:
        return False, str(e)


def format_alert(alert, label):
    price = ""
    if alert.get("price") is not None:
        price = "\n💶 <b>%.2f %s</b>" % (alert["price"], alert.get("currency") or "EUR")
    date = "\n📅 %s" % alert["date"] if alert.get("date") else ""
    loc = "\n📍 %s" % alert["location"] if alert.get("location") else ""
    detail = "\nℹ️ %s" % alert["detail"] if alert.get("detail") else ""
    return (
        "🎟 <b>Place trouvée !</b>\n"
        "🎤 %s%s%s%s%s\n"
        "🔎 Source : %s\n"
        '👉 <a href="%s">Voir l\'annonce</a>'
    ) % (alert["event_name"], date, loc, price, detail, label, alert["url"])
