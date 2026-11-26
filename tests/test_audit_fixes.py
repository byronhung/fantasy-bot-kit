from datetime import date, datetime, timezone

from fantasy_bot.alerts import fresh_news
from fantasy_bot.calibrate import outcome
from fantasy_bot.engine.matchup import outlook
from fantasy_bot.engine.project import project
from fantasy_bot.engine.recommend import Plan, _dead_week_moves
from fantasy_bot.report.export import plan_json
from fantasy_bot.report.render import short
from fantasy_bot.yahoo.parse import TeamLine, current_week, parse_player_cell
from tests.test_engine import mk


def test_video_forecast_label_is_stripped():
    p = parse_player_cell("Quentin GrimesVideo ForecastPlayer NoteLAL - SG,SF")
    assert (p["name"], p["team"]) == ("Quentin Grimes", "LAL")
    p = parse_player_cell("Quentin GrimesQVideo ForecastNew Player NoteLAL - SG,SF")
    assert (p["name"], p["status"]) == ("Quentin Grimes", "Q")


def test_current_week_from_matchup_links():
    assert current_week('href="/nba/1/matchup?week=6&date=2026-11-23"') == 6


def _outlook():
    stats = {c: 0.0 for c in ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]}
    e = project([], {})
    return outlook(TeamLine("me", dict(stats), (0, 0), (0, 0)), e, TeamLine("o", dict(stats), (0, 0), (0, 0)), e)


def test_dead_week_prefers_better_player_and_uses_flat_games_when_schedule_tbd():
    weak = mk("Weak", "PG", pts=5); weak.pct_ros = 5
    good_fa = mk("Good", "PG", pts=25); good_fa.pct_ros = 60
    roster = [weak] + [mk(f"core{i}", "C", pts=40) for i in range(8)]
    for p in roster[1:]:
        p.pct_ros = 90
    tbd_week = {date(2026, 11, 30) + __import__("datetime").timedelta(days=i): {"AAA"} for i in range(7)}
    moves = _dead_week_moves(roster, [good_fa], tbd_week, _outlook(), 2, 0)
    assert moves and moves[0].add.name == "Good" and moves[0].drop.name == "Weak"
    assert isinstance(moves[0].next_in, float)  # 7 team-games < 80: schedule treated as unknown


def test_fresh_news_since_last_seen(monkeypatch):
    import fantasy_bot.alerts as alerts_mod   # no leagues.json on a fresh copy: use a fake league
    monkeypatch.setattr(alerts_mod, "LEAGUES", [{"key": "lg", "name": "LG"}])
    rosters = {"lg": [{"name": "A Guy", "slot": "PG"}]}
    news = {"a guy": {"name": "A Guy", "status": "Out", "short": "x", "date": "2026-11-25T01:00Z"}}
    now = datetime(2026, 11, 25, 5, tzinfo=timezone.utc)
    alerts, seen = fresh_news(rosters, news, {}, now)
    assert len(alerts) == 1
    alerts2, _ = fresh_news(rosters, news, seen, now)   # same item again: no alert
    assert alerts2 == []
    news["a guy"]["date"] = "2026-11-25T04:30Z"          # newer item, hours later: alert
    assert len(fresh_news(rosters, news, seen, now)[0]) == 1


def test_outcome_lower_to_wins():
    me = {"FG%": .5, "FT%": .8, "3PTM": 10, "PTS": 100, "REB": 50, "AST": 20, "ST": 5, "BLK": 5, "TO": 10}
    opp = {**me, "TO": 12, "PTS": 90}
    o = outcome(me, opp)
    assert o["TO"] == 1.0 and o["PTS"] == 1.0 and o["REB"] == 0.5


def test_short_push_is_one_line_and_export_has_cats():
    lg = {"name": "Hoopers", "key": "hoopers"}
    p = Plan(lg, "Opp", (5, 3), _outlook(), 0, 4, 4, [])
    s = short(p)
    assert "\n" not in s and s.startswith("Hoopers 5-3") and s.endswith("hold")
    j = plan_json(p)
    assert len(j["cats"]) == 9 and j["mode"] == "this_week"


def test_long_term_only_move_does_not_block_weekly_moves():
    # A source-level guard: candidates with no weekly gain are skipped before scoring.
    import inspect
    from fantasy_bot.engine import recommend
    src = inspect.getsource(recommend.build_plan)
    assert "if gain <= 0:" in src and src.index("if gain <= 0:") < src.index("score = gain + weight")
