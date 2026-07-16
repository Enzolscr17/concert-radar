# Petit client HTTP basé sur urllib (aucune dépendance externe).
import gzip
import json
import os
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Préfixe proxy de scraping optionnel (ex: ScraperAPI) pour les sites protégés :
# SCRAPER_PROXY_PREFIX="http://api.scraperapi.com?api_key=XXX&url="
SCRAPER_PROXY_PREFIX = os.environ.get("SCRAPER_PROXY_PREFIX", "")


def fetch(url, timeout=20, use_proxy=False, headers=None):
    """Retourne (status_code, body_str). Lève en cas d'erreur réseau."""
    target = url
    if use_proxy and SCRAPER_PROXY_PREFIX:
        target = SCRAPER_PROXY_PREFIX + urllib.parse.quote(url, safe="")
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(target, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return r.status, body.decode("utf8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf8", errors="replace")


def fetch_json(url, timeout=20, use_proxy=False):
    status, body = fetch(
        url, timeout=timeout, use_proxy=use_proxy,
        headers={"Accept": "application/json"},
    )
    if status != 200:
        raise RuntimeError("HTTP %s sur %s" % (status, url))
    return json.loads(body)
