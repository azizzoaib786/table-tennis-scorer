"""Table tennis scoring logic (singles + doubles, ITTF-compliant).

All rules are configurable per match:
  - Points per game (default 11), win by 2.
  - Best of N games (1, 3, 5, 7). First to (N // 2 + 1) games wins the match.
  - Service alternates every ``service_interval`` points (default 2), and every
    ``deuce_interval`` points (default 1) once both scores are >= (points_to_win - 1).
  - In the deciding game, ends change when the leader reaches
    ``deciding_side_change_at`` points (default 5, set 0 to disable).
  - Singles: server alternates between team A and B; first server alternates each game.
  - Doubles: serve rotates player-by-player (e.g. A1 -> B1 -> A2 -> B2 -> A1 ...).
    When ends change in the deciding game, the receiving pair swap positions.

Events (from ``list_events``):
  - ``scorer`` in {"A", "B"}: team that won the rally.
  - ``type`` == "let": a let (net on serve) - no score/serve change.
  - ``undone`` bool: soft-deleted events are ignored.
"""
from typing import Dict, List, Optional, Tuple


def _live_events(all_events: List[dict]) -> List[dict]:
    return [e for e in all_events if not e.get("undone")]


def _team_players(match: dict, team: str) -> Tuple[str, str]:
    """Return (side1_name, side2_name) for the given team letter."""
    if team == "A":
        return match.get("player_a", "Player A"), match.get("player_a2", "Player A2")
    return match.get("player_b", "Player B"), match.get("player_b2", "Player B2")


def _player_display(match: dict, team: str, side: Optional[int]) -> str:
    """Human-friendly name for the (team, side) pair."""
    if side is None:
        return match.get("player_a", "Player A") if team == "A" else match.get("player_b", "Player B")
    p1, p2 = _team_players(match, team)
    return p1 if side == 1 else p2


def _other_team(team: str) -> str:
    return "B" if team == "A" else "A"


def _other_side(side: int) -> int:
    return 2 if side == 1 else 1


