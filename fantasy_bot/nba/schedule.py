"""Games left in the fantasy week, from ESPN's public scoreboard feed.

Yahoo weeks run Monday to Sunday, US Eastern dates. A game counts as 'left'
only if it hasn't tipped off yet (ESPN status STATUS_SCHEDULED).
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# ESPN and Yahoo spell some teams differently; map everything to one spelling.
ALIAS = {"NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "UTH": "UTA", "WSH": "WAS",
         "GS": "GSW", "BRK": "BKN", "PHO": "PHX", "CHO": "CHA", "NOR": "NOP"}


def canon(team: str | None) -> str | None:
    return ALIAS.get(team, team) if team else team


def today_et(now: datetime | None = None) -> date:
    return (now or datetime.now(ET)).astimezone(ET).date()


def week_dates(now: datetime | None = None) -> list[date]:
    """Remaining ET dates in this Mon-Sun week, starting today."""
    d = today_et(now)
    sunday = d + timedelta(days=6 - d.weekday())
    return [d + timedelta(days=i) for i in range((sunday - d).days + 1)]


def scoreboard(d: date) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d:%Y%m%d}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    games = []
    for e in data.get("events", []):
        comp = e["competitions"][0]
        teams = {c["homeAway"]: canon(c["team"]["abbreviation"]) for c in comp["competitors"]}
        games.append({
            "date": d, "home": teams.get("home"), "away": teams.get("away"),
            "status": e["status"]["type"]["name"], "start_utc": e.get("date"),
        })
    return games


def next_week_games(now: datetime | None = None) -> dict[date, set[str]]:
    """{ET date: teams playing} for next Mon-Sun (used when this week is already lost)."""
    d = today_et(now)
    monday = d + timedelta(days=7 - d.weekday())
    return {monday + timedelta(days=i): {t for g in scoreboard(monday + timedelta(days=i))
                                          for t in (g["home"], g["away"])} for i in range(7)}


def remaining_games(now: datetime | None = None) -> dict[date, set[str]]:
    """{ET date: set of teams with a not-yet-started game that day} for the rest of the week."""
    out = {}
    for d in week_dates(now):
        out[d] = {t for g in scoreboard(d) if g["status"] == "STATUS_SCHEDULED" for t in (g["home"], g["away"])}
    return out
