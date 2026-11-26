from datetime import date

from fantasy_bot.engine.matchup import outlook
from fantasy_bot.engine.project import RAW, Player, project, starting_slots
from fantasy_bot.engine.recommend import adds_this_week
from fantasy_bot.yahoo.parse import TeamLine, parse_player_cell

D = date(2026, 11, 20)


def mk(name, pos, team="AAA", pts=10.0, status=None, slot="BN"):
    rate = {k: 0.0 for k in RAW}
    rate.update({"PTS": pts, "fgm": 4, "fga": 9, "ftm": 2, "fta": 2.5, "REB": 5, "AST": 3})
    return Player(name, team, pos.split(","), status, rate, pts, slot=slot)


def test_bench_overflow_wastes_games():
    # 11 centers, only C, C, Util, Util can hold them -> 4 starters, 7 benched games.
    roster = [mk(f"c{i}", "C") for i in range(11)]
    pr = project(roster, {D: {"AAA"}})
    assert len(pr.per_day[D]) == 4
    assert pr.benched_games == 7


def test_matching_moves_flexible_player_to_make_room():
    # PG,SG can play SG; pure PG must take PG. Both should start.
    roster = [mk("combo", "PG,SG", pts=30), mk("pure", "PG", pts=10)]
    pr = project(roster, {D: {"AAA"}}, ["PG", "SG"])
    assert set(pr.per_day[D]) == {"combo", "pure"}


def test_out_players_and_il_score_nothing():
    roster = [mk("hurt", "SF", status="O"), mk("il", "SF", slot="IL")]
    pr = project(roster, {D: {"AAA"}})
    assert pr.games == 0


def test_roster_positions_parse():
    s = starting_slots("PG, SG, G, SF, PF, F, C, FC, Util, Util, BN, BN, BN, IL, IL")
    assert s == ["PG", "SG", "G", "SF", "PF", "F", "C", "FC", "Util", "Util"]


def test_turnovers_lower_wins_and_matchup_prob():
    stats = {c: 0.0 for c in ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]}
    me = TeamLine("me", {**stats, "TO": 10}, (40, 80), (10, 12))
    opp = TeamLine("opp", {**stats, "TO": 30}, (30, 80), (8, 12))
    empty = project([], {})
    o = outlook(me, empty, opp, empty)
    to = next(c for c in o.cats if c.cat == "TO")
    assert to.p_win == 1.0
    assert 0 <= o.p_win <= 1


def test_adds_this_week_counts_only_my_team_since_monday():
    adds = [
        {"team": "Hoopers", "date": "Nov 19"},
        {"team": "Hoopers", "date": "Nov 15"},   # last week (Sun)
        {"team": "Other", "date": "Nov 19"},
    ]
    assert adds_this_week(adds, "Hoopers", D) == 1


def test_long_term_value_and_weight():
    from fantasy_bot.engine.project import long_term_value
    keeper = mk("Keeper", "C", pts=20); keeper.season_value, keeper.pct_ros = 40, 85
    stream = mk("Stream", "PG", pts=12); stream.season_value, stream.pct_ros = 20, 10
    lt_k, lt_s = long_term_value(keeper), long_term_value(stream)
    assert lt_k > lt_s
    # a +14% weekly gain doesn't justify dropping the keeper at weight 0.5...
    assert 0.14 + 0.5 * (lt_s - lt_k) < 0
    # ...but does at weight 0 (pure streaming)
    assert 0.14 + 0.0 * (lt_s - lt_k) > 0


def test_player_cell():
    p = parse_player_cell("Andrew NembhardQNew Player NoteIND - PG,SG")
    assert (p["name"], p["status"], p["team"], p["pos"]) == ("Andrew Nembhard", "Q", "IND", "PG,SG")
    p = parse_player_cell("OG AnunobyPlayer NoteNYK - SF,PFW, 102-99 @ MIN")
    assert p["pos"] == "SF,PF" and p["game"].startswith("W")
