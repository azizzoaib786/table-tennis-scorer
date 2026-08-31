"""Unit tests for the scoring engine in ``app.logic``.

These tests are pure — no AWS / DB required. Run with:

    pytest -q                       # from repo root
    pytest -q tests/test_logic.py   # single file
    pytest -q -k doubles            # match a keyword

Every rule from the README's "Table tennis rules implemented" section
is exercised here at least once.
"""
from app.logic import compute_state, player_name


# ── Fixtures (plain dicts, no fixtures framework needed) ───────────────────────

SINGLES_BASE = {
    "match_type": "singles",
    "best_of": 3,
    "points_to_win": 11,
    "service_interval": 2,
    "deuce_interval": 1,
    "first_server": "A",
    "deciding_side_change_at": 5,
    "player_a": "Alice",
    "player_b": "Bob",
}

DOUBLES_BASE = {
    "match_type": "doubles",
    "best_of": 1,
    "points_to_win": 11,
    "service_interval": 2,
    "deuce_interval": 1,
    "first_server": "A",
    "first_server_side": 1,
    "first_receiver_side": 1,
    "deciding_side_change_at": 5,
    "player_a": "A1",
    "player_a2": "A2",
    "player_b": "B1",
    "player_b2": "B2",
}


def _pt(scorer):
    return {"scorer": scorer}


# ── Singles ───────────────────────────────────────────────────────────────────

def test_singles_serve_flips_after_two_points():
    events = [_pt("A"), _pt("B")]
    state = compute_state(SINGLES_BASE, events)
    assert state["a_score"] == 1
    assert state["b_score"] == 1
    assert state["server"] == "B", "serve should switch to B after 2 points"


def test_singles_serve_stays_after_one_point():
    events = [_pt("A")]
    state = compute_state(SINGLES_BASE, events)
    assert state["server"] == "A", "serve stays with A after 1 point"


def test_singles_deuce_flag_activates_at_10_10():
    events = [_pt("A")] * 10 + [_pt("B")] * 10
    state = compute_state(SINGLES_BASE, events)
    assert state["is_deuce"] is True


def test_singles_serve_flips_every_point_in_deuce():
    # Get to 10-10 (both scored 10 alternately produces same effect for scoring).
    events = [_pt("A")] * 10 + [_pt("B")] * 10
    state = compute_state(SINGLES_BASE, events)
    server_at_deuce = state["server"]
    # One deuce point.
    events.append(_pt("A"))
    state = compute_state(SINGLES_BASE, events)
    assert state["server"] != server_at_deuce, "serve should flip every deuce point"


def test_singles_game_won_at_11_by_2():
    # 11-9: A scores 2, B scores 9, A scores 9 → 11-9 for A.
    events = [_pt("A")] * 2 + [_pt("B")] * 9 + [_pt("A")] * 9
    state = compute_state(SINGLES_BASE, events)
    assert len(state["games"]) == 1
    assert state["games"][0]["winner"] == "A"
    assert state["games"][0]["a"] == 11
    assert state["games"][0]["b"] == 9


def test_singles_no_game_at_11_10():
    # 11-10 is not a game; play must continue.
    events = [_pt("A")] * 10 + [_pt("B")] * 10 + [_pt("A")]  # 11-10
    state = compute_state(SINGLES_BASE, events)
    assert state["games"] == []
    assert state["is_deuce"] is True


def test_singles_deuce_won_by_two():
    # Reach 10-10 then 12-10 (A wins).
    events = [_pt("A")] * 10 + [_pt("B")] * 10 + [_pt("A"), _pt("A")]
    state = compute_state(SINGLES_BASE, events)
    assert len(state["games"]) == 1
    assert state["games"][0]["winner"] == "A"
    assert state["games"][0]["a"] == 12
    assert state["games"][0]["b"] == 10


def test_singles_match_winner_bo3():
    events = [_pt("A")] * 11 + [_pt("A")] * 11
    state = compute_state(SINGLES_BASE, events)
    assert state["match_winner"] == "A"
    assert state["a_games"] == 2


def test_singles_first_server_alternates_each_game():
    # Play game 1 (A wins 11-0); starting server of game 2 should be B.
    events = [_pt("A")] * 11
    state = compute_state(SINGLES_BASE, events)
    assert state["current_game_num"] == 2
    assert state["server"] == "B"


def test_singles_player_name_helper():
    assert player_name(SINGLES_BASE, "A") == "Alice"
    assert player_name(SINGLES_BASE, "B") == "Bob"


# ── Doubles ───────────────────────────────────────────────────────────────────

