from fastapi.testclient import TestClient

import app.main as main


def _tournament():
    return {"tournament_id": "t1", "name": "Demo", "rounds": [], "qualify_per_group": 4}


def test_tv_top16_is_public_and_shows_qualifiers(monkeypatch):
    monkeypatch.setattr(main, "get_tournament", lambda tid: _tournament())
    seeds = [{"seed": 1, "key": "k1", "label": "Net Ninjas", "level": "Advanced", "pool": "Pluto",
              "wins": 3, "pf": 66, "pa": 3, "nrr": 63, "tied": False, "manual": False},
             {"seed": 2, "key": "k2", "label": "Ali Titans", "level": "Intermediate", "pool": "Mercury",
              "wins": 1, "pf": 50, "pa": 61, "nrr": -11, "tied": True, "manual": True}]
    monkeypatch.setattr(main, "_seeding", lambda t: {"seeds": seeds, "ready": True, "manual": True, "others": []})
    r = TestClient(main.app).get("/live/tournaments/t1/tv/top16")  # no cookies / credentials
    assert r.status_code == 200
    body = r.text
    assert "Net Ninjas" in body and "Ali Titans" in body
    assert "MANUAL" in body and "TIE" in body and "PF" in body
    assert "Remove" not in body
