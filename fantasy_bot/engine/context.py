"""Adjustments for things the raw stats can't see.

1. Teammate returns. A role player's last 2 weeks look great while a star teammate sits out;
   when the star comes back, the shots and minutes go back to him. If a top-100 (preseason)
   teammate missed 3+ of the team's recent games and is now back or about to be, and the
   player's recent form is clearly above his season form, project him mostly on his season form.

2. Opponent adds. The opponent isn't frozen: an active manager streams players into open days.
   Estimate how many adds they'll still use from their pace (this week and the last 14 days),
   and give them that many decent streamers in the projection.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from fantasy_bot.engine.project import RAW, Player, fantasy_value
from fantasy_bot.nba.schedule import canon

MISSED_MIN = 3          # star missed at least this many of the team's last-14-day games
BOOST_MIN = 1.10        # player's recent value at least 10% above his season value
SEASON_WEIGHT = 0.8     # after the star returns: 80% season form, 20% recent
BACK_STATUSES = {None, "P", "Q", "GTD", "DTD"}  # star is playing again, or day-to-day

# An "Out" star whose latest news says he's about to play (Reaves: "full participant in practice").
_RETURNING = re.compile(r"full participant|fully participat|full practice|probable|expected to (?:play|return)"
                        r"|set to return|will return|cleared to (?:play|return)|upgraded to questionable"
                        r"|questionable|available", re.I)
_LONG_OUT = re.compile(r"weeks|months|season|re-evaluated|surgery|indefinitely|not expected", re.I)


def returning_soon(note: str | None) -> bool:
    return bool(note) and bool(_RETURNING.search(note)) and not _LONG_OUT.search(note)


SKIP_TOP_FAS = 5        # opponent's streamers: decent, not the very best (you might grab those)


def team_games_14(groups: list[list[dict]]) -> dict[str, int]:
    """Games each NBA team played in the last 14 days ~ the most any of its players played."""
    out: dict[str, int] = {}
    for g in groups:
        for p in g:
            t = canon(p.get("team"))
            gp = (p.get("l14") or {}).get("gp", p.get("gp")) or 0
            if t:
                out[t] = max(out.get(t, 0), int(gp))
    return out


def stars_back(stars: list[dict], team_gp: dict[str, int]) -> dict[str, list[str]]:
    """team -> names of top players who missed recent games and are back / day-to-day now."""
    out: dict[str, list[str]] = {}
    for s in stars:
        t = canon(s.get("team"))
        if not t:
            continue
        missed = team_gp.get(t, 0) - int(s.get("gp") or 0)
        back = s.get("status") in BACK_STATUSES or returning_soon(s.get("espn_note"))
        if missed >= MISSED_MIN and back:
            out.setdefault(t, []).append(s["name"])
    return out


def apply_teammate_returns(players: list[Player], back: dict[str, list[str]]) -> list[str]:
    """Shift boosted players toward season form. Returns notes for the report."""
    notes = []
    for p in players:
        names = [n for n in back.get(p.team or "", []) if n != p.name]
        if not names or p.gp14 < 3 or not p.l14_rate or not p.season_rate:
            continue
        recent, season = fantasy_value(p.l14_rate), fantasy_value(p.season_rate)
        if season <= 0 or recent < BOOST_MIN * season:
            continue
        p.rate = {k: SEASON_WEIGHT * p.season_rate[k] + (1 - SEASON_WEIGHT) * p.l14_rate[k] for k in RAW}
        p.value = fantasy_value(p.rate)
        p.meta["teammate_back"] = names
        notes.append(f"{p.name}: recent numbers came while {' & '.join(names)} sat; "
                     f"projected closer to his season form ({round(recent)} -> {round(p.value)} value/game).")
    return notes


def _adds_since(adds: list[dict], team: str, since: date, today: date) -> int:
    n = 0
    for a in adds:
        if a["team"] != team:
            continue
        d = datetime.strptime(f"{a['date']} {today.year}", "%b %d %Y").date()
        if d > today:
            d = d.replace(year=today.year - 1)
        if d >= since:
            n += 1
    return n


def expected_opp_adds(adds: list[dict], opp_team: str, used: int, left: int,
                      today: date, days_left: int) -> int:
    """How many more adds the opponent will probably make this week."""
    if left <= 0 or days_left <= 0:
        return 0
    days_in = max(1, today.weekday())                       # Mon=0 -> 1 day of evidence
    week_pace = used / days_in
    hist_pace = _adds_since(adds, opp_team, today - timedelta(days=14), today) / 14
    exp = max(week_pace, hist_pace) * days_left
    return min(left, int(exp + 0.5))


def opp_with_streamers(opp: list[Player], fas: list[Player], n: int,
                       games: dict[str, int]) -> tuple[list[Player], list[str]]:
    """Opponent's roster after n likely streams: best-by-games FAs (skipping the top few)
    replace their weakest active players."""
    if n <= 0:
        return opp, []
    pool = sorted((f for f in fas if games.get(f.name, 0) > 0),
                  key=lambda f: -f.value * games[f.name])[SKIP_TOP_FAS:SKIP_TOP_FAS + n]
    roster = list(opp)
    for f in pool:
        active = [p for p in roster if p.slot != "IL" and not p.meta.get("streamer")]
        if not active:
            break
        weakest = min(active, key=lambda p: p.value)
        clone = Player(**{**f.__dict__, "meta": {"streamer": True}, "slot": "BN"})
        roster = [p for p in roster if p is not weakest] + [clone]
    return roster, [f.name for f in pool]
