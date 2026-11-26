"""Are the bot's win percentages honest?

Every full run logs its predictions to data/predictions/<date>-<league>.json.
On Mondays it also logs last week's final result. This script pairs them and prints a
Brier score per category (0 = perfect, 0.25 = coin flip) plus how often "80%" calls came true.

uv run python -m fantasy_bot.calibrate
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

from fantasy_bot.config import CATS, LOWER_WINS
from fantasy_bot.yahoo.browser import ROOT

PRED_DIR = ROOT / "data" / "predictions"


def outcome(me: dict, opp: dict) -> dict[str, float]:
    """Final category results: 1 win, 0 loss, 0.5 tie."""
    out = {}
    for c in CATS:
        a, b = me.get(c) or 0, opp.get(c) or 0
        if c in LOWER_WINS:
            a, b = b, a
        out[c] = 1.0 if a > b else 0.0 if a < b else 0.5
    out["MATCHUP"] = 1.0 if sum(out[c] for c in CATS) > 4.5 else 0.0
    return out


def log_prediction(plan, data: dict, today: date) -> None:
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"date": today.isoformat(), "league": plan.league["key"], "week": data.get("week"),
           "days_left": plan.days_left, "p_win": plan.base.p_win,
           "cats": {c.cat: c.p_win for c in plan.base.cats}}
    lw = data.get("last_week")
    if lw and data.get("week"):
        rec["final_of_week"] = data["week"] - 1
        rec["final"] = outcome(lw.me.stats, lw.opp.stats)
    (PRED_DIR / f"{today.isoformat()}-{plan.league['key']}.json").write_text(json.dumps(rec), encoding="utf-8")


def score() -> str:
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PRED_DIR.glob("*.json"))]
    finals = {(r["league"], r["final_of_week"]): r["final"] for r in recs if "final" in r}
    sq, n = defaultdict(float), defaultdict(int)
    buckets = defaultdict(lambda: [0, 0.0])        # "70-80%" -> [calls, hits]
    for r in recs:
        f = finals.get((r["league"], r.get("week")))
        if not f:
            continue
        for c, p in list(r["cats"].items()) + [("MATCHUP", r["p_win"])]:
            sq[c] += (p - f[c]) ** 2
            n[c] += 1
            b = f"{int(p * 10) * 10}-{int(p * 10) * 10 + 10}%"
            buckets[b][0] += 1
            buckets[b][1] += f[c]
    if not n:
        return "No finished weeks logged yet. Needs at least one Monday run after a logged week."
    lines = ["Brier score (lower is better; 0.25 = coin flip):"]
    lines += [f"  {c:<8} {sq[c] / n[c]:.3f}  ({n[c]} predictions)" for c in CATS + ["MATCHUP"] if n[c]]
    lines.append("When the bot said X%, it happened:")
    for b in sorted(buckets, key=lambda s: int(s.split("-")[0])):
        calls, hits = buckets[b]
        lines.append(f"  {b:<8} {hits / calls:.0%} of {calls}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(score())
