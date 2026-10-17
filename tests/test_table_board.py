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
