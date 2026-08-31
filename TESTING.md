# Testing the Scoring Engine + Configuration Reference

This document explains **how to run the automated test suite**, **how to
manually verify every table-tennis rule** the engine implements, and lists
**every configuration knob** you can tune (global, per-tournament, per-match).

- Engine under test: [`app/logic.py`](app/logic.py) — pure, no AWS, no state.
- Suite: [`tests/`](tests/) — currently **38 tests**, `pytest`-based.
- Config: `tt_settings` DynamoDB table + per-match / per-tournament overrides.

---

## 1. Run the automated suite

### One-time setup

```bash
cd table-tennis-scorer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

`requirements-dev.txt` adds `pytest>=8.0`. The engine tests never touch AWS,
so **no credentials are required** to run them.

### Commands

```bash
pytest -q                                     # everything, quiet
pytest -v                                     # everything, verbose
pytest -q tests/test_logic.py                 # scoring engine only
pytest -q tests/test_pair_parsing.py          # bulk-pairing parser only
pytest -q -k doubles                          # keyword filter
pytest -q -k "deuce or change_ends"           # boolean keyword
pytest -q tests/test_logic.py::test_singles_deuce_won_by_two   # single test
pytest -q --tb=short                          # short tracebacks on failure
pytest -q -x                                  # stop at first failure
```

### What the suite covers

| File | Focus | # tests |
|------|-------|---------|
| [`tests/test_logic.py`](tests/test_logic.py) | `compute_state` — all scoring rules | 23 |
| [`tests/test_pair_parsing.py`](tests/test_pair_parsing.py) | `_parse_pair_line` — bulk-pairing grammar | 15 |

Every rule from the README's *Table tennis rules implemented* section is
exercised by at least one test. Quick map:

| Rule | Test |
|------|------|
| Singles serve flips every 2 points | `test_singles_serve_flips_after_two_points` |
| No flip on point 1 | `test_singles_serve_stays_after_one_point` |
| Deuce flag activates at 10–10 | `test_singles_deuce_flag_activates_at_10_10` |
| Serve flips every point at deuce | `test_singles_serve_flips_every_point_in_deuce` |
| Game won at 11 with ≥ 2 margin | `test_singles_game_won_at_11_by_2` |
| No game at 11–10 | `test_singles_no_game_at_11_10` |
| Deuce won by 2 (e.g. 13–11) | `test_singles_deuce_won_by_two` |
| Match winner in Bo3 | `test_singles_match_winner_bo3` |
| First server alternates each new game | `test_singles_first_server_alternates_each_game` |
| Doubles rotation A1→B1→A2→B2→A1 | `test_doubles_rotation_a1_b1_a2_b2_cycle` |
| Doubles server / team display names | `test_doubles_server_name_display`, `test_doubles_team_display_name` |
| Let event: no score change | `test_let_does_not_change_score` |
| Let event: no serve rotation | `test_let_does_not_advance_serve_rotation` |
| Change-ends alert at N in deciding game | `test_change_ends_alert_fires_at_5_in_deciding_game` |
| No change-ends in non-deciding game | `test_change_ends_does_not_fire_in_non_deciding_game` |
| `deciding_side_change_at = 0` disables it | `test_change_ends_disabled_when_threshold_zero` |
| Change-ends fires only once per deciding game | `test_change_ends_alert_fires_only_once_per_deciding_game` |
| Doubles receiver-side auto-swap on change-ends | `test_doubles_receiver_swaps_on_deciding_side_change` |
| Backward-compat: `match_type` missing → singles | `test_missing_match_type_defaults_to_singles` |
| Undone events ignored | `test_undone_event_is_ignored` |
| Player name helper | `test_singles_player_name_helper` |
| Bulk-pair grammar (all separators + rejection) | `test_pair_parsing.py::*` |

---

## 2. Write your own engine test (template)

The engine is pure. You build an *events* list, hand it to `compute_state`,
and assert on the returned dict.

```python
from app.logic import compute_state

