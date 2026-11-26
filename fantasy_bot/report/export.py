"""Plan -> JSON for the web dashboard (site/index.html reads site/report.json)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fantasy_bot.engine.recommend import Move, Plan


def _r(x: float, n: int = 3) -> float:
    return round(float(x), n)


def _move(m: Move) -> dict:
    r = m.add.rate
    return {
        "add": {"name": m.add.name, "team": m.add.team, "pos": "/".join(p for p in m.add.pos if p),
                "games": m.add_games, "waiver_clears": m.add.avail_from.isoformat() if m.add.avail_from else None,
                "first_game": m.first_day.isoformat() if m.first_day else None,
                "per_game": {k: _r(r[k], 1) for k in ("PTS", "REB", "AST", "ST", "BLK", "3PTM", "TO")},
                "fg": _r(r["fgm"] / r["fga"]) if r["fga"] else None,
                "teammate_back": m.add.meta.get("teammate_back"),
                "ft": _r(r["ftm"] / r["fta"]) if r["fta"] else None},
        "drop": ({"name": m.drop.name, "team": m.drop.team, "games": m.drop_games,
                  "rank": m.drop.rank_now, "teammate_back": m.drop.meta.get("teammate_back")}
                 if m.drop else None),
        "win_before": _r(m.before.p_win), "win_after": _r(m.after.p_win),
        "flipped": m.flipped(), "kind": m.kind,
        "lt_in": _r(m.lt_in, 2), "lt_out": _r(m.lt_out, 2), "weight": m.weight, "score": _r(m.score),
        "next_in": m.next_in, "next_out": m.next_out,
        "value_in": round(m.add.value), "value_out": round(m.drop.value) if m.drop else 0,
    }


def plan_json(p: Plan) -> dict:
    return {
        "league": p.league["name"], "key": p.league["key"], "opponent": p.opp_name,
        "score": list(p.score), "win": _r(p.base.p_win), "expected_cats": _r(p.base.expected_cats, 1),
        "days_left": p.days_left, "my_games": p.my_games, "opp_games": p.opp_games,
        "adds_left": p.adds_left, "max_adds": p.max_adds, "mode": p.mode,
        "cats": [{"cat": c.cat, "me": _r(c.me), "opp": _r(c.opp), "p": _r(c.p_win), "label": c.label}
                 for c in p.base.cats],
        "moves": [_move(m) for m in p.moves],
        "il_moves": p.il_moves, "lineup": p.lineup,
        "injuries": p.injury_notes, "warnings": p.warnings, "notes": p.notes,
        "opp_adds_left": p.opp_adds_left, "opp_expected_adds": p.opp_expected_adds,
    }


def write_report(plans: list[Plan], path: Path, alerts: list[str] | None = None) -> dict:
    doc = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "leagues": [plan_json(p) for p in plans], "alerts": alerts or []}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc
