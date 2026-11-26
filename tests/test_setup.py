import json

from fantasy_bot import config
from fantasy_bot.login import to_storage_state
from fantasy_bot.setup import slug


def test_storage_state_keeps_only_yahoo_and_normalizes():
    s = to_storage_state([
        {"name": "T", "value": "1", "domain": ".yahoo.com", "path": "/", "expires": 2e9, "sameSite": "None", "secure": True},
        {"name": "S", "value": "2", "domain": "login.yahoo.com", "session": True, "expires": -1},
        {"name": "G", "value": "3", "domain": ".google.com", "expires": 2e9},
    ])
    assert [c["name"] for c in s["cookies"]] == ["T", "S"]
    assert s["cookies"][1]["sameSite"] == "Lax" and s["cookies"][1]["expires"] == -1
    assert s["origins"] == []


def test_leagues_from_env(monkeypatch):
    monkeypatch.setenv("FBOT_LEAGUES", json.dumps([{"key": "a", "name": "A", "league_id": "1", "team_id": "2"}]))
    assert config.load_leagues()[0]["league_id"] == "1"


def test_slug():
    assert slug("Lau's Legendary Team!") == "lau_s_legendary_team"


def test_league_problem_checks_scoring_and_categories():
    from fantasy_bot.setup import league_problem
    std = ("Field Goal Percentage (FG%), Free Throw Percentage (FT%), 3-point Shots Made (3PTM), "
           "Points Scored (PTS), Total Rebounds (REB), Assists (AST), Steals (ST), Blocked Shots (BLK), Turnovers (TO)")
    h2h = "Head-to-Head - Categories"
    assert league_problem({"Scoring Type": h2h, "Players Stat Categories": std}) is None
    assert league_problem({"Scoring Type": h2h}) is None  # field missing: don't block
    assert "not head-to-head" in league_problem({"Scoring Type": "Head-to-Head - Points"})
    eight = std.replace(", Turnovers (TO)", "")
    assert "missing: TO" in league_problem({"Scoring Type": h2h, "Players Stat Categories": eight})
    assert "extra: DD" in league_problem({"Scoring Type": h2h, "Players Stat Categories": std + ", Double-Doubles (DD)"})