MATCH = {
    "match_id": "demo",
    "match_type": "singles",
    "player_a": "Alice",
    "player_b": "Bob",
    "best_of": 3,
    "points_to_win": 11,
    "service_interval": 2,
    "deuce_interval": 1,
    "first_server": "A",
    "deciding_side_change_at": 5,
}

def _pt(scorer):
    return {"type": "point", "scorer": scorer}

def test_your_scenario():
    events = [_pt("A")] * 2 + [_pt("B")] * 9 + [_pt("A")] * 9   # 11–9 for A
    state = compute_state(MATCH, events)
    assert state["games"][0]["winner"] == "A"
    assert state["games"][0]["a"] == 11
    assert state["games"][0]["b"] == 9
```

### Event schema

```python
{"type": "point", "scorer": "A" | "B", "undone": False}   # a scored point
{"type": "let",   "scorer": None,     "undone": False}    # net on serve — no score, no rotation
```

Any event with `"undone": True` is ignored by the engine (that's how the
scorer's "↶ Undo" button works — it soft-deletes rather than replaying).

### Fields returned by `compute_state`

Read-friendly shape (see [`app/logic.py`](app/logic.py) for authority):

| Field | Meaning |
|-------|---------|
| `a_score`, `b_score` | Current game score |
| `a_games`, `b_games` | Games won so far |
| `games` | List of completed games `{game_num, a, b, winner}` |
| `current_game_num` | 1-indexed |
| `is_deuce` | True once both scores ≥ `points_to_win - 1` |
| `is_deciding_game` | True when both teams are one game away from winning |
| `match_type`, `is_doubles` | `"singles"` / `"doubles"` |
| `server`, `receiver` | `"A"` / `"B"` |
| `server_side`, `receiver_side` | `1` / `2` (doubles only) |
| `server_name`, `receiver_name` | Resolved display names |
| `service_change` | True on the point where serve just flipped |
| `side_change_alert` | True on the point that triggers the deciding-game change-ends |
| `ends_swapped` | True after ends have been swapped in the current deciding game |
| `let_count` | Number of lets recorded so far in the match |
| `total_points` | Non-let, non-undone points played |
| `match_winner` | `"A"` / `"B"` / `""` |
| `history` | Chronological summary per point/let |

---

## 3. Manual (hands-on) test walkthroughs

Every automated rule can also be verified by hand from the UI. Bring up a
local dev server and click through these scenarios.

```bash
export AWS_REGION=eu-west-1
python setup_db.py           # only the first time
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

Then open <http://localhost:8002> and log in as `admin / admin`.

### 3.1 Singles — basic serve rotation

1. Create a match: Alice vs Bob, Bo3, points 11, service interval 2, deuce interval 1.
2. Tap "Point for Alice" twice → banner **🔁 Service change** appears, "Next Serve" flips to Bob.
3. Two more points → banner appears again, serve flips back.

**Pass** if the banner fires exactly on points 2, 4, 6, … (and never in between).

### 3.2 Singles — deuce

1. Score 10–10 → **DEUCE** badge appears.
2. Now serve flips **every single point**.
3. Score to 12–10 → game ends, winner recorded, new game starts.

**Pass** if 11–10 does *not* end the game and the winner needs to be ahead by 2.

### 3.3 Singles — match winner

1. Bo3 → first to 2 games wins.
2. Score 2 games straight for Alice → 🏆 banner on scoreboard + game live board.

### 3.4 Doubles — full rotation

1. Create a match: match type = **Doubles**, A1 = Alice, A2 = Amy, B1 = Bob, B2 = Ben. First server = A, first server side = 1, first receiver side = 1.
2. Score points slowly and watch the **Next Serve** and **↳ receiving** lines:

   | Points played | Server | Receiver |
   |---:|---|---|
   | 0 | Alice | Bob |
   | 2 | Bob   | Amy |
   | 4 | Amy   | Ben |
   | 6 | Ben   | Alice |
   | 8 | Alice | Bob |

**Pass** if the cycle `Alice → Bob → Amy → Ben → Alice` repeats. This is the ITTF rule (next server = current receiver; next receiver = partner of previous server).

### 3.5 Let (net on serve)

