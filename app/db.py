import os
import uuid
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from boto3.dynamodb.types import TypeSerializer
from typing import Any, Dict, List, Optional

# AWS configuration
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
MATCHES_TABLE = os.getenv("MATCHES_TABLE", "tt_matches")
EVENTS_TABLE = os.getenv("EVENTS_TABLE", "tt_events")
USERS_TABLE = os.getenv("USERS_TABLE", "tt_users")
TOURNAMENTS_TABLE = os.getenv("TOURNAMENTS_TABLE", "tt_tournaments")
SETTINGS_TABLE = os.getenv("SETTINGS_TABLE", "tt_settings")
ROSTER_TABLE = os.getenv("ROSTER_TABLE", "tt_roster")
REGISTRATIONS_TABLE = os.getenv("REGISTRATIONS_TABLE", "tt_registrations")
PRACTICE_BOOKINGS_TABLE = os.getenv("PRACTICE_BOOKINGS_TABLE", "tt_practice_bookings")

ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
matches = ddb.Table(MATCHES_TABLE)
events = ddb.Table(EVENTS_TABLE)
users = ddb.Table(USERS_TABLE)
tournaments = ddb.Table(TOURNAMENTS_TABLE)
settings_tbl = ddb.Table(SETTINGS_TABLE)
roster_tbl = ddb.Table(ROSTER_TABLE)
registrations_tbl = ddb.Table(REGISTRATIONS_TABLE)
practice_bookings_tbl = ddb.Table(PRACTICE_BOOKINGS_TABLE)


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


def list_matches_by_tournament(tournament_id: str) -> List[Dict[str, Any]]:
    """Return every match belonging to a tournament (paginated scan)."""
    items: List[Dict[str, Any]] = []
    kwargs = {
        "FilterExpression": "tournament_id = :tid",
        "ExpressionAttributeValues": {":tid": tournament_id},
    }
    while True:
        resp = matches.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
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


def set_user_admin(user_id: str, is_admin: bool) -> None:
    """Grant or revoke admin rights for a user."""
    users.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET is_admin = :f",
        ExpressionAttributeValues={":f": bool(is_admin)},
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


