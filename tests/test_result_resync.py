"""A match that is finished, undone and finished the other way must update the
tournament slot's winner (and take back / re-apply player stats)."""
import copy

import app.main as main


def _fixture():
    slot = {"slot": 1, "match_id": "m1", "winner": "B", "winner_name": "Spin Twins",
            "a_points": 1, "b_points": 2, "ended_at": "x", "duration_sec": 5}
    tournament = {"tournament_id": "t1", "rounds": [{"round_num": 3, "matches": [slot]}]}
    match = {"match_id": "m1", "tournament_id": "t1", "round_num": 3, "match_type": "singles",
             "player_a": "A", "player_b": "B", "player_a_id": "ua", "player_b_id": "ub",
             "stats_recorded": True, "winner": "B",
             "stats_snapshot": [{"uid": "ub", "won": True, "gp": 2, "gw": 2, "pts": 22}]}
    return tournament, match


def _patch(monkeypatch, tournament):
    calls = {"stats": [], "match": []}
    monkeypatch.setattr(main, "get_tournament", lambda tid: tournament)
    monkeypatch.setattr(main, "update_tournament", lambda tid, expr, vals: None)
    monkeypatch.setattr(main, "update_match", lambda mid, expr, vals: calls["match"].append((expr, vals)))
    monkeypatch.setattr(main, "update_user_stats",
                        lambda *a, **k: calls["stats"].append((a, k)))
    monkeypatch.setattr(main, "_fill_from_sources", lambda t: False)
    return calls


def test_undo_clears_recorded_winner(monkeypatch):
    tournament, match = _fixture()
    calls = _patch(monkeypatch, tournament)
    main._unrecord_match_result(match)
    slot = tournament["rounds"][0]["matches"][0]
    assert slot["winner"] == "" and slot["winner_name"] == ""
    assert "a_points" not in slot and "ended_at" not in slot
    assert calls["stats"][0][1] == {"sign": -1}
    assert calls["match"][0][1] == {":s": False}


def test_refinish_with_other_winner_resyncs_slot(monkeypatch):
    tournament, match = _fixture()
    calls = _patch(monkeypatch, tournament)
    monkeypatch.setattr(main, "_winning_side_label", lambda m, t, w: "Pongfinity")
    state = {"match_winner": "A", "games": [{"a": 0, "b": 11}, {"a": 12, "b": 10}, {"a": 11, "b": 0}],
             "a_games": 2, "b_games": 1}
    main._finalize_stats_if_needed(copy.deepcopy(match), state)
    slot = tournament["rounds"][0]["matches"][0]
    assert slot["winner"] == "A"
    assert slot["winner_name"] == "Pongfinity"
    assert (slot["a_points"], slot["b_points"]) == (23, 21)


def test_same_winner_is_not_recorded_twice(monkeypatch):
    tournament, match = _fixture()
    calls = _patch(monkeypatch, tournament)
    state = {"match_winner": "B", "games": [], "a_games": 0, "b_games": 2}
    main._finalize_stats_if_needed(match, state)
    assert calls["stats"] == [] and calls["match"] == []
