"""Pick the add/drops that best balance this week's win chance against long-term value.

move score = (this week's matchup-win % gained)
           + LONG_TERM_WEIGHT * (long-term value of the add - long-term value of the drop)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from fantasy_bot.config import LONG_TERM_WEIGHT
from fantasy_bot.engine.context import (
    apply_teammate_returns, expected_opp_adds, opp_with_streamers, stars_back, team_games_14,
)
from fantasy_bot.engine.matchup import Outlook, outlook
from fantasy_bot.yahoo.parse import SlotLookup
from fantasy_bot.engine.project import (
    NON_STARTING, Player, long_term_value, project, starting_slots, to_player,
)

PROTECT_TOP = 8        # safety net: never drop your 8 most productive players, whatever the weight
MIN_GAIN = 0.01        # ignore moves scoring < 1 point
IL_STATUSES = {"O", "INJ"}

# Dead-week mode: below this win chance, this week's adds would go to waste, so spend them
# on next week instead: long-term value + next week's production (value x games).
DEAD_WEEK = 0.05
NEXT_WEEK_SCALE = 200  # value x games of a solid 4-game week (~4 x 50) counts as 1.0
DEAD_MIN_SCORE = 0.05


@dataclass
class Move:
    add: Player
    drop: Player | None
    before: Outlook
    after: Outlook
    add_games: int
    drop_games: int
    first_day: date | None
    kind: str                     # "stream" (short-term) or "upgrade"
    lt_in: float = 0.0            # long-term value of the add (0..1)
    lt_out: float = 0.0           # long-term value of the drop (0..1)
    weight: float = LONG_TERM_WEIGHT
    next_in: int = 0              # dead-week mode: next week's games for the add / the drop
    next_out: int = 0
    dead_score: float | None = None

    @property
    def gain(self) -> float:
        """This week's matchup-win % gained."""
        return self.after.p_win - self.before.p_win

    @property
    def lt_delta(self) -> float:
        return self.lt_in - self.lt_out

    @property
    def score(self) -> float:
        if self.dead_score is not None:
            return self.dead_score
        return self.gain + self.weight * self.lt_delta

    def flipped(self) -> list[str]:
        b = {c.cat: c.p_win for c in self.before.cats}
        return [c.cat for c in self.after.cats if c.p_win - b[c.cat] >= 0.08]


@dataclass
class Plan:
    league: dict
    opp_name: str
    score: tuple[int, int]
    base: Outlook
    adds_used: int
    adds_left: int
    max_adds: int
    moves: list[Move]
    il_moves: list[str] = field(default_factory=list)
    lineup: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    injury_notes: list[str] = field(default_factory=list)
    days_left: int = 0
    my_games: int = 0
    opp_games: int = 0
    mode: str = "this_week"       # or "next_week" when this week is already lost
    notes: list[str] = field(default_factory=list)   # context the projection accounted for
    opp_adds_left: int = 0
    opp_expected_adds: int = 0


def adds_this_week(adds: list[dict], team: str, today: date) -> int:
    monday = today - timedelta(days=today.weekday())
    n = 0
    for a in adds:
        if a["team"] != team:
            continue
        d = datetime.strptime(f"{a['date']} {today.year}", "%b %d %Y").date()
        if d > today:  # "Dec 30" seen in January
            d = d.replace(year=today.year - 1)
        if d >= monday:
            n += 1
    return n


def _games(p: Player, days: dict[date, set[str]]) -> int:
    return sum(1 for d, t in days.items() if p.team in t and (p.avail_from is None or d >= p.avail_from))