def compute_state(match: dict, all_events: List[dict]) -> dict:
    """Derive full match state from the event log."""
    points_to_win = int(match.get("points_to_win", 11))
    best_of = int(match.get("best_of", 5))
    service_interval = max(1, int(match.get("service_interval", 2)))
    deuce_interval = max(1, int(match.get("deuce_interval", 1)))
    deciding_side_change_at = int(match.get("deciding_side_change_at", 5))
    hard_cap_enabled = bool(match.get("hard_cap_enabled", False))
    hard_cap_at = int(match.get("hard_cap_at", 15))
    target_games = best_of // 2 + 1
    match_type = match.get("match_type", "singles")
    is_doubles = match_type == "doubles"

    first_server: str = match.get("first_server", "A")
    first_server_side = int(match.get("first_server_side", 1)) if is_doubles else None
    first_receiver_side = int(match.get("first_receiver_side", 1)) if is_doubles else None

    ev = _live_events(all_events)

    games: List[dict] = []
    a_games = 0
    b_games = 0
    a_score = 0
    b_score = 0
    game_num = 1
    match_winner: Optional[str] = None

    server = first_server
    server_side: Optional[int] = first_server_side
    receiver: str = _other_team(server)
    receiver_side: Optional[int] = first_receiver_side
    points_since_serve_change = 0
    ends_swapped_this_game = False
    point_history: List[dict] = []
    let_count = 0

    def is_deciding_game_now() -> bool:
        return (a_games == target_games - 1) and (b_games == target_games - 1)

    for e in ev:
        if match_winner:
            break
        # Lets don't affect score or serve.
        if e.get("type") == "let":
            let_count += 1
            point_history.append({
                "ts": e.get("ts"),
                "kind": "let",
                "game_num": game_num,
                "a": a_score,
                "b": b_score,
                "server_after": server,
                "server_side_after": server_side,
            })
            continue
        scorer = e.get("scorer")
        if scorer not in ("A", "B"):
            continue

        prev_server = server
        prev_server_side = server_side
        prev_receiver = receiver
        prev_receiver_side = receiver_side

        if scorer == "A":
            a_score += 1
        else:
            b_score += 1
        points_since_serve_change += 1

        is_deuce_now = (a_score >= points_to_win - 1) and (b_score >= points_to_win - 1)
        interval = deuce_interval if is_deuce_now else service_interval

        service_change = False
        if points_since_serve_change >= interval:
            service_change = True
            if is_doubles:
                # A1 -> B1 -> A2 -> B2 -> A1 rotation: next server = current receiver;
                # next receiver = partner of previous server.
                server = prev_receiver
                server_side = prev_receiver_side
                receiver = prev_server
                receiver_side = _other_side(prev_server_side) if prev_server_side else None
            else:
                server = _other_team(prev_server)
                receiver = prev_server
            points_since_serve_change = 0

        # Deciding-game mid-game side change (banner + doubles-receiver swap).
        side_change_alert = False
        if (
            deciding_side_change_at > 0
            and is_deciding_game_now()
            and not ends_swapped_this_game
            and max(a_score, b_score) >= deciding_side_change_at
        ):
            side_change_alert = True
            ends_swapped_this_game = True
            if is_doubles and receiver_side:
                receiver_side = _other_side(receiver_side)

        point_history.append({
            "ts": e.get("ts"),
            "kind": "point",
            "scorer": scorer,
            "game_num": game_num,
            "a": a_score,
            "b": b_score,
            "server_before": prev_server,
            "server_side_before": prev_server_side,
            "server_after": server,
            "server_side_after": server_side,
            "receiver_after": receiver,
            "receiver_side_after": receiver_side,
            "service_change": service_change,
            "side_change_alert": side_change_alert,
        })

        game_winner: Optional[str] = None
        # Normal win-by-2 at points_to_win.
        if a_score >= points_to_win and a_score - b_score >= 2:
            game_winner = "A"
        elif b_score >= points_to_win and b_score - a_score >= 2:
            game_winner = "B"
        # Hard-cap override: first to reach the cap wins outright, no lead required.
        elif hard_cap_enabled and a_score >= hard_cap_at:
            game_winner = "A"
        elif hard_cap_enabled and b_score >= hard_cap_at:
            game_winner = "B"

        if game_winner:
            games.append({
                "game_num": game_num,
                "a": a_score,
                "b": b_score,
                "winner": game_winner,
            })
            if game_winner == "A":
                a_games += 1
            else:
                b_games += 1

            if a_games >= target_games:
                match_winner = "A"
                break
            if b_games >= target_games:
                match_winner = "B"
                break

            # Start next game.
            game_num += 1
            a_score = 0
            b_score = 0
            points_since_serve_change = 0
            ends_swapped_this_game = False

            # Singles/doubles: server team alternates each game.
            if game_num % 2 == 0:
                server = _other_team(first_server)
            else:
                server = first_server
            receiver = _other_team(server)
            if is_doubles:
                # Alternate the sub-side each game so all four players share serving duty.
                if (game_num - 1) % 2 == 0:
                    server_side = first_server_side
                    receiver_side = first_receiver_side
                else:
                    server_side = _other_side(first_server_side) if first_server_side else 1
                    receiver_side = _other_side(first_receiver_side) if first_receiver_side else 1

    is_deuce = (
        a_score >= points_to_win - 1
        and b_score >= points_to_win - 1
        and not match_winner
    )
    last = point_history[-1] if point_history else None
    last_service_change = bool(
        last and last.get("service_change") and last.get("kind") == "point" and not match_winner
    )
    last_side_change_alert = bool(last and last.get("side_change_alert"))
    is_deciding = is_deciding_game_now() and not match_winner

    server_name = _player_display(match, server, server_side) if not match_winner else None
    receiver_name = (
        _player_display(match, receiver, receiver_side)
        if (is_doubles and not match_winner)
        else None
    )

    return {
        "match_type": match_type,
        "is_doubles": is_doubles,
        "games": games,
        "current_game_num": game_num if not match_winner else games[-1]["game_num"],
        "a_score": a_score,
        "b_score": b_score,
        "a_games": a_games,
        "b_games": b_games,
        "target_games": target_games,
        "server": server if not match_winner else None,
        "server_side": server_side if (is_doubles and not match_winner) else None,
        "server_name": server_name,
        "receiver": receiver if (is_doubles and not match_winner) else None,
        "receiver_side": receiver_side if (is_doubles and not match_winner) else None,
        "receiver_name": receiver_name,
        "service_change": last_service_change,
        "side_change_alert": last_side_change_alert,
        "is_deuce": is_deuce,
        "is_deciding_game": is_deciding,
        "ends_swapped": ends_swapped_this_game,
        "match_winner": match_winner,
        "point_history": point_history,
        "total_points": sum(1 for p in point_history if p.get("kind") == "point"),
        "let_count": let_count,
        "points_to_win": points_to_win,
        "best_of": best_of,
        "service_interval": service_interval,
        "deuce_interval": deuce_interval,
        "deciding_side_change_at": deciding_side_change_at,
    }


def player_name(match: dict, ab: str) -> str:
    """Team display name used in flash messages."""
    if match.get("match_type") == "doubles":
        p1, p2 = _team_players(match, ab)
        return f"{p1} / {p2}"
    if ab == "A":
        return match.get("player_a", "Player A")
    return match.get("player_b", "Player B")


def stats_for_match(state: dict) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Return (games_won_by_team, points_scored_by_team) as dicts keyed 'A','B'."""
    a_points = sum(g["a"] for g in state["games"]) + state["a_score"]
    b_points = sum(g["b"] for g in state["games"]) + state["b_score"]
    return (
        {"A": state["a_games"], "B": state["b_games"]},
        {"A": a_points, "B": b_points},
    )
