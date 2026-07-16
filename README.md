# 🎟 Concert Radar

Surveille en permanence les plateformes de billetterie et de revente, et t'envoie
une **alerte Telegram avec le lien direct** dès qu'une place correspond à une de
tes recherches (artiste + ville + dates).

**Zéro dépendance** : Python 3.9+ suffit, rien à installer.

## Sources surveillées

| Source | Méthode | État |
|---|---|---|
| **Reelax Tickets** | API JSON publique du site (recherche + billets + prix) | ✅ fonctionne directement |
| **DICE** | API de recherche publique (`api.dice.fm`) — statut on-sale/sold-out, prix, retours en vente | ✅ fonctionne directement |
| **Ticketmaster** | API officielle Discovery (clé gratuite) | ⚠️ la France est quasi absente de leur API publique — utile surtout pour l'étranger |
| **Viagogo** | Scraping best-effort — anti-bot | ⚠️ nécessite `SCRAPER_PROXY_PREFIX` |
| ~~Zepass~~ | — | ❌ plateforme fermée |
| ~~Ticketswap, Shotgun, Fnac, Leboncoin~~ | — | ❌ verrouillés (Cloudflare / Vercel / DataDome), inaccessibles sans proxy payant |

## Pilotage par Telegram

Tout se gère directement depuis le chat avec le bot :

| Message | Effet |
|---|---|
| `Don Toliver, Paris, 25 octobre` | crée la recherche (ville et date optionnelles) |
| `Don Toliver, Paris, 25 octobre, fosse` | ne notifie que les billets fosse |
| `Gims, Nîmes, cat 1-2` | catégorie 1 **ou** 2 |
| `SCH, Marseille, du 20 au 30 novembre` | recherche sur une plage de dates |
| `/concert` | liste les recherches actives (avec leur n°) |
| `/suppr 2` | supprime la recherche n°2 |
| `/scan` | scan immédiat |
| `/aide` | aide |

Formats de date compris : `25 octobre`, `25 octobre 2026`, `25/10`, `21/07/2026`,
`2026-12-01`, `du 20 au 30 novembre`, `25/10 - 27/10`. Sans année, la prochaine
occurrence à venir est choisie. L'interface web reste disponible en parallèle.
Le bot n'obéit qu'au chat configuré dans `TELEGRAM_CHAT_ID`.

Catégories comprises : `fosse`, `cat 1-2-3-4` (= l'une d'elles), `carré or`,
`pelouse`, `gradins`, `tribune`, `balcon`, `VIP`, `debout`, `assis`, `loge`,
`orchestre`, `parterre`. Le filtre s'applique aux sources qui exposent la
catégorie des billets (Reelax) ; pour les autres (DICE…), l'alerte part quand
même avec la mention « catégorie non vérifiable » plutôt que de risquer de
rater une place.

## Démarrage rapide (local)

```bash
cd concert-radar
export TELEGRAM_BOT_TOKEN="123456:ABC..."   # cf. ci-dessous
export TELEGRAM_CHAT_ID="123456789"
export TICKETMASTER_API_KEY="..."           # optionnel mais recommandé
python3 app.py
```

Puis ouvre **http://localhost:8400**, ajoute une recherche, clique « Scanner
maintenant ». Le scan tourne ensuite tout seul toutes les 5 minutes
(`CHECK_INTERVAL_MINUTES` pour changer).

## Configurer Telegram (2 minutes)

1. Dans Telegram, écris à **@BotFather** → `/newbot` → choisis un nom → il te
   donne un **token** (`123456:ABC-DEF...`).
2. Envoie n'importe quel message à ton nouveau bot (important, sinon il ne peut
   pas t'écrire).
3. Ouvre dans ton navigateur :
   `https://api.telegram.org/bot<TON_TOKEN>/getUpdates`
   et repère `"chat":{"id": 123456789}` → c'est ton **chat id**.
4. Renseigne `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`, puis utilise le bouton
   « 📨 Tester Telegram » dans l'interface.

## Configurer Ticketmaster (2 minutes)

1. Crée un compte sur https://developer.ticketmaster.com
2. Crée une app → copie la **Consumer Key** → mets-la dans
   `TICKETMASTER_API_KEY`.

Le site ticketmaster.fr bloque le scraping (DataDome) ; l'API officielle permet
de détecter qu'un événement correspondant à ta recherche est **en vente** (ou
remis en vente) et t'envoie le lien officiel.

## Viagogo (optionnel)

Viagogo/StubHub bloquent les robots (HTTP 202 vide). Pour activer cette source,
prends une clé sur un proxy de scraping (ex. ScraperAPI, offre gratuite) et
configure :

```
SCRAPER_PROXY_PREFIX=http://api.scraperapi.com?api_key=TA_CLE&url=
```

Sans ça, la source s'affiche « bloqué (anti-bot) » dans l'interface — le reste
fonctionne normalement.

## Déployer 24/7 sur Railway (recommandé)

1. Pousse ce dossier sur un dépôt GitHub.
2. Sur https://railway.app → **New Project → Deploy from GitHub repo** →
   choisis le dépôt. Railway détecte le `Dockerfile` automatiquement.
3. Onglet **Variables** : ajoute `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
   `TICKETMASTER_API_KEY` (et le reste si besoin).
4. Onglet **Settings → Volumes** : ajoute un volume monté sur **`/data`**
   (pour que tes recherches survivent aux redéploiements).
5. **Settings → Networking → Generate Domain** pour obtenir l'URL de
   l'interface.

Fonctionne aussi sur Fly.io, Render, un VPS, un Raspberry Pi… : c'est un simple
conteneur qui expose le port 8400 et écrit dans `/data`.

## Comment ça marche

- `app.py` — serveur web (interface + API JSON) et lancement du scanner.
- `radar/scanner.py` — boucle : pour chaque recherche active × chaque source,
  récupère les annonces, filtre (`radar/matcher.py` : artiste/ville/dates,
  insensible aux accents), **déduplique** (une annonce ne notifie qu'une fois)
  et envoie sur Telegram (`radar/notify.py`).
- `radar/sources/*.py` — un adaptateur par site. Pour ajouter un site, crée un
  module avec `NAME`, `LABEL` et `search(watch) -> [listings]` et ajoute-le à
  `SOURCES` dans `scanner.py`.
- Les données vivent dans `data/db.json` (`DATA_DIR` en prod).

## Limites honnêtes

- « Scanner tout internet » n'existe pas : chaque site a une protection et un
  format différents, donc on couvre des sources précises, extensibles une par
  une.
- Reelax est la meilleure source pour les concerts complets en France (revente
  officielle à prix plafonné) — et c'est celle qui marche le mieux ici.
- Fnac Spectacles et les remises en vente fan-to-fan de Ticketmaster demandent
  un vrai navigateur headless ou un proxy payant ; pas inclus dans cette v1.
