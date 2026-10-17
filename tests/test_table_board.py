import app.main as main

T = {"num_tables": 6}


def _m(table, status="pending", slot=1):
    return {"table_number": table, "status": status, "slot": slot}


def _tables(rounds):
    return [e["table"] for e in main._build_table_board(T, rounds)]


def test_pool_stage_shows_all_tables():
    rounds = [{"name": "Pool A", "stage_type": "pool", "matches": [_m(1), _m(2)]}]
    assert _tables(rounds) == [1, 2, 3, 4, 5, 6]


def test_top16_with_four_tables_hides_unused():
    rounds = [
        {"name": "Pool A", "stage_type": "pool", "matches": [_m(5, "finished"), _m(6, "finished")]},
        {"name": "Top 16", "stage_type": "knockout", "matches": [_m(1), _m(2), _m(3), _m(4)]},
    ]
    assert _tables(rounds) == [1, 2, 3, 4]


def test_tables_come_back_when_later_round_uses_them():
    rounds = [
        {"name": "Top 16", "stage_type": "knockout", "matches": [_m(i, "finished") for i in range(1, 7)]},
        {"name": "Quarter Finals", "stage_type": "knockout", "matches": [_m(1), _m(2), _m(3), _m(4)]},
    ]
    assert _tables(rounds) == [1, 2, 3, 4]
    rounds[1]["matches"] += [_m(5), _m(6)]
    assert _tables(rounds) == [1, 2, 3, 4, 5, 6]


def test_pool_still_running_keeps_all_tables_even_if_knockout_assigned():
    rounds = [
        {"name": "Pool A", "stage_type": "pool", "matches": [_m(1)]},
        {"name": "Top 16", "stage_type": "knockout", "matches": [_m(1)]},
    ]
    assert _tables(rounds) == [1, 2, 3, 4, 5, 6]


def test_semis_winner_stays_in_box_until_next_round_starts():
    def rnd(num, name, matches):
        return {"round_num": num, "name": name, "stage_type": "knockout", "matches": matches}

    qf = rnd(1, "Quarter Finals", [dict(_m(i, "finished"), winner="A", winner_name=f"Q{i}") for i in range(1, 5)])
    sf = rnd(2, "Semi Finals", [dict(_m(1, "finished"), winner="A", winner_name="Net Ninjas"), _m(2, "live")])
    board = main._build_table_board(T, [qf, sf])
    assert [e["table"] for e in board] == [1, 2]
    assert board[0]["show_last"] and board[0]["last"]["winner_name"] == "Net Ninjas"

    # both semis done, final not assigned yet: semi winners stay, quarter tables do not return
    sf["matches"][1]["status"] = "finished"
    board = main._build_table_board(T, [qf, sf, rnd(3, "Final", [_m(0)])])
    assert [e["table"] for e in board] == [1, 2]
    assert all(e["last"] for e in board)

    # final starts on table 1: semi winner is cleared
    board = main._build_table_board(T, [qf, sf, rnd(3, "Final", [_m(1, "live")])])
    assert [e["table"] for e in board] == [1]
    assert board[0]["last"] is None and board[0]["live"]


def test_top16_does_not_flag_last_winner():
    top16 = {"round_num": 1, "name": "Top 16", "stage_type": "knockout", "matches": [_m(1), _m(2)]}
    assert not any(e["show_last"] for e in main._build_table_board(T, [top16]))


def test_tv_renders_winner_in_finished_semi_box(monkeypatch):
    from fastapi.testclient import TestClient

    done = {"table_number": 1, "status": "finished", "slot": 1, "winner": "A", "winner_name": "Net Ninjas",
            "a_name": "Net Ninjas", "b_name": "Spin Twins", "a_games": 2, "b_games": 0,
            "round_name": "Semi Finals", "match_type": "singles"}
    rounds = [{"round_num": 1, "name": "Semi Finals", "stage_type": "knockout", "matches": [done]}]
    monkeypatch.setattr(main, "get_tournament", lambda tid: {"tournament_id": "t1", "name": "Demo", "num_tables": 6,
                                                            "best_of": 3, "points_to_win": 11})
    monkeypatch.setattr(main, "_build_rounds_view", lambda t: rounds)
    r = TestClient(main.app).get("/live/tournaments/t1/tv")
    assert r.status_code == 200
    assert "WINNER" in r.text and "Net Ninjas" in r.text
    assert "Table 2" not in r.text
