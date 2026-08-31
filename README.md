# 🏓 Table Tennis Scorer

Mobile-first table tennis scoring platform with live shareable links, scorer accounts, tournament brackets, and an admin panel. Inspired by [iquitscorer](../iquitscorer).

## Features

- 🔐 **Scorer login** — the scorer who starts a match continues it after re-login
- 👑 **Admin panel** — manage users (add/delete/activate/promote scorers), matches, tournaments, and **scoring defaults**
- 📺 **Live scoring link** — read-only shareable URL, auto-refreshes every 5 seconds
- 🔁 **Service change notice** — banner + haptic buzz whenever service switches (every 2 points normally, every 1 point at deuce — both configurable per match)
- 🤝 **Singles & Doubles** — full ITTF-compliant doubles rotation `A1 → B1 → A2 → B2 → A1 …` with configurable initial server/receiver sides
- 🌐 **Let button** — record a net-on-serve without changing score or serve
- 🔀 **Change-ends banner** — in the deciding game, once the leader reaches N points (default 5, configurable, 0 disables) a change-ends alert fires; in doubles the receiving pair is auto-swapped
- 🏆 **Tournaments** — create tournaments, bulk-upload participants, add rounds, pair participants (singles **or** doubles), edit / delete pairings before a match starts, spin up matches per pairing, winners appear in bracket
- 🌐 **Tournament-wide live board** — one public link (`/live/tournaments/{id}`) shows every match with its current score; viewers click any match to open its full live scoreboard
- 📱 **Mobile-first PWA** — installable, big touch targets, works offline (basic caching)
- ✅ **Tested** — pure scoring engine covered by a pytest suite (`tests/`)

## Tech Stack

- **Backend**: FastAPI + Python
- **Frontend**: HTMX + Tailwind CSS
- **Database**: AWS DynamoDB
- **Deployment**: Uvicorn + Nginx + EC2

## Quick Start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt   # dev deps include pytest

# Configure AWS creds (env vars, ~/.aws/credentials, or IAM role)
export AWS_REGION=me-central-1

python setup_db.py       # creates the tt_* tables + default admin
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

Open http://localhost:8002 and log in as **admin / admin** (change the password immediately via `/change-password`).

## Tests

The scoring engine (`app/logic.py`) is pure and covered by a pytest suite —
no AWS or DB required to run it.

```bash
pip install -r requirements-dev.txt   # once
pytest -q                             # run everything
pytest -q -k doubles                  # only doubles tests
pytest -q tests/test_logic.py::test_let_does_not_change_score
```

For a full walkthrough (automated + manual test scenarios, every config
knob, event schema, troubleshooting) see [TESTING.md](TESTING.md).

What's covered:

| Area | Tests |
|------|-------|
| Singles serve rotation (every 2, every 1 at deuce) | ✅ |
| Win by 2, no-game-at-11–10, deuce play beyond 11 | ✅ |
| Match winner in Bo3 | ✅ |
| First server alternates each new game | ✅ |
| Doubles rotation `A1→B1→A2→B2→A1` (full cycle) | ✅ |
| Doubles display names / server & receiver names | ✅ |
| Let (net on serve): no score, no serve advance | ✅ |
| Deciding-game change-ends alert at N (fires once) | ✅ |
| Change-ends disabled when threshold = 0 | ✅ |
| Doubles receiver-side swap on change-ends | ✅ |
| Backward compatibility (matches without `match_type`) | ✅ |
| Undone events ignored | ✅ |
| Bulk-pairing line parser (singles / doubles / separators / bad input) | ✅ |

## DynamoDB tables (deletable when the tournament is over)

| Table | Purpose |
|-------|---------|
| `tt_users` | Users (scorers, players, admin) + aggregate stats |
| `tt_matches` | Match metadata (players, format, tournament link, match type, doubles partners) |
| `tt_events` | Individual points and lets (source of truth for scoring) |
| `tt_tournaments` | Tournament brackets (participants + rounds + pairings) |
| `tt_settings` | Global scoring defaults (best-of, points, service intervals, match type, change-ends threshold) |
| `tt_roster` | Admin-managed roster of players used when building tournaments |

Wipe them with `python teardown_db.py` when you no longer need them.

## Routes

| Path | Purpose |
|------|---------|
| `/` | Home — create new match / tournament, see recents |
| `/login`, `/register`, `/logout` | Auth |
| `/change-password` | Change own password |
| `/profile/{user_id}` | Player/scorer profile with stats |
| `/matches/{match_id}` | **Live scoring** (needs auth + ownership/admin) |
| `/live/{match_id}` | **Public read-only** live scoreboard for one match (share this link) |
| `/tournaments/{tournament_id}` | Tournament bracket management (owner + admin) |
| `/live/tournaments/{tournament_id}` | **Public tournament board** — every match, live scores, click into any live scoreboard |
| `/admin` | Admin panel (users, matches, tournaments, roster, scoring defaults) |

### Tournament-management sub-routes (owner + admin)

| Method + Path | Purpose |
|---|---|
| `POST /tournaments` | Create a tournament |
| `POST /tournaments/{tid}/participants` | Add one participant (name or roster player) |
| `POST /tournaments/{tid}/participants/bulk` | **Bulk upload** — paste many names, one per line |
| `POST /tournaments/{tid}/participants/remove` | Remove a participant |
| `POST /tournaments/{tid}/rounds` | Add a round |
| `POST /tournaments/{tid}/rounds/{n}/pairs` | Add a pairing (singles or doubles) |
| `POST /tournaments/{tid}/rounds/{n}/pairs/bulk` | **Bulk paste pairings** (see grammar below) |
| `POST /tournaments/{tid}/rounds/{n}/pairs/{slot}/edit` | Change who plays whom (only before the match starts) |
| `POST /tournaments/{tid}/rounds/{n}/pairs/{slot}/delete` | Remove a pairing (only before the match starts) |
| `POST /tournaments/{tid}/rounds/{n}/start/{slot}` | Spin up a match record and open the scoreboard |

