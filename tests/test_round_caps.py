import pytest

from app.main import _score_rule_defaults_for_round

T = {"hard_cap_at": 15}
CFG = {"hard_cap_at": 15}


@pytest.mark.parametrize("round_data", [
    {"name": "Final", "stage_type": "knockout"},
    {"name": "Final"},                      # seeded by name, no stage_type
    {"name": "Grand Final", "stage_type": "custom"},
    {"name": "Semi Finals"},
    {"name": "Plate Final", "stage_type": "plate"},
])
def test_final_and_knockouts_have_no_cap(round_data):
    assert _score_rule_defaults_for_round(round_data, CFG, T) == {"hard_cap_enabled": False, "hard_cap_at": 0}


def test_pool_uses_tournament_cap():
    r = _score_rule_defaults_for_round({"name": "Pool A", "stage_type": "pool"}, CFG, T)
    assert r == {"hard_cap_enabled": True, "hard_cap_at": 15}


def test_explicit_round_cap_still_wins():
    r = _score_rule_defaults_for_round({"name": "Final", "hard_cap_at": 21}, CFG, T)
    assert r == {"hard_cap_enabled": True, "hard_cap_at": 21}
