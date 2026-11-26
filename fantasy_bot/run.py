"""Entry point.

uv run python -m fantasy_bot.run                  # full report (15:00 Manila) + push
uv run python -m fantasy_bot.run --mode check     # pre-tip-off lineup check (07:00)
uv run python -m fantasy_bot.run --mode watch     # injury watch during games (no Yahoo)
add --no-send to print instead of pushing (full mode).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from fantasy_bot.alerts import check, save_roster_cache, watch
from fantasy_bot.calibrate import log_prediction
from fantasy_bot.config import LEAGUES
from fantasy_bot.engine.recommend import build_plan
from fantasy_bot.nba import injuries as inj
from fantasy_bot.nba.schedule import next_week_games, remaining_games, today_et
from fantasy_bot.report.export import write_report
from fantasy_bot.report.notify import push
from fantasy_bot.report.render import full, short
from fantasy_bot.yahoo.browser import ROOT, LoginRequired
from fantasy_bot.yahoo.parse import SlotLookup
from fantasy_bot.yahoo.reader import read_all

sys.stdout.reconfigure(encoding="utf-8")  # emoji in reports; Windows consoles default to cp1252


STALE_DAYS = 7
SITE_REPORT = ROOT / "site" / "report.json"


def _fresh(n: dict, now: datetime) -> bool:
    """Skip week-old blurbs unless the player is still Out (then the old news still matters)."""
    if not n.get("date") or n["status"] == "Out":
        return True
    when = datetime.strptime(n["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    return now - when <= timedelta(days=STALE_DAYS)


def apply_espn(data: dict, news: dict) -> None:
    """Yahoo's tags can lag; if ESPN already has a player Out, trust ESPN."""
    now = datetime.now(timezone.utc)
    for lg in data.values():
        notes = []
        for group in ("mine", "opp", "fas", "stars"):
            for p in lg.get(group, []):
                n = news.get(inj.norm(p["name"]))
                if not n:
                    continue
                espn = inj.to_yahoo_status(n["status"])
                p["espn_note"] = n["short"]
                if espn == "O" and p.get("status") not in ("O", "INJ"):
                    p["status"] = "O"
                # Yahoo's "O" is often just one game; ESPN day-to-day means he can return this week.
                elif espn == "GTD" and p.get("status") == "O":
                    p["status"] = "GTD"
                if group == "mine" and _fresh(n, now):
                    notes.append({"name": p["name"], "status": n["status"], "text": n["short"],
                                  "date": (n.get("date") or "")[:10]})
        lg["injury_notes"] = notes


def report_url() -> str | None:
    return os.environ.get("REPORT_URL") or None


def full_run(send: bool) -> None:
    data = read_all()
    try:
        apply_espn(data, inj.fetch())
    except Exception as e:  # ESPN down shouldn't kill the report
        print("ESPN injuries unavailable:", e)
    save_roster_cache({k: [{"name": p["name"], "team": p.get("team"), "slot": SlotLookup(v["matchup"].my_players).get(p)}
                           for p in v["mine"]]
                       for k, v in data.items()})
    days = remaining_games()
    today = today_et()
    try:
        next_days = next_week_games()
    except Exception as e:
        print("next week's schedule unavailable:", e)
        next_days = None
    plans = [build_plan(data[lg["key"]], days, today, next_days) for lg in LEAGUES]
    for p in plans:
        p.injury_notes = data[p.league["key"]].get("injury_notes", [])
        try:
            log_prediction(p, data[p.league["key"]], today)
        except Exception as e:
            print("prediction log failed:", e)
    write_report(plans, SITE_REPORT)
    print("\n\n".join(full(p) for p in plans))
    if send:
        push("\n".join(short(p) for p in plans), title="Fantasy bot: today's moves", click=report_url())


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["full", "check", "watch"], default="full")
    ap.add_argument("--no-send", action="store_true")
    a = ap.parse_args()
    if not LEAGUES:
        raise SystemExit("No leagues set up. Run: uv run python -m fantasy_bot.setup leagues "
                         "(in GitHub Actions: set the LEAGUES repository variable via the 'github' setup step).")
    try:
        if a.mode == "full":
            full_run(send=not a.no_send)
        elif a.mode == "check":
            print("alerts:", check(send=not a.no_send))
        else:
            print("alerts:", watch(send=not a.no_send))
    except LoginRequired:
        push("Yahoo login expired. On your PC, open Claude Code in the bot folder and type /setup (2 minutes).",
             title="Fantasy bot: re-login needed", priority="high", tags="warning")
        raise


if __name__ == "__main__":
    main()