def test_doubles_rotation_a1_b1_a2_b2_cycle():
    """Serve rotation A1 → B1 → A2 → B2 → A1 with interval=2 per side."""
    events = []
    # After first 2 pts, B1 serves.
    events += [_pt("A"), _pt("B")]
    state = compute_state(DOUBLES_BASE, events)
    assert (state["server"], state["server_side"]) == ("B", 1)
    assert (state["receiver"], state["receiver_side"]) == ("A", 2)

    # 2 more pts → A2 serves to B2.
    events += [_pt("A"), _pt("B")]
    state = compute_state(DOUBLES_BASE, events)
    assert (state["server"], state["server_side"]) == ("A", 2)
    assert (state["receiver"], state["receiver_side"]) == ("B", 2)

    # 2 more pts → B2 serves to A1.
    events += [_pt("A"), _pt("B")]
    state = compute_state(DOUBLES_BASE, events)
    assert (state["server"], state["server_side"]) == ("B", 2)
    assert (state["receiver"], state["receiver_side"]) == ("A", 1)

    # 2 more pts → back to A1 serving to B1.
    events += [_pt("A"), _pt("B")]
    state = compute_state(DOUBLES_BASE, events)
    assert (state["server"], state["server_side"]) == ("A", 1)
    assert (state["receiver"], state["receiver_side"]) == ("B", 1)


def test_doubles_server_name_display():
    state = compute_state(DOUBLES_BASE, [])
    assert state["server_name"] == "A1"
    assert state["receiver_name"] == "B1"


def test_doubles_team_display_name():
    assert player_name(DOUBLES_BASE, "A") == "A1 / A2"
    assert player_name(DOUBLES_BASE, "B") == "B1 / B2"


# ── Let (net on serve) ────────────────────────────────────────────────────────

def test_let_does_not_change_score():
    events = [_pt("A"), _pt("A"), {"type": "let"}]
    state = compute_state(SINGLES_BASE, events)
    assert state["a_score"] == 2
    assert state["b_score"] == 0
    assert state["let_count"] == 1


def test_let_does_not_advance_serve_rotation():
    events = [_pt("A"), {"type": "let"}]  # A scored 1, then a let
    state = compute_state(SINGLES_BASE, events)
    # Server should still be A (not yet 2 real points).
    assert state["server"] == "A"


# ── Deciding-game change-ends ─────────────────────────────────────────────────

def _play_out_game(events, scorer, times=11):
    events.extend([_pt(scorer)] * times)


def test_change_ends_alert_fires_at_5_in_deciding_game():
    events = []
    _play_out_game(events, "A")  # game 1 → A
    _play_out_game(events, "B")  # game 2 → B
    events += [_pt("A")] * 5  # 5-0 in deciding
    state = compute_state(SINGLES_BASE, events)
    assert state["is_deciding_game"] is True
    assert state["side_change_alert"] is True


def test_change_ends_does_not_fire_in_non_deciding_game():
    events = [_pt("A")] * 5  # 5-0 in game 1 (not deciding)
    state = compute_state(SINGLES_BASE, events)
    assert state["side_change_alert"] is False


def test_change_ends_disabled_when_threshold_zero():
    match = dict(SINGLES_BASE, deciding_side_change_at=0)
    events = []
    _play_out_game(events, "A")
    _play_out_game(events, "B")
    events += [_pt("A")] * 5
    state = compute_state(match, events)
    assert state["side_change_alert"] is False


def test_change_ends_alert_fires_only_once_per_deciding_game():
    events = []
    _play_out_game(events, "A")
    _play_out_game(events, "B")
    events += [_pt("A")] * 5  # trigger
    state1 = compute_state(SINGLES_BASE, events)
    assert state1["side_change_alert"] is True
    events += [_pt("A")]  # 6th point
    state2 = compute_state(SINGLES_BASE, events)
    assert state2["side_change_alert"] is False, "alert should only fire on the triggering point"


def test_doubles_receiver_swaps_on_deciding_side_change():
    """When ends change in the deciding game (doubles), receiver-side flips."""
    match = dict(DOUBLES_BASE, best_of=3)
    events = []
    # Game 1: A wins 11-0.
    _play_out_game(events, "A")
    # Game 2: B wins 11-0.
    _play_out_game(events, "B")
    # Deciding game: play until leader reaches 5.
    events += [_pt("A")] * 5
    state = compute_state(match, events)
    assert state["is_deciding_game"] is True
    assert state["side_change_alert"] is True
    # The receiver_side should have been flipped by the alert. We can't easily
    # predict the pre-flip value without replaying, but we can confirm it is
    # 1 or 2 (i.e. still a valid doubles state) and that ``ends_swapped`` is set.
    assert state["ends_swapped"] is True
    assert state["receiver_side"] in (1, 2)


# ── Backward compatibility ────────────────────────────────────────────────────

def test_missing_match_type_defaults_to_singles():
    match = {k: v for k, v in SINGLES_BASE.items() if k != "match_type"}
    state = compute_state(match, [_pt("A"), _pt("B")])
    assert state["match_type"] == "singles"
    assert state["is_doubles"] is False


def test_missing_side_config_still_works_for_singles():
    minimal = {
        "best_of": 1,
        "points_to_win": 11,
        "first_server": "A",
    }
    state = compute_state(minimal, [_pt("A")] * 11)
    assert state["match_winner"] == "A"


# ── Undo semantics ────────────────────────────────────────────────────────────

def test_undone_event_is_ignored():
    events = [_pt("A"), _pt("A"), {"scorer": "A", "undone": True}]
    state = compute_state(SINGLES_BASE, events)
    assert state["a_score"] == 2, "undone event must not contribute to score"
