"""Turn a Plan into the short push text and the full report text."""
from __future__ import annotations

from fantasy_bot.engine.recommend import Plan

ICON = {"locked": "✅", "swing": "⚔️", "lost": "❌"}


def _v(cat: str, x: float) -> str:
    return f"{x:.3f}".lstrip("0") if cat in ("FG%", "FT%") else f"{x:.0f}"


def _last(name: str) -> str:
    parts = name.split()
    return parts[-1] if len(parts) > 1 and parts[-1] not in ("Jr.", "Sr.", "II", "III", "IV") else name


def short(plan: Plan) -> str:
    """One line per league for the push; details live on the dashboard."""
    head = f"{plan.league['name']} {plan.score[0]}-{plan.score[1]} · {plan.base.p_win:.0%}"
    if plan.moves:
        m = plan.moves[0]
        act = f"ADD {_last(m.add.name)}" + (f" / DROP {_last(m.drop.name)}" if m.drop else "")
        more = f" (+{len(plan.moves) - 1} more)" if len(plan.moves) > 1 else ""
        tail = ("next week: " if plan.mode == "next_week" else "") + act + more
    else:
        tail = "hold"
    extra = " · IL: " + ", ".join(_last(s) for s in plan.il_moves) if plan.il_moves else ""
    return f"{head} · {tail}{extra}"


def full(plan: Plan) -> str:
    L = [f"{plan.league['name'].upper()} vs {plan.opp_name}",
         f"Now {plan.score[0]}-{plan.score[1]}. {plan.days_left} days left. "
         f"Games left: you {plan.my_games}, them {plan.opp_games}.",
         f"Win chance: {plan.base.p_win:.0%} (expected {plan.base.expected_cats:.1f} cats)", "",
         "CATEGORY BOARD (projected end of week)"]
    for c in plan.base.cats:
        L.append(f" {c.cat:<5} {ICON[c.label]} {c.label:<6} {_v(c.cat, c.me):>6} vs {_v(c.cat, c.opp):<6} {c.p_win:.0%}")
    L += ["", f"MOVES ({plan.adds_left} of {plan.max_adds} adds left)"]
    if plan.mode == "next_week":
        L.append(" This week is gone. These adds build next week's roster (games next week shown).")
        def g(n):
            return "schedule TBD" if isinstance(n, float) else f"{n}G next week"
        for i, m in enumerate(plan.moves, 1):
            drop = f"DROP {m.drop.name} ({g(m.next_out)})" if m.drop else "into the open spot"
            L.append(f" {i}. ADD {m.add.name} ({m.add.team}, {g(m.next_in)}), {drop}")
            L.append(f"    Long-term value {m.lt_in:.2f} vs {m.lt_out:.2f}; per-game value "
                     f"{m.add.value:.0f} vs {m.drop.value if m.drop else 0:.0f}.")
        if not plan.moves:
            L.append(" Hold. Nobody available beats your roster for next week.")
    for i, m in enumerate(plan.moves if plan.mode != "next_week" else [], 1):
        rk = f", Yahoo rank {m.drop.rank_now:.0f}" if m.drop and m.drop.rank_now else ""
        drop = f"DROP {m.drop.name} ({m.drop_games}G left{rk})" if m.drop else "into the open spot"
        r = m.add.rate
        L.append(f" {i}. ADD {m.add.name} ({m.add.team}, {m.add_games}G left), {drop}")
        L.append(f"    Win chance {m.before.p_win:.0%} -> {m.after.p_win:.0%}. Moves: {', '.join(m.flipped()) or 'small edges'}.")
        if m.drop:
            L.append(f"    Long-term value: {m.add.name} {m.lt_in:.2f} vs {m.drop.name} {m.lt_out:.2f} "
                     f"({m.lt_delta:+.2f} x weight {m.weight} = {m.weight * m.lt_delta:+.0%}). "
                     f"Move score {m.score:+.0%}.")
        L.append(f"    Per game: {r['PTS']:.1f} pts, {r['REB']:.1f} reb, {r['AST']:.1f} ast, {r['ST']:.1f} stl, "
                 f"{r['BLK']:.1f} blk, {r['3PTM']:.1f} 3pm, {r['TO']:.1f} to"
                 + (f", FG {r['fgm']/r['fga']:.0%}" if r['fga'] else ""))
        note = []
        if m.add.avail_from:
            note.append(f"on waivers, clears {m.add.avail_from:%a %b %d}")
        if m.first_day:
            note.append(f"first game {m.first_day:%a}")
        if m.kind == "stream":
            note.append("streaming pickup: he's worse long-term than who you drop")
        for who in (m.add, m.drop):
            if who and who.meta.get("teammate_back"):
                note.append(f"{who.name}'s recent numbers came while {' & '.join(who.meta['teammate_back'])} "
                            "sat out, so he's projected closer to his season form")
        if note:
            L.append("    " + "; ".join(note) + ".")
    if not plan.moves and plan.mode != "next_week":
        L.append(" Hold. No available player raises your win chance by 1%+.")
    if plan.il_moves:
        L += ["", "ROSTER"] + [f" Move {s} to IL (frees a spot without a drop)" for s in plan.il_moves]
    if plan.lineup:
        L += ["", "TODAY'S LINEUP"] + [" " + s for s in plan.lineup]
    if plan.injury_notes:
        L += ["", "INJURY NEWS (your roster, ESPN)"] + [
            f" {n['name']} ({n['status']}, {n['date']}): {n['text']}" if isinstance(n, dict) else " " + n
            for n in plan.injury_notes]
    if plan.notes:
        L += ["", "ACCOUNTED FOR"] + [" " + n for n in plan.notes]
    if plan.warnings:
        L += ["", "WARNINGS"] + [" " + w for w in plan.warnings]
    return "\n".join(L)
