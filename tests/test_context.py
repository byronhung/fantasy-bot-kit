from datetime import date

from fantasy_bot.engine.context import (
    apply_teammate_returns, expected_opp_adds, opp_with_streamers, stars_back, team_games_14,
)
from fantasy_bot.engine.project import RAW
from fantasy_bot.yahoo.parse import parse_player_cell
from tests.test_engine import mk


def _rates(pts):
    r = {k: 0.0 for k in RAW}
    r.update({"PTS": pts, "fgm": pts / 2.5, "fga": pts / 2.2, "ftm": 1, "fta": 1.2, "REB": 3, "AST": 2})
    return r


def test_role_player_deflates_when_star_teammate_returns():
    team_gp = team_games_14([[{"team": "LAL", "l14": {"gp": 7}}]])
    stars = [{"name": "Austin Reaves", "team": "LAL", "gp": 1, "status": "GTD"},   # missed 6, day-to-day
             {"name": "Luka Doncic", "team": "LAL", "gp": 7, "status": None}]      # never missed
    back = stars_back(stars, team_gp)
    assert back == {"LAL": ["Austin Reaves"]}

    grimes = mk("Quentin Grimes", "SG", team="LAL", pts=20)
    grimes.gp14, grimes.l14_rate, grimes.season_rate = 7, _rates(20), _rates(12)
    grimes.rate = _rates(16.8)
    notes = apply_teammate_returns([grimes], back)
    assert grimes.meta["teammate_back"] == ["Austin Reaves"]
    assert abs(grimes.rate["PTS"] - (0.8 * 12 + 0.2 * 20)) < 1e-9
    assert notes and "Austin Reaves" in notes[0]


def test_no_deflation_when_star_still_out_or_no_boost():
    team_gp = {"LAL": 7}
    assert stars_back([{"name": "Reaves", "team": "LAL", "gp": 1, "status": "O"}], team_gp) == {}
    back = {"LAL": ["Reaves"]}
    steady = mk("Steady", "SG", team="LAL", pts=15)
    steady.gp14, steady.l14_rate, steady.season_rate = 7, _rates(15), _rates(15)
    assert apply_teammate_returns([steady], back) == [] and "teammate_back" not in steady.meta


def test_expected_opp_adds_from_pace():
    thu = date(2026, 11, 26)  # weekday 3
    adds = [{"team": "Opp", "date": "Nov 24"}, {"team": "Opp", "date": "Nov 25"}]
    assert expected_opp_adds(adds, "Opp", used=2, left=2, today=thu, days_left=4) == 2   # 2/3 per day x 4
    assert expected_opp_adds([], "Opp", used=0, left=4, today=thu, days_left=4) == 0     # inactive manager
    assert expected_opp_adds(adds, "Opp", used=4, left=0, today=thu, days_left=4) == 0   # out of adds


def test_opp_streamers_replace_weakest_and_skip_best_fas():
    opp = [mk("star", "PG", pts=30), mk("scrub", "C", pts=2)]
    fas = [mk(f"fa{i}", "SF", pts=20 - i) for i in range(8)]
    games = {f.name: 3 for f in fas}
    roster, names = opp_with_streamers(opp, fas, 1, games)
    assert names == ["fa5"]                                   # top 5 skipped
    assert {p.name for p in roster} == {"star", "fa5"}
    assert next(p for p in roster if p.name == "fa5").meta["streamer"]


def test_probable_tag_not_glued_to_name():
    p = parse_player_cell("Karl-Anthony TownsPNew Player NoteNYK - PF,C7:30 pm vs CLE")
    assert p["name"] == "Karl-Anthony Towns" and p["status"] == "P" and p["team"] == "NYK"


def test_out_star_with_practice_news_counts_as_returning():
    from fantasy_bot.engine.context import returning_soon
    assert returning_soon("Reaves (heel) was a full participant in Wednesday's practice, X reports.")
    assert not returning_soon("Curry has been diagnosed with an oblique abdominal tear and will be re-evaluated in two weeks.")
    assert not returning_soon("Pippen (back) is out for Wednesday's game against the Clippers.")
    star = {"name": "Austin Reaves", "team": "LAL", "gp": 1, "status": "O",
            "espn_note": "Reaves (heel) was a full participant in Wednesday's practice."}
    assert stars_back([star], {"LAL": 7}) == {"LAL": ["Austin Reaves"]}


def test_new_matchup_layout_parses():
    """Yahoo's newer (game-day) matchup page: no FGM/A columns, abbreviated names, <abbr> status."""
    from fantasy_bot.yahoo.parse import SlotLookup, estimate_shots, parse_matchup, short_key
    head = "".join(f"<th>{h}</th>" for h in ["Team", "FG%", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO", "Score"])
    row = lambda n, w: "<tr>" + "".join(f"<td>{x}</td>" for x in [n, ".484", ".714", "15", "193", "102", "50", "18", "13", "38", w]) + "</tr>"
    cell = lambda pid, n, tp, st="": (f'<td><a class="playernote" data-ys-playerid="{pid}">{n}</a>'
                                     f'<span>{tp}</span>{st}</td>' + "<td>-</td>" * 9)
    ph = "".join(f"<th>{h}</th>" for h in ["Player"] + ["c"] * 9 + ["Pos", "Player"] + ["c"] * 9)
    prow = ("<tr>" + cell("1", "A. Black", "ORL - PG,SG") + "<td>PG</td>"
            + cell("2", "M. Porter Jr.", "BKN - SF,PF", '<abbr title="Out">O</abbr>') + "</tr>")
    html = (f"<table><tr>{head}</tr>{row('Me', '6')}{row('Them', '3')}</table>"
            f"<table><tr>{ph}</tr>{prow}</table>")
    m = parse_matchup(html)
    assert m.me.cats_won == 6 and m.opp.cats_won == 3
    fgm, fga = m.me.fgm_a
    assert abs(fgm / fga - 0.484) < 0.01 and 140 < fga < 170
    assert m.my_players[0] == {**m.my_players[0], "name": "A. Black", "team": "ORL", "slot": "PG", "pid": "1"}
    assert m.opp_players[0]["status"] == "O" and m.opp_players[0]["slot"] == "PG"
    assert short_key("Michael Porter Jr.") == short_key("M. Porter Jr.") == "m porter"
    look = SlotLookup(m.my_players)
    assert look.get({"name": "Anthony Black"}) == "PG"            # by abbreviated name
    assert look.get({"name": "Someone Else", "pid": "1"}) == "PG"  # by Yahoo id
