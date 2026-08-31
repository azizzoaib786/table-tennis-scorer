import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from typing import Any, Dict, List, Optional

# AWS configuration
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
MATCHES_TABLE = os.getenv("MATCHES_TABLE", "tt_matches")
EVENTS_TABLE = os.getenv("EVENTS_TABLE", "tt_events")
USERS_TABLE = os.getenv("USERS_TABLE", "tt_users")
TOURNAMENTS_TABLE = os.getenv("TOURNAMENTS_TABLE", "tt_tournaments")
SETTINGS_TABLE = os.getenv("SETTINGS_TABLE", "tt_settings")
ROSTER_TABLE = os.getenv("ROSTER_TABLE", "tt_roster")

ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
matches = ddb.Table(MATCHES_TABLE)
events = ddb.Table(EVENTS_TABLE)
users = ddb.Table(USERS_TABLE)
tournaments = ddb.Table(TOURNAMENTS_TABLE)
settings_tbl = ddb.Table(SETTINGS_TABLE)
roster_tbl = ddb.Table(ROSTER_TABLE)


# ── Matches ───────────────────────────────────────────────────────────────────
def put_match(item: Dict[str, Any]) -> None:
    matches.put_item(Item=item)


def get_match(match_id: str) -> Optional[Dict[str, Any]]:
    resp = matches.get_item(Key={"match_id": match_id})
    return resp.get("Item")


def list_matches(limit: int = 50) -> List[Dict[str, Any]]:
    resp = matches.scan(Limit=limit)
    items = resp.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def list_matches_by_user(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    resp = matches.scan(
        FilterExpression="user_id = :uid",
        ExpressionAttributeValues={":uid": user_id},
        Limit=limit,
    )
    items = resp.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def update_match(match_id: str, update_expr: str, expr_vals: Dict[str, Any],
                 expr_names: Optional[Dict[str, str]] = None) -> None:
    kwargs = dict(
        Key={"match_id": match_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_vals,
    )
    if expr_names:
        kwargs["ExpressionAttributeNames"] = expr_names
    matches.update_item(**kwargs)


def delete_match(match_id: str) -> None:
    matches.delete_item(Key={"match_id": match_id})
    ev = list_events(match_id)
    for e in ev:
        events.delete_item(Key={"match_id": match_id, "ts": e["ts"]})


# ── Events (points) ───────────────────────────────────────────────────────────
def put_event(item: Dict[str, Any]) -> None:
    events.put_item(Item=item)


def list_events(match_id: str) -> List[Dict[str, Any]]:
    resp = events.query(
        KeyConditionExpression=Key("match_id").eq(match_id),
        ScanIndexForward=True,
    )
    return resp.get("Items", [])


def delete_last_event(match_id: str) -> Optional[Dict[str, Any]]:
    """Delete most recent non-undone event; return it or None."""
    ev = list_events(match_id)
    for e in reversed(ev):
        if not e.get("undone"):
            events.delete_item(Key={"match_id": match_id, "ts": e["ts"]})
            return e
    return None


# ── Users ─────────────────────────────────────────────────────────────────────
def create_user(user_id: str, username: str, password_hash: str,
                is_admin: bool = False, email: str = "", role: str = "scorer") -> None:
    users.put_item(Item={
        "user_id": user_id,
        "username": username,
        "password_hash": password_hash,
        "is_admin": is_admin,
        "is_active": is_admin,
        "email": email,
        "role": role,
        "stat_matches_played": 0,
        "stat_matches_won": 0,
        "stat_games_played": 0,
        "stat_games_won": 0,
        "stat_points_scored": 0,
    })


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    resp = users.scan(
        FilterExpression="username = :u",
        ExpressionAttributeValues={":u": username},
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    resp = users.get_item(Key={"user_id": user_id})
    return resp.get("Item")


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    resp = users.scan(FilterExpression=Attr("email").eq(email))
    items = resp.get("Items", [])
    return items[0] if items else None


def list_all_users() -> List[Dict[str, Any]]:
    return users.scan().get("Items", [])


def delete_user(user_id: str) -> None:
    users.delete_item(Key={"user_id": user_id})


def update_user_password(user_id: str, new_password_hash: str) -> None:
    users.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET password_hash = :ph",
        ExpressionAttributeValues={":ph": new_password_hash},
    )


def set_user_must_change_password(user_id: str, flag: bool) -> None:
    """Force (or clear) a mandatory password change on the user's next login."""
    users.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET must_change_password = :f",
        ExpressionAttributeValues={":f": bool(flag)},
    )


def toggle_user_active(user_id: str, is_active: bool) -> None:
    users.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET is_active = :a",
        ExpressionAttributeValues={":a": is_active},
    )


