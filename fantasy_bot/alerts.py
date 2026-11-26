"""Short alert runs between the daily reports.

check  (07:00 Manila, before the first tip-off): reads your Yahoo lineups. Alerts if a
       starter is ruled out tonight, or a starter has no game while a bench player does.
watch  (every 20 min during games): ESPN injury feed only, no Yahoo login. Alerts on
       injury news newer than the last item seen for each player on your rosters.
Both send nothing when there's nothing new; repeats are suppressed for 24 h.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fantasy_bot.config import LEAGUES
from fantasy_bot.nba import injuries as inj
from fantasy_bot.nba.schedule import scoreboard, today_et, canon
from fantasy_bot.report.notify import push_once
from fantasy_bot.yahoo.browser import ROOT

ROSTER_CACHE = ROOT / "data" / "roster.json"
SEEN_CACHE = ROOT / "data" / "watch_seen.json"   # player -> date of the last ESPN item we alerted on
BENCH_SLOTS = {"BN", "IL", "IL+", "--", None}


def save_roster_cache(rosters: dict[str, list[dict]]) -> None:
    ROSTER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ROSTER_CACHE.write_text(json.dumps(rosters, indent=1), encoding="utf-8")


def _status(p: dict, news: dict) -> tuple[str | None, str]:
    n = news.get(inj.norm(p["name"]))
    if n is None and p.get("short_name"):   # newer matchup layout: "A. Black" -> match on initial + surname
        from fantasy_bot.yahoo.parse import short_key
        k = short_key(p["name"])
        n = next((v for v in news.values() if short_key(v["name"]) == k), None)
    espn = inj.to_yahoo_status(n["status"]) if n else None
    return (p.get("status") or espn), (n["short"] if n else "")


def lineup_alerts(league_name: str, players: list[dict], playing: set[str], news: dict) -> list[str]:
    out = []
    starters = [p for p in players if p.get("slot") not in BENCH_SLOTS and p.get("team")]
    bench = [p for p in players if p.get("slot") == "BN" and p.get("team")]
    bench_live = [p["name"] for p in bench if canon(p["team"]) in playing and _status(p, news)[0] not in ("O", "INJ")]
    for p in starters:
        if canon(p["team"]) not in playing:
            continue
        st, note = _status(p, news)
        if st in ("O", "INJ"):
            alt = f" Bench options playing today: {', '.join(bench_live)}." if bench_live else ""
            out.append(f"{league_name}: {p['name']} is in your lineup but OUT tonight. {note}{alt}".strip())
        elif st in ("GTD", "Q", "D", "DTD"):
            out.append(f"{league_name}: {p['name']} ({st}) is a game-time call. {note}".strip())
    idle = [p["name"] for p in starters if canon(p["team"]) not in playing]
    if idle and bench_live:
        out.append(f"{league_name}: starters with no game today: {', '.join(idle)}. "
                   f"On your bench with a game: {', '.join(bench_live)}. Swap if positions allow.")
    return out


def check(send: bool = True) -> list[str]:
    from fantasy_bot.yahoo.reader import read_matchups  # needs the browser; watch doesn't
    mus = read_matchups()
    today = today_et()
    playing = {t for g in scoreboard(today) if g["status"] == "STATUS_SCHEDULED" for t in (g["home"], g["away"])}
    news = inj.fetch()
    alerts = []
    for lg in LEAGUES:
        alerts += lineup_alerts(lg["name"], mus[lg["key"]].my_players, playing, news)
    if not send:
        return alerts
    return push_once(alerts, title="Fantasy bot: before tip-off") if alerts else []


def fresh_news(rosters: dict, news: dict, seen: dict[str, str], now: datetime,
               first_look_h: int = 12) -> tuple[list[str], dict[str, str]]:
    """News newer than what we last alerted on for that player (or, for a player we've never
    alerted on, newer than first_look_h hours). Runs can come hours apart; nothing falls through."""
    alerts, seen = [], dict(seen)
    first_cut = now - timedelta(hours=first_look_h)
    for lg in LEAGUES:
        for p in rosters.get(lg["key"], []):
            if p.get("slot") == "IL":
                continue
            key = inj.norm(p["name"])
            n = news.get(key)
            if not n or not n["date"]:
                continue
            when = datetime.strptime(n["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            last = seen.get(key)
            is_new = when > datetime.fromisoformat(last) if last else when >= first_cut
            if is_new:
                alerts.append(f"{lg['name']}: {n['name']} ({n['status']}). {n['short']}")
            seen[key] = max(when, datetime.fromisoformat(last)).isoformat() if last else when.isoformat()
    return alerts, seen


def watch(send: bool = True) -> list[str]:
    if not ROSTER_CACHE.exists():
        return []
    rosters = json.loads(ROSTER_CACHE.read_text(encoding="utf-8"))
    seen = json.loads(SEEN_CACHE.read_text(encoding="utf-8")) if SEEN_CACHE.exists() else {}
    alerts, seen = fresh_news(rosters, inj.fetch(), seen, datetime.now(timezone.utc))
    if not send:
        return alerts
    sent = push_once(alerts, title="Fantasy bot: injury news") if alerts else []
    SEEN_CACHE.write_text(json.dumps(seen, indent=1), encoding="utf-8")
    return sent