def _int(s: str | None, default: int) -> int:
    try:
        return int(s)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _dead_week_moves(roster: list[Player], fas: list[Player], next_days: dict[date, set[str]],
                     base: Outlook, n: int, open_spots: int) -> list[Move]:
    """This week is lost: pick adds that make next week's roster better."""
    moves, taken = [], set()
    roster = list(roster)
    # The NBA leaves some dates TBD (e.g. NBA Cup knockout week) and fills them in later.
    # A normal week has ~50 games (100 team-games); if it's far short, games can't be trusted,
    # so give everyone the same count and decide on per-game value alone.
    slots = sum(len(t) for t in next_days.values())
    if slots < 80 or any("TBD" in t for t in next_days.values()):
        next_days = {}
    flat = 3.5 if not next_days else None
    for _ in range(n):
        active = [p for p in roster if p.slot != "IL"]
        protected = {p.name for p in sorted(active, key=lambda p: -p.value)[:PROTECT_TOP]}
        drops: list[Player | None] = [None] if open_spots > 0 else [p for p in active if p.name not in protected]
        best: Move | None = None
        for fa in fas:
            if fa.name in taken:
                continue
            g_in = flat or sum(1 for t in next_days.values() if fa.team in t)
            for dr in drops:
                g_out = flat or sum(1 for t in next_days.values() if dr and dr.team in t)
                lt_in, lt_out = long_term_value(fa), long_term_value(dr) if dr else 0.0
                prod = (fa.value * g_in - (dr.value * g_out if dr else 0)) / NEXT_WEEK_SCALE
                s = 0.5 * (lt_in - lt_out) + 0.5 * prod
                if best is None or s > best.score:
                    best = Move(fa, dr, base, base, 0, 0, None,
                                "upgrade" if lt_in >= lt_out else "stream",
                                lt_in=lt_in, lt_out=lt_out, weight=0.5,
                                next_in=g_in, next_out=g_out, dead_score=s)
        if best is None or best.score < DEAD_MIN_SCORE:
            break
        moves.append(best)
        taken.add(best.add.name)
        best.add.slot = "BN"
        roster = [p for p in roster if p is not best.drop] + [best.add]
        if best.drop is None:
            open_spots -= 1
    return moves


