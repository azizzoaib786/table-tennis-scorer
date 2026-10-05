#!/usr/bin/env python3
"""Seed a TEST tournament: 24 singles players, 4 pools of 6, all pool matches
already decided. Stops right before the knockout so you can create the
"Round of 16" in the UI and validate the rest of the flow.

Usage (same AWS env/region as the app):
    python seed_test_tournament.py            # create
    python seed_test_tournament.py --delete   # remove all tournaments created by this script
"""
import random
import sys
import uuid
from datetime import datetime, timezone

from app import db
from app.main import _round_robin_pairings

NAME = "TEST - 24 teams doubles (safe to delete)"
GROUPS = ["Pool A", "Pool B", "Pool C", "Pool D"]
TEAMS_PER_GROUP = 6


def _owner_id() -> str:
    resp = db.users.scan()
    items = resp.get("Items", [])
    admin = next((u for u in items if u.get("username") == "admin"), None) \
        or next((u for u in items if u.get("is_admin")), None)
    if not admin:
        sys.exit("No admin user found")
    return admin["user_id"]


def delete_all() -> None:
    for t in db.list_tournaments(limit=500):
        if t.get("is_test_seed"):
            db.delete_tournament(t["tournament_id"])
            print("Deleted", t["tournament_id"])


def create() -> None:
    rnd = random.Random(42)
    cfg = db.get_settings()
    participants = [
        {"id": uuid.uuid4().hex[:8], "name": f"Player {i:02d}", "user_id": ""}
        for i in range(1, len(GROUPS) * TEAMS_PER_GROUP * 2 + 1)
    ]
    # Doubles: consecutive players form a team (1+2, 3+4, ...).
    teams_all = [participants[i:i + 2] for i in range(0, len(participants), 2)]
    rounds = []
    for g, gname in enumerate(GROUPS):
        team = teams_all[g * TEAMS_PER_GROUP:(g + 1) * TEAMS_PER_GROUP]
        matches = []
        slot = 1
        for pairs in _round_robin_pairings(len(team)):
            for i, j in pairs:
                a, b = team[i], team[j]
                a_wins = rnd.random() < (0.5 + (j - i) * 0.08)
                win_pts = 33
                lose_pts = rnd.randint(15, 31)
                winner_team = a if a_wins else b
                matches.append({
                    "slot": slot, "match_type": "doubles",
                    "a_name": a[0]["name"], "a_id": a[0]["id"],
                    "a2_name": a[1]["name"], "a2_id": a[1]["id"],
                    "b_name": b[0]["name"], "b_id": b[0]["id"],
                    "b2_name": b[1]["name"], "b2_id": b[1]["id"],
                    "table_number": (slot - 1) % int(cfg.get("default_num_tables", 6)) + 1,
                    "match_id": "",
                    "winner": "A" if a_wins else "B",
                    "winner_name": f"{winner_team[0]['name']} & {winner_team[1]['name']}",
                    "a_points": win_pts if a_wins else lose_pts,
                    "b_points": lose_pts if a_wins else win_pts,
                })
                slot += 1
        rounds.append({"round_num": g + 1, "name": gname, "stage_type": "pool", "matches": matches})

    tid = uuid.uuid4().hex
    db.put_tournament({
        "tournament_id": tid,
        "name": NAME,
        "best_of": int(cfg["default_best_of"]),
        "points_to_win": int(cfg["default_points_to_win"]),
        "service_interval": int(cfg["service_interval"]),
        "deuce_interval": int(cfg["deuce_interval"]),
        "num_tables": int(cfg["default_num_tables"]),
        "qualify_per_group": 4,
        "user_id": _owner_id(),
        "scorer_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "participants": participants,
        "rounds": rounds,
        "format": "doubles",
        "status": "registration",
        "is_test_seed": True,
    })
    print(f"Created '{NAME}': /tournaments/{tid}")
    print("Next: Add Round -> 'Round of 16' (Knockout), then pick pairings from the 16 qualifiers.")


if __name__ == "__main__":
    delete_all() if "--delete" in sys.argv else create()