### Bulk-pairings text grammar

One pairing per line. Empty lines and lines starting with `#` are ignored.

```
Alice vs Bob                (singles)
Charlie - Dave              (singles, dash separator)
Eve | Frank                 (singles, pipe separator)
Alice + Amy vs Bob + Ben    (doubles)
Alice & Amy vs Bob & Ben    (doubles, ampersand)
Alice / Amy vs Bob / Ben    (doubles, slash)
```

- Side separator: `vs`, `v`, `-`, `—`, `|` (case-insensitive).
- Doubles partner separator: `+`, `&`, `/`.
- Participant names are matched **case-insensitively** against people already added to the tournament — unknown names are skipped and reported.

## Table tennis rules implemented

All rules are **configurable per match** and inherit sensible defaults from
the admin panel (`/admin` → *Scoring Defaults*).

### Scoring
- Points per game: default **11**, editable (min 5).
- **Win by 2** — 11–9 wins, 11–10 does not; deuce continues until one side leads by 2.
- Match format: **best of 1, 3, 5, or 7**. First to `best_of // 2 + 1` games wins.

### Service
- Serve rotates every **`service_interval`** points (default **2**).
- At deuce (both ≥ `points_to_win - 1`) serve rotates every **`deuce_interval`** points (default **1**).
- Initial server alternates each game.
- The scoreboard shows a **🔁 Service change** banner (with a short vibration on mobile) at the exact point service switches.

### Singles vs Doubles
- `match_type = "singles"` (default): two players; server just flips between team A and team B.
- `match_type = "doubles"`: four players (A1+A2 vs B1+B2). Serve rotates
  player-by-player following the ITTF pattern:

  ```
  A1 → B1 → A2 → B2 → A1 …
  ```

  (“next server = current receiver; next receiver = partner of previous server”).
  At deuce, each player still serves only 1 point before rotation.
  Configurable per match: `first_server` (team), `first_server_side` (1 or 2),
  `first_receiver_side` (1 or 2).

### Change ends (deciding game)
- In the **deciding game** (both teams one game away from winning), once the
  leader reaches **`deciding_side_change_at`** points (default **5**, set **0**
  to disable) a **🔀 CHANGE ENDS** banner + haptic pulse fires **once**.
- In doubles, the receiving pair is auto-swapped at that moment (ITTF rule).

### Let (net on serve)
- Scorers can tap **🌐 Let** on the scoreboard — an event is recorded but the
  score and serve rotation are unaffected. The count is shown in the match
  summary once games have completed.

### Rules NOT enforced by the app (physical umpiring)
These are impossible to detect from a score-only interface — the scorer / umpire
awards the point manually, which is the standard workflow:

- Ball toss ≥ 16 cm, open-palm, struck while falling.
- Diagonal serve landing (doubles) — the scoreboard shows a text hint instead.
- Partners alternating shots in doubles.
- Volley / double-bounce / hitting the net for point loss.

## Deploy to EC2 (Amazon Linux) — `tt.azizzoaib.com`

Same pattern as `52patta.azizzoaib.com` (iquitscorer). One EC2 host, Nginx virtual
host per subdomain, uvicorn on a unique port (`8002` here), Let's Encrypt SSL.

**1. DNS.** Create an A record `tt.azizzoaib.com` → EC2 public IP (Route 53
or wherever azizzoaib.com is hosted).

**2. Security group.** Ensure inbound TCP `80` and `443` are open on the EC2.

**3. Edit `deploy.sh`** and set:
- `REPO_URL` — your GitHub repo
- `CERTBOT_EMAIL` — your email for Let's Encrypt notices
- (`DOMAIN` is already `tt.azizzoaib.com`)

**4. Run it on the EC2:**
```bash
bash deploy.sh
```

The script installs Python + Nginx + certbot, creates a `table-tennis-scorer.service`
systemd unit, writes an Nginx vhost for `tt.azizzoaib.com`, requests a
Let's Encrypt cert (auto-redirects HTTP → HTTPS), and provisions the DynamoDB
tables. It coexists with `iquitscorer.service` — different port (`8002` vs
`8000`), different Nginx `server_name`.

**5. Quick redeploy after `git push`:**
```bash
bash redeploy.sh
```

If certbot fails during first run (DNS not propagated yet, security group
closed), fix the cause then re-run:
```bash
sudo certbot --nginx -d tt.azizzoaib.com -m you@example.com --agree-tos --redirect
```

## Roles

- **admin** — full access: manage users, matches, tournaments
- **scorer** — create + score matches and tournaments (needs admin activation on register)
- **player** — auto-activated on register; can view their profile / stats

Admins can promote a player to scorer (or vice versa) and reset passwords from the admin panel.

## Notes

- Icons for the PWA go in `app/static/icons/icon-192.png` and `icon-512.png`. If you don't add them, the manifest will still work; the icons just won't render.
- Same architecture and deployment pattern as [iquitscorer](../iquitscorer). Runs alongside it on the same EC2: iquit on `52patta.azizzoaib.com` → `127.0.0.1:8000`, this app on `tt.azizzoaib.com` → `127.0.0.1:8002`.
- The live-share link in the match page is generated dynamically from the request URL, so it will render as `https://tt.azizzoaib.com/live/<match_id>` once deployed.
