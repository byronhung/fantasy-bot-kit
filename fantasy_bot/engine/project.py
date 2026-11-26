"""Rest-of-week projection for a roster.

Per player:  per-game rate = 60% last-14-days + 40% season (season only if < 3 recent games).
Per day:     players with a game compete for 10 starting slots. Bench games don't count,
             so we fill slots best-player-first with an augmenting-path matching.
Status:      chance he actually plays (O/INJ = 0, Q/GTD = 60%, D = 30%, healthy = 95%).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from fantasy_bot.nba.schedule import canon

COUNT = ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
RAW = ["fgm", "fga", "ftm", "fta"] + COUNT

DEFAULT_SLOTS = ["PG", "SG", "G", "SF", "PF", "F", "C", "C", "Util", "Util"]
SLOT_OK = {  # starting slot -> player positions allowed in it
    "PG": {"PG"}, "SG": {"SG"}, "G": {"PG", "SG"},
    "SF": {"SF"}, "PF": {"PF"}, "F": {"SF", "PF"},
    "C": {"C"}, "FC": {"SF", "PF", "C"}, "F/C": {"SF", "PF", "C"},
    "GF": {"SG", "SF"}, "G/F": {"SG", "SF"},
}
NON_STARTING = {"BN", "IL", "IL+", "NA"}


def starting_slots(roster_positions: str | None) -> list[str]:
    """'PG, SG, G, SF, PF, F, C, FC, Util, Util, BN, BN, BN, IL, IL' -> the starting slots."""
    if not roster_positions:
        return DEFAULT_SLOTS
    return [s.strip() for s in roster_positions.split(",") if s.strip() and s.strip() not in NON_STARTING]
PLAY_PROB = {None: 0.95, "P": 0.9, "Q": 0.6, "GTD": 0.6, "DTD": 0.6, "D": 0.3,
             "O": 0.0, "INJ": 0.0, "SUSP": 0.0, "NA": 0.0}

# Per-game variance as a multiple of the mean (counting stats are over-dispersed:
# points come in 2s and 3s, so PTS variance is far above its mean).
DISPERSION = {"3PTM": 1.6, "PTS": 7.0, "REB": 2.0, "AST": 2.0, "ST": 1.3, "BLK": 1.5, "TO": 1.4}


@dataclass
class Player:
    name: str
    team: str | None
    pos: list[str]
    status: str | None
    rate: dict[str, float]           # per game, RAW keys
    value: float                     # rough per-game fantasy value (for ordering only)
    avail_from: date | None = None   # waiver players: first ET date he'd be ours
    roster: str = ""
    rank_now: float | None = None
    rank_pre: float | None = None
    pct_ros: float | None = None     # % of Yahoo leagues rostering him: the crowd's long-term verdict
    season_value: float = 0.0        # per-game value over the whole season (not just recent form)
    gp14: int = 0
    slot: str | None = None          # current Yahoo slot (BN/IL/...) for rostered players
    l14_rate: dict | None = None     # per game, last 14 days / season (for context adjustments)
    season_rate: dict | None = None
    meta: dict = field(default_factory=dict)

    def fits(self, slot: str) -> bool:
        return slot == "Util" or bool(set(self.pos) & SLOT_OK.get(slot, set()))


def per_game(t: dict | None) -> dict[str, float] | None:
    if not t or not t.get("gp"):
        return None
    return {k: t.get(k, 0) / t["gp"] for k in RAW}


def blend(l14: dict | None, season: dict | None) -> tuple[dict[str, float], int]:
    a, b = per_game(l14), per_game(season)
    gp14 = (l14 or {}).get("gp", 0)
    if a and b and gp14 >= 3:
        return {k: 0.6 * a[k] + 0.4 * b[k] for k in RAW}, gp14
    return (b or a or {k: 0.0 for k in RAW}), gp14


def fantasy_value(r: dict[str, float]) -> float:
    # Shooting impact = makes above a league-average shooter on the same attempts,
    # so a 64% big on 9 shots counts for FG%, and a 37% gunner counts against it.
    fg_impact = r["fgm"] - 0.47 * r["fga"]
    ft_impact = r["ftm"] - 0.78 * r["fta"]
    return (r["PTS"] + 1.2 * r["REB"] + 1.5 * r["AST"] + 3 * r["ST"] + 3 * r["BLK"]
            + 1.5 * r["3PTM"] - r["TO"] + 6 * fg_impact + 4 * ft_impact)


_W_DATE = re.compile(r"W \((\w{3}) (\d{1,2})\)")


def waiver_date(roster: str, year: int) -> date | None:
    m = _W_DATE.search(roster or "")
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)} {m.group(2)} {year}", "%b %d %Y").date()


def long_term_value(p: "Player") -> float:
    """0..1: half season production (value 50/game ~ an early-round player = 1.0),
    half the share of Yahoo leagues that roster him."""
    prod = max(0.0, min(1.0, p.season_value / 50))
    crowd = (p.pct_ros if p.pct_ros is not None else 0) / 100
    return 0.5 * prod + 0.5 * crowd


def to_player(p: dict, year: int, slot: str | None = None) -> Player:
    rate, gp14 = blend(p.get("l14"), p.get("season"))
    season_rate = per_game(p.get("season")) or rate
    return Player(
        name=p["name"], team=canon(p.get("team")), pos=(p.get("pos") or "").split(","),
        status=p.get("status"), rate=rate, value=fantasy_value(rate),
        avail_from=waiver_date(p.get("roster", ""), year), roster=p.get("roster", ""),
        rank_now=p.get("rank_now"), rank_pre=p.get("rank_pre"), pct_ros=p.get("pct_ros"),
        season_value=fantasy_value(season_rate), gp14=gp14, slot=slot,
        l14_rate=per_game(p.get("l14")), season_rate=per_game(p.get("season")),
    )


def _match(players: list[Player], slots: list[str]) -> list[Player]:
    """Max starters for one day, preferring higher-value players (greedy augmenting paths)."""
    slot_owner: dict[int, Player] = {}

    def try_assign(pl: Player, seen: set[int]) -> bool:
        for i, s in enumerate(slots):
            if pl.fits(s) and i not in seen:
                seen.add(i)
                if i not in slot_owner or try_assign(slot_owner[i], seen):
                    slot_owner[i] = pl
                    return True
        return False

    for pl in sorted(players, key=lambda x: -x.value):
        try_assign(pl, set())
    return list(slot_owner.values())


@dataclass
class Projection:
    mean: dict[str, float]           # RAW totals for rest of week
    var: dict[str, float]            # variance of counting stats + fgm/ftm
    games: int                       # expected started games
    per_day: dict[date, list[str]]   # who starts each day
    benched_games: int               # games lost to the slot crunch


def project(roster: list[Player], days: dict[date, set[str]],
            slots: list[str] = DEFAULT_SLOTS) -> Projection:
    mean = {k: 0.0 for k in RAW}
    var = {k: 0.0 for k in RAW}
    games, benched, per_day = 0.0, 0, {}
    for d, teams in sorted(days.items()):
        playing = [p for p in roster
                   if p.slot != "IL" and p.team in teams
                   and PLAY_PROB.get(p.status, 0.95) > 0
                   and (p.avail_from is None or d >= p.avail_from)]
        starters = _match(playing, slots)
        benched += len(playing) - len(starters)
        per_day[d] = [p.name for p in starters]
        for p in starters:
            q = PLAY_PROB.get(p.status, 0.95)
            games += q
            for k in RAW:
                mean[k] += q * p.rate[k]
            for k in COUNT:
                # variance of a "maybe plays" game: q*Var + q(1-q)*mean^2
                var[k] += q * DISPERSION[k] * p.rate[k] + q * (1 - q) * p.rate[k] ** 2
            for made, att in (("fgm", "fga"), ("ftm", "fta")):
                pct = p.rate[made] / p.rate[att] if p.rate[att] else 0
                var[made] += q * p.rate[att] * pct * (1 - pct) * 1.5
    return Projection(mean, var, round(games), per_day, benched)