def build_plan(data: dict, days: dict[date, set[str]], today: date,
               next_days: dict[date, set[str]] | None = None) -> Plan:
    lg, mu, st = data["league"], data["matchup"], data.get("settings", {})
    year = today.year
    positions = [s.strip() for s in st.get("Roster Positions", "").split(",") if s.strip()]
    slots = starting_slots(st.get("Roster Positions"))
    active_cap = len([s for s in positions if s not in ("IL", "IL+", "NA")]) or 13
    il_cap = positions.count("IL") + positions.count("IL+")
    max_adds = _int(st.get("Max Acquisitions per Week"), 4)

    slot_of, opp_slot = SlotLookup(mu.my_players), SlotLookup(mu.opp_players)
    mine = [to_player(p, year, slot_of.get(p)) for p in data["mine"]]
    opp = [to_player(p, year, opp_slot.get(p)) for p in data["opp"]]
    fas = [to_player(f, year) for f in data["fas"]]
    fas = [f for f in fas if f.status not in IL_STATUSES and (f.roster == "FA" or f.avail_from)]

    # Star teammates coming back: deflate role players whose recent numbers came without them.
    stars = data.get("stars", [])
    back = stars_back(stars, team_games_14([data["mine"], data["opp"], data["fas"], stars]))
    notes = apply_teammate_returns(mine, back)
    apply_teammate_returns(opp + fas, back)

    # The opponent keeps streaming: add the adds they'll probably still make.
    opp_used = adds_this_week(data["adds"], mu.opp.name, today)
    opp_left = max(0, max_adds - opp_used)
    opp_exp = expected_opp_adds(data["adds"], mu.opp.name, opp_used, opp_left, today, len(days))
    opp, streamers = opp_with_streamers(opp, fas, opp_exp, {f.name: _games(f, days) for f in fas})
    if streamers:
        notes.append(f"{mu.opp.name} has used {opp_used} of {max_adds} adds; expecting about {opp_exp} more "
                     f"(streamers like {', '.join(streamers[:2])}). Win % already counts them.")

    opp_proj = project(opp, days, slots)

    def run(roster: list[Player]) -> tuple[Outlook, int]:
        pr = project(roster, days, slots)
        return outlook(mu.me, pr, mu.opp, opp_proj), pr.games

    used = adds_this_week(data["adds"], lg["name"], today)
    left = max(0, max_adds - used)

    # Roster housekeeping: open spots, IL moves, healthy players stuck on IL.
    warnings = []
    on_il = [p for p in mine if p.slot == "IL"]
    for p in on_il:
        if p.status not in IL_STATUSES:
            warnings.append(f"{p.name} is on IL but healthy/not IL-eligible: Yahoo blocks adds until he's moved off.")
    empty_active = max(0, active_cap - (len(mine) - len(on_il)))
    empty_il = max(0, il_cap - len(on_il))
    il_moves = []
    for p in sorted([p for p in mine if p.slot != "IL" and p.status in IL_STATUSES], key=lambda p: -p.value)[:empty_il]:
        il_moves.append(p.name)
        p.slot = "IL"
        empty_active += 1

    base, my_games = run(mine)
    plan = Plan(lg, mu.opp.name, (mu.me.cats_won or 0, mu.opp.cats_won or 0), base, used, left, max_adds, [],
                il_moves=il_moves, warnings=warnings,
                days_left=len(days), my_games=my_games, opp_games=opp_proj.games,
                notes=notes, opp_adds_left=opp_left, opp_expected_adds=opp_exp)

    # Move search, greedy: best single move, apply it, search again.
    roster = list(mine)
    current = base
    taken = set()
    weight = lg.get("long_term_weight", LONG_TERM_WEIGHT)
    dead = base.p_win < DEAD_WEEK and next_days is not None and left > 0
    if dead:
        plan.mode = "next_week"
        plan.moves = _dead_week_moves(roster, fas, next_days, base, min(left, 2), empty_active)
        for m in plan.moves:
            roster = [p for p in roster if p is not m.drop] + [m.add]
    for _ in range(0 if dead else min(left, 3)):
        active = [p for p in roster if p.slot != "IL"]
        protected = {p.name for p in sorted(active, key=lambda p: -p.value)[:PROTECT_TOP]}
        drops: list[Player | None] = [None] if empty_active > 0 else [p for p in active if p.name not in protected]
        best: Move | None = None
        for fa in fas:
            if fa.name in taken:
                continue
            g = _games(fa, days)
            if g == 0:
                continue
            lt_in = long_term_value(fa)
            for dr in drops:
                trial = [p for p in roster if p is not dr] + [fa]
                after, _ = run(trial)
                lt_out = long_term_value(dr) if dr else 0.0
                gain = after.p_win - current.p_win
                if gain <= 0:
                    # Only moves that help this week compete. Otherwise a long-term-only move
                    # (worse this week) could top the score and end the search with no picks.
                    continue
                score = gain + weight * (lt_in - lt_out)
                if best is None or score > best.score + 1e-9:
                    first = min((d for d, t in days.items() if fa.team in t
                                 and (fa.avail_from is None or d >= fa.avail_from)), default=None)
                    best = Move(fa, dr, current, after, g, _games(dr, days) if dr else 0, first,
                                "upgrade" if lt_in >= lt_out else "stream",
                                lt_in=lt_in, lt_out=lt_out, weight=weight)
        if best is None or best.score < MIN_GAIN or best.gain <= 0:
            break
        plan.moves.append(best)
        taken.add(best.add.name)
        best.add.slot = "BN"
        roster = [p for p in roster if p is not best.drop] + [best.add]
        if best.drop is None:
            empty_active -= 1
        current = best.after

    # Today's lineup on the roster *after* the moves.
    if today in days:
        best_today = set(project(roster, {today: days[today]}, slots).per_day[today])
        for p in roster:
            if p.name in best_today and p.slot in ("BN", None):
                plan.lineup.append(f"START {p.name} (plays today)")
            elif p.slot not in NON_STARTING and p.slot is not None and p.name not in best_today:
                why = p.status if p.status in IL_STATUSES else "no game" if p.team not in days[today] else "sit"
                if why != "no game" or any(q.name in best_today and q.slot in ("BN", None) for q in roster):
                    plan.lineup.append(f"BENCH {p.name} ({why})")
    return plan
