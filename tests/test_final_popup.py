from app import main


def _popup(monkeypatch, name, stage_type="knockout"):
    t = {"tournament_id": "t1", "name": "T", "participants": [],
         "rounds": [{"round_num": 1, "name": name, "stage_type": stage_type, "matches": []}]}
    monkeypatch.setattr(main, "get_tournament", lambda tid: t)
    match = {"tournament_id": "t1", "round_num": 1, "match_type": "singles",
             "player_a": "A", "player_b": "B"}
    return main._final_popup(match, {"match_winner": "A", "a_games": 2, "b_games": 0})


def test_popup_only_for_main_final(monkeypatch):
    assert _popup(monkeypatch, "Final")["title"] == "Final"
    assert _popup(monkeypatch, "Plate Final", "plate") is None
    assert _popup(monkeypatch, "Plate Final") is None
    assert _popup(monkeypatch, "3rd Place", "plate") is None
    assert _popup(monkeypatch, "Semi Finals") is None
    assert _popup(monkeypatch, "Quarter Finals") is None