def set_user_role(user_id: str, role: str) -> None:
    users.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #r = :r",
        ExpressionAttributeNames={"#r": "role"},
        ExpressionAttributeValues={":r": role},
    )


def search_users(query: str, exclude_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    exclude_ids = exclude_ids or []
    resp = users.scan()
    q = query.lower()
    results = [
        {"user_id": u["user_id"], "username": u["username"]}
        for u in resp.get("Items", [])
        if q in u.get("username", "").lower() and u["user_id"] not in exclude_ids
    ]
    return results[:10]


def update_user_stats(user_id: str, match_won: bool, games_played: int,
                       games_won: int, points_scored: int) -> None:
    users.update_item(
        Key={"user_id": user_id},
        UpdateExpression=(
            "ADD stat_matches_played :one, stat_matches_won :mw, "
            "stat_games_played :gp, stat_games_won :gw, stat_points_scored :ps"
        ),
        ExpressionAttributeValues={
            ":one": 1,
            ":mw": 1 if match_won else 0,
            ":gp": int(games_played),
            ":gw": int(games_won),
            ":ps": int(points_scored),
        },
    )


# ── Tournaments ───────────────────────────────────────────────────────────────
def put_tournament(item: Dict[str, Any]) -> None:
    tournaments.put_item(Item=item)


def get_tournament(tournament_id: str) -> Optional[Dict[str, Any]]:
    resp = tournaments.get_item(Key={"tournament_id": tournament_id})
    return resp.get("Item")


def list_tournaments(limit: int = 50) -> List[Dict[str, Any]]:
    resp = tournaments.scan(Limit=limit)
    items = resp.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def list_tournaments_by_user(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    resp = tournaments.scan(
        FilterExpression="user_id = :uid",
        ExpressionAttributeValues={":uid": user_id},
        Limit=limit,
    )
    items = resp.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def update_tournament(tournament_id: str, update_expr: str, expr_vals: Dict[str, Any]) -> None:
    tournaments.update_item(
        Key={"tournament_id": tournament_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_vals,
    )


def delete_tournament(tournament_id: str) -> None:
    tournaments.delete_item(Key={"tournament_id": tournament_id})


# ── Settings (single global config item, config_id = "global") ────────────────
DEFAULT_SETTINGS: Dict[str, Any] = {
    "config_id": "global",
    "default_best_of": 5,
    "default_points_to_win": 11,
    "service_interval": 2,   # normal serve rotates every N points
    "deuce_interval": 1,     # at deuce serve rotates every N points
    "default_match_type": "singles",  # "singles" | "doubles"
    "deciding_side_change_at": 5,     # ends change at N pts in the deciding game (0 disables)
    "hard_cap_enabled": False,        # if True, first to hard_cap_at wins (overrides win-by-2)
    "hard_cap_at": 15,                # score at which hard cap triggers
}


def get_settings() -> Dict[str, Any]:
    resp = settings_tbl.get_item(Key={"config_id": "global"})
    item = resp.get("Item") or {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in item.items() if v is not None})
    # Cast numeric fields
    for k in ("default_best_of", "default_points_to_win", "service_interval",
              "deuce_interval", "deciding_side_change_at"):
        try:
            merged[k] = int(merged[k])
        except Exception:
            merged[k] = int(DEFAULT_SETTINGS[k])
    if merged.get("default_match_type") not in ("singles", "doubles"):
        merged["default_match_type"] = "singles"
    # Hard-cap fields
    merged["hard_cap_enabled"] = bool(merged.get("hard_cap_enabled", False))
    try:
        merged["hard_cap_at"] = int(merged.get("hard_cap_at", 15))
    except Exception:
        merged["hard_cap_at"] = 15
    return merged


def update_settings(new_values: Dict[str, Any]) -> None:
    """Upsert the single global settings row."""
    item = dict(DEFAULT_SETTINGS)
    existing = settings_tbl.get_item(Key={"config_id": "global"}).get("Item") or {}
    item.update(existing)
    item.update(new_values)
    item["config_id"] = "global"
    settings_tbl.put_item(Item=item)


# ── Roster (admin-managed player pool used by tournaments) ────────────────────
def add_roster_player(player_id: str, name: str, user_id: str = "") -> None:
    roster_tbl.put_item(Item={
        "player_id": player_id,
        "name": name,
        "user_id": user_id or "",
    })


def list_roster() -> List[Dict[str, Any]]:
    resp = roster_tbl.scan()
    items = resp.get("Items", [])
    items.sort(key=lambda x: x.get("name", "").lower())
    return items


def delete_roster_player(player_id: str) -> None:
    roster_tbl.delete_item(Key={"player_id": player_id})


def get_roster_player(player_id: str) -> Optional[Dict[str, Any]]:
    resp = roster_tbl.get_item(Key={"player_id": player_id})
    return resp.get("Item")
