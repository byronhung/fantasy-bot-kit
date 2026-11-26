"""Category win probabilities for the current H2H week.

final = what's already banked this week (from the matchup page) + projected rest of week.
Win chance per category = P(my final beats theirs), normal approximation.
Matchup win = P(I win at least 5 of 9 categories).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from fantasy_bot.engine.project import Projection
from fantasy_bot.yahoo.parse import TeamLine

CATS = ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
LOCK, LOST = 0.85, 0.15


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass
class CatState:
    cat: str
    me: float
    opp: float
    p_win: float
    label: str  # locked / swing / lost


@dataclass
class Outlook:
    cats: list[CatState]
    expected_cats: float
    p_win: float


def _final(line: TeamLine, proj: Projection) -> tuple[dict, dict]:
    fgm0, fga0 = line.fgm_a or (0, 0)
    ftm0, fta0 = line.ftm_a or (0, 0)
    m, v = proj.mean, proj.var
    out, var = {}, {}
    fga = fga0 + m["fga"]
    fta = fta0 + m["fta"]
    out["FG%"] = (fgm0 + m["fgm"]) / fga if fga else 0
    out["FT%"] = (ftm0 + m["ftm"]) / fta if fta else 0
    var["FG%"] = v["fgm"] / fga ** 2 if fga else 0
    var["FT%"] = v["ftm"] / fta ** 2 if fta else 0
    for c in ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]:
        out[c] = (line.stats.get(c) or 0) + m[c]
        var[c] = v[c]
    return out, var


def outlook(me: TeamLine, my_proj: Projection, opp: TeamLine, opp_proj: Projection) -> Outlook:
    a, va = _final(me, my_proj)
    b, vb = _final(opp, opp_proj)
    cats = []
    for c in CATS:
        diff = (b[c] - a[c]) if c == "TO" else (a[c] - b[c])
        sd = math.sqrt(va[c] + vb[c])
        p = (1.0 if diff > 0 else 0.0 if diff < 0 else 0.5) if sd < 1e-9 else phi(diff / sd)
        label = "locked" if p >= LOCK else "lost" if p <= LOST else "swing"
        cats.append(CatState(c, a[c], b[c], p, label))
    # P(win >= 5 cats): Poisson-binomial by dynamic programming
    dist = [1.0]
    for cs in cats:
        nxt = [0.0] * (len(dist) + 1)
        for k, pk in enumerate(dist):
            nxt[k] += pk * (1 - cs.p_win)
            nxt[k + 1] += pk * cs.p_win
        dist = nxt
    return Outlook(cats, sum(c.p_win for c in cats), sum(dist[5:]))