1. From the scoreboard, tap **🌐 Let**.
2. Neither score changes; server does **not** advance; a flash `🌐 Let — serve replayed` appears.
3. Match summary (after games end) shows `let_count` incremented.

### 3.6 Deciding-game change ends

1. Configure `deciding_side_change_at = 5` (admin panel or per-match).
2. Play a Bo3 to 1–1 in games → next game is the **deciding** game (`DECIDING` badge).
3. Score to 5–0 (leader reaches 5) → **🔀 CHANGE ENDS** banner + haptic pulse on mobile.
4. Continue playing → banner appears **only once** per deciding game.

**Doubles variant**: in step 3 the receiving side is auto-swapped (verify by checking the receiver name flips to the current-receiver's partner).

**Disable check**: set `deciding_side_change_at = 0` → banner never fires.

### 3.7 Undo

1. Score a few points, tap **↶ Undo**.
2. The last non-undone event is soft-deleted; scores roll back one step.
3. Undo across a game boundary → the completed game re-opens.

### 3.8 Public per-match live link

- Copy the `/live/{match_id}` URL from the scoreboard footer.
- Open in a private window → read-only, refreshes every 5 s.

### 3.9 Public tournament-wide live board

1. Create a tournament, add participants (bulk paste one name per line), add a round, add 2–3 pairings (mix singles + doubles), tap **▶️ Start** on one or two.
2. Open the **🌐 Open** button at the top of the tournament page (or copy the link).
3. Verify:
   - Each match shows a **SINGLES** or **DOUBLES** badge and its current score.
   - Started matches show **🔴 LIVE** and are clickable → drills into `/live/{match_id}`.
   - Unstarted matches show **⏳ PENDING** and are not clickable.
   - Finished matches show **✅ FINAL** and the winner name.
4. Board auto-refreshes every 10 s.

### 3.10 Edit / delete pairings

1. In the tournament page, on any pairing **that has not been started**, tap **✏️ Edit** → an amber panel opens.
2. Switch match type between Singles / Doubles, change any player, tap **💾 Save pairing** → the pair updates in place.
3. Tap **🗑️** on a pending pair → confirms and removes.
4. After you tap **▶️ Start** on a pair, the Edit and Delete buttons disappear — protects event history.

---

## 4. Configuration reference

Three layers of config, in override order (later beats earlier):

```
DEFAULT_SETTINGS (code)
  ↓
tt_settings row (admin panel)                  ← global defaults for new matches
  ↓
tournament row (POST /tournaments)             ← inherits from global; per-tournament override
  ↓
match row (POST /matches or start_pair_match)  ← per-match final say
```

### 4.1 Global defaults — `tt_settings` (admin panel → *Scoring Defaults*)

Set via `POST /admin/settings`. Stored in [`app/db.py`](app/db.py) `DEFAULT_SETTINGS`.

| Key | Type | Default | Constraint | Meaning |
|---|---|---:|---|---|
| `default_best_of` | int | `5` | `1`, `3`, `5`, `7` | Games needed to win a match (Bo). |
| `default_points_to_win` | int | `11` | ≥ `5` | Points in a normal game (before deuce). |
| `service_interval` | int | `2` | ≥ `1` | Serve rotates every N points. |
| `deuce_interval` | int | `1` | ≥ `1` | Serve rotates every N points at deuce. |
| `default_match_type` | str | `"singles"` | `singles` \| `doubles` | Default for new matches. |
| `deciding_side_change_at` | int | `5` | ≥ `0` (0 disables) | Deciding-game change-ends threshold. |

### 4.2 Per-tournament overrides — `POST /tournaments`

Any field left blank / `0` inherits from `tt_settings`.

| Form field | Type | Notes |
|---|---|---|
| `name` | str | Required. |
| `best_of` | int | Same constraint as `default_best_of`. |
| `points_to_win` | int | Same constraint as `default_points_to_win`. |
| `service_interval` | int | Optional. |
| `deuce_interval` | int | Optional. |

Every match spun up from this tournament (via `▶️ Start`) inherits these
values automatically.

### 4.3 Per-pairing (inside a tournament)

`POST /tournaments/{tid}/rounds/{n}/pairs` (or `/pairs/bulk` or `/pairs/{slot}/edit`).

| Form field | Type | Meaning |
|---|---|---|
| `match_type` | `singles` \| `doubles` | Doubles requires 4 distinct participants. |
| `participant_a`, `participant_b` | participant IDs | Required. |
| `participant_a2`, `participant_b2` | participant IDs | Required when `match_type=doubles`. |

### 4.4 Per-match overrides — `POST /matches`

Every value that's left `0` (or `-1` for `deciding_side_change_at`) is filled
in from `tt_settings`.

| Form field | Type | Default source | Notes |
|---|---|---|---|
| `name` | str | — | Required. |
| `match_type` | str | `default_match_type` | `singles` \| `doubles`. |
| `player_a`, `player_b` | str | — | Required. |
| `player_a2`, `player_b2` | str | — | **Required if** `match_type=doubles`. |
| `best_of` | int | `default_best_of` | 1/3/5/7. |
| `points_to_win` | int | `default_points_to_win` | ≥ 5. |
| `service_interval` | int | `service_interval` | ≥ 1. |
| `deuce_interval` | int | `deuce_interval` | ≥ 1. |
| `deciding_side_change_at` | int | `deciding_side_change_at` | 0 disables; `-1` inherits. |
| `first_server` | `A` \| `B` | `A` | Who serves the first game. |
| `first_server_side` | 1 \| 2 | 1 | Doubles only. |
| `first_receiver_side` | 1 \| 2 | 1 | Doubles only. |
| `tournament_id`, `round_num`, `match_slot` | — | — | Set automatically by tournament start. |

### 4.5 Bulk-pairings grammar (per line)

Used by `POST /tournaments/{tid}/rounds/{n}/pairs/bulk`.

```
Alice vs Bob                (singles)
Charlie - Dave              (singles, dash separator)
Eve | Frank                 (singles, pipe separator)
Alice + Amy vs Bob + Ben    (doubles, plus)
Alice & Amy vs Bob & Ben    (doubles, ampersand)
Alice / Amy vs Bob / Ben    (doubles, slash)
# comment lines start with # and are ignored
```

- Side separator (case-insensitive): `vs`, `vs.`, `v`, `v.`, `-`, `—`, `|`.
- Doubles partner separator: `+`, `&`, `/`.
- Names are matched **case-insensitively** to already-added participants. Unknown names are skipped and reported in the flash message.
- Mixed sides (`Alice vs Bob + Ben`) are rejected.
- More than 2 players on a side is rejected.

### 4.6 Environment variables

| Var | Default | Purpose |
|---|---|---|
| `AWS_REGION` | `eu-west-1` | DynamoDB region. |
| `MATCHES_TABLE` | `tt_matches` | Table name. |
| `EVENTS_TABLE` | `tt_events` | Table name. |
| `USERS_TABLE` | `tt_users` | Table name. |
| `TOURNAMENTS_TABLE` | `tt_tournaments` | Table name. |
| `SETTINGS_TABLE` | `tt_settings` | Table name. |
| `ROSTER_TABLE` | `tt_roster` | Table name. |

Override any of these when running against alternate infrastructure (e.g. a
staging region or a DynamoDB Local instance).

---

## 5. Troubleshooting

- **`No module named pytest`** — activate `.venv` and reinstall dev deps:
  `pip install -r requirements-dev.txt`.
- **`No module named app`** — always run `pytest` from the repo root so
  `app/` is importable.
- **AWS errors during `pytest`** — should never happen; the engine tests
  don't call the DB. If they do, something imports `app.main` at
  collection time; check `sys.path` and imports.
- **A rule test suddenly fails after editing `app/logic.py`** — read the
  assertion carefully; the tests describe expected behaviour precisely
  (score, server, receiver, flags). Fix the engine, not the test, unless
  you're deliberately changing a rule.
- **UI banner doesn't fire manually but the test passes** — check the
  template still reads the same `state.*` key (e.g. `state.side_change_alert`).
  Renaming a key in `logic.py` needs a matching template update.
