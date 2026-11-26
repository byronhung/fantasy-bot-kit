from fantasy_bot.alerts import lineup_alerts
from fantasy_bot.nba.injuries import norm, to_yahoo_status
from fantasy_bot.report.notify import alert_key


def test_norm_matches_yahoo_and_espn_spellings():
    assert norm("Nikola Jokić") == norm("Nikola Jokic")
    assert norm("Trey Murphy III") == norm("Trey Murphy")
    assert norm("P.J. Washington") == norm("PJ Washington")


def test_espn_status_mapping():
    assert to_yahoo_status("Out") == "O"
    assert to_yahoo_status("Day-To-Day") == "GTD"
    assert to_yahoo_status("Active") is None


def test_lineup_alert_for_out_starter_suggests_bench():
    players = [
        {"name": "Hurt Guy", "team": "ATL", "slot": "SG", "status": "O"},
        {"name": "Bench Guy", "team": "HOU", "slot": "BN", "status": None},
        {"name": "Idle Guy", "team": "NYK", "slot": "PF", "status": None},
    ]
    out = lineup_alerts("L", players, {"ATL", "HOU"}, {})
    assert any("Hurt Guy is in your lineup but OUT" in a and "Bench Guy" in a for a in out)
    assert any("no game today: Idle Guy" in a for a in out)


def test_alert_key_stable():
    assert alert_key("x") == alert_key("x") and alert_key("x") != alert_key("y")