def list_tournaments_for_scorer(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Tournaments visible to a scorer: ones they created OR were assigned to via
    scorer_ids. Scans and filters in Python (list stays small; no GSI needed)."""
    resp = tournaments.scan(Limit=limit)
    items = []
    for t in resp.get("Items", []):
        if t.get("user_id") == user_id:
            items.append(t)
            continue
        sids = t.get("scorer_ids") or []
        if user_id in sids:
            items.append(t)
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def update_tournament(tournament_id: str, update_expr: str, expr_vals: Dict[str, Any],
                      expr_names: Optional[Dict[str, str]] = None) -> None:
    kwargs: Dict[str, Any] = {
        "Key": {"tournament_id": tournament_id},
        "UpdateExpression": update_expr,
        "ExpressionAttributeValues": expr_vals,
    }
    if expr_names:
        kwargs["ExpressionAttributeNames"] = expr_names
    tournaments.update_item(**kwargs)


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


# ── Tournament registrations (public sign-up to play) ─────────────────────────
def put_registration(item: Dict[str, Any]) -> None:
    registrations_tbl.put_item(Item=item)


_dynamo_serializer = TypeSerializer()


def put_registrations_transact(items: List[Dict[str, Any]]) -> None:
    """Atomically write multiple registration rows (e.g. a doubles pair's
    primary + partner) in a single DynamoDB transaction. Either every row
    commits or none do — prevents an orphaned "half a pair" registration if
    a photo upload, network blip, or process crash interrupts the write
    partway through. Each item must already contain a unique
    `registration_id` (we guard against silently overwriting one with a
    ConditionExpression, though uuid4 collisions are effectively impossible).
    """
    if not items:
        return
    if len(items) == 1:
        # Single-row writes don't need a transaction — plain put_item is
        # cheaper and this keeps singles registrations on the simple path.
        put_registration(items[0])
        return
    client = ddb.meta.client
    transact_items = [
        {
            "Put": {
                "TableName": REGISTRATIONS_TABLE,
                "Item": {k: _dynamo_serializer.serialize(v) for k, v in item.items()},
                "ConditionExpression": "attribute_not_exists(registration_id)",
            }
        }
        for item in items
    ]
    client.transact_write_items(TransactItems=transact_items)


def get_registration(registration_id: str) -> Optional[Dict[str, Any]]:
    resp = registrations_tbl.get_item(Key={"registration_id": registration_id})
    return resp.get("Item")


def list_registrations_by_tournament(tournament_id: str) -> List[Dict[str, Any]]:
    resp = registrations_tbl.scan(
        FilterExpression="tournament_id = :tid",
        ExpressionAttributeValues={":tid": tournament_id},
    )
    items = resp.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""))
    return items


def list_all_registrations() -> List[Dict[str, Any]]:
    resp = registrations_tbl.scan()
    items = resp.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def find_registration_by_its(its: str) -> Optional[Dict[str, Any]]:
    """Return the first registration (across all tournaments) whose primary
    `its` or `partner_its` equals the given ITS ID. ITS IDs are globally
    unique per player, so this is used to reject re-registration attempts."""
    key = (its or "").strip()
    if not key:
        return None
    resp = registrations_tbl.scan(
        FilterExpression="its = :i OR partner_its = :i",
        ExpressionAttributeValues={":i": key},
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def update_registration_paid(registration_id: str, paid: bool) -> None:
    registrations_tbl.update_item(
        Key={"registration_id": registration_id},
        UpdateExpression="SET payment_done = :p",
        ExpressionAttributeValues={":p": bool(paid)},
    )


def delete_registration(registration_id: str) -> None:
    registrations_tbl.delete_item(Key={"registration_id": registration_id})


def find_registration_by_name(tournament_id: str, name: str) -> Optional[Dict[str, Any]]:
    """Case-insensitive lookup used to auto-link photos to a match."""
    key = (name or "").strip().lower()
    if not key:
        return None
    for r in list_registrations_by_tournament(tournament_id):
        if r.get("name", "").strip().lower() == key:
            return r
    return None


# ── Practice slot bookings (standalone flow — separate from tournaments
# and live scoring) ───────────────────────────────────────────────────────────
# Capacity is enforced with a conditional put on a composite "slot_key"
# (date#start-end#slot_no), so two people racing for the last open slot
# can never both win it — DynamoDB rejects the loser's write atomically.
PRACTICE_SLOTS_PER_HOUR = 6
PRACTICE_TIME_RANGES = [("10:00", "11:00"), ("11:00", "12:00"), ("12:00", "13:00")]


def _practice_slot_key(date: str, start_time: str, end_time: str, slot_no: int) -> str:
    return f"{date}#{start_time}-{end_time}#{slot_no}"


def create_practice_booking(date: str, start_time: str, end_time: str, name: str,
                            phone: str) -> Optional[Dict[str, Any]]:
    """Try to claim the first free slot (1..6) for this date/time range.
    Returns the created booking dict, or None if the time range is full."""
    booking_id = uuid.uuid4().hex
    reference_number = ("PB" + booking_id[:6]).upper()
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    for slot_no in range(1, PRACTICE_SLOTS_PER_HOUR + 1):
        item = {
            "slot_key": _practice_slot_key(date, start_time, end_time, slot_no),
            "booking_id": booking_id,
            "reference_number": reference_number,
            "name": name,
            "phone": phone,
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "slot_no": slot_no,
            "created_at": created_at,
        }
        try:
            practice_bookings_tbl.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(slot_key)",
            )
            return item
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                continue
            raise
    return None


def get_practice_booking_by_reference(reference_number: str) -> Optional[Dict[str, Any]]:
    key = (reference_number or "").strip().upper()
    if not key:
        return None
    resp = practice_bookings_tbl.scan(
        FilterExpression="reference_number = :r",
        ExpressionAttributeValues={":r": key},
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def list_all_practice_bookings() -> List[Dict[str, Any]]:
    resp = practice_bookings_tbl.scan()
    items = resp.get("Items", [])
    items.sort(key=lambda x: (x.get("date", ""), x.get("start_time", ""), x.get("slot_no", 0)))
    return items


def search_practice_bookings(query: str) -> List[Dict[str, Any]]:
    """Admin search across name/phone/reference number (in-memory filter —
    booking volume for a single club's practice sessions is small)."""
    q = (query or "").strip().lower()
    if not q:
        return list_all_practice_bookings()
    return [
        b for b in list_all_practice_bookings()
        if q in b.get("name", "").strip().lower()
        or q in b.get("phone", "").strip().lower()
        or q in b.get("reference_number", "").strip().lower()
    ]


def get_practice_slot_availability(date: str) -> Dict[str, int]:
    """Return {"10:00-11:00": booked_count, ...} for the given date."""
    resp = practice_bookings_tbl.scan(
        FilterExpression="#d = :d",
        ExpressionAttributeNames={"#d": "date"},
        ExpressionAttributeValues={":d": date},
    )
    items = resp.get("Items", [])
    counts: Dict[str, int] = {f"{s}-{e}": 0 for s, e in PRACTICE_TIME_RANGES}
    for b in items:
        key = f"{b.get('start_time')}-{b.get('end_time')}"
        if key in counts:
            counts[key] += 1
    return counts


def delete_practice_booking(slot_key: str) -> None:
    practice_bookings_tbl.delete_item(Key={"slot_key": slot_key})


def delete_practice_booking_by_id(booking_id: str) -> None:
    """Admin delete by booking_id (URL-safe), avoiding the '#' characters
    in slot_key which don't survive cleanly as a URL path segment."""
    resp = practice_bookings_tbl.scan(
        FilterExpression="booking_id = :b",
        ExpressionAttributeValues={":b": booking_id},
    )
    for item in resp.get("Items", []):
        practice_bookings_tbl.delete_item(Key={"slot_key": item["slot_key"]})


# Admin-managed date ranges open for practice booking. Stored as its own row
# in the settings table (config_id = "practice_booking") so it stays separate
# from the scoring defaults. A single day is a range with start == end.
# Until an admin saves a list, the default applies.
PRACTICE_CONFIG_ID = "practice_booking"
DEFAULT_PRACTICE_DATE_RANGES = [{"start": "2026-10-11", "end": "2026-10-11"}]


def get_practice_date_ranges() -> List[Dict[str, str]]:
    item = settings_tbl.get_item(Key={"config_id": PRACTICE_CONFIG_ID}).get("Item")
    if not item:
        return [dict(r) for r in DEFAULT_PRACTICE_DATE_RANGES]
    if "date_ranges" in item:
        ranges = [{"start": str(r["start"]), "end": str(r["end"])} for r in item["date_ranges"]]
    elif "allowed_dates" in item:
        # Legacy format (individual dates) -> single-day ranges.
        ranges = [{"start": str(d), "end": str(d)} for d in item["allowed_dates"]]
    else:
        return [dict(r) for r in DEFAULT_PRACTICE_DATE_RANGES]
    return sorted(ranges, key=lambda r: (r["start"], r["end"]))


def set_practice_date_ranges(ranges: List[Dict[str, str]]) -> None:
    unique = {(str(r["start"]), str(r["end"])) for r in ranges}
    settings_tbl.put_item(Item={
        "config_id": PRACTICE_CONFIG_ID,
        "date_ranges": [{"start": s, "end": e} for s, e in sorted(unique)],
    })


def is_practice_date_open(date: str, ranges: List[Dict[str, str]]) -> bool:
    """YYYY-MM-DD strings compare correctly as plain strings."""
    return any(r["start"] <= date <= r["end"] for r in ranges)
