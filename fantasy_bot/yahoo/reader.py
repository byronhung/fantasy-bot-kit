"""Fetch the Yahoo pages the bot needs, snapshot them, parse them."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from fantasy_bot.config import BASE, LEAGUES
from fantasy_bot.yahoo.browser import ROOT, LoginRequired, is_login_page, yahoo_context
from fantasy_bot.nba.schedule import today_et
from fantasy_bot.yahoo.parse import (
    current_week, find_team_id, parse_matchup, parse_players, parse_settings, parse_transactions,
)

SEASON = "S_S_2026"   # Yahoo's id for 2026-27 season totals
FA_PAGES = 3          # 25 per page -> top 75 available by current rank
STAR_PAGES = 4        # top 100 by preseason rank, last-14-day games: who has been sitting out


def snapshot_dir() -> Path:
    return ROOT / "data" / "raw" / f"{datetime.now():%Y-%m-%d_%H%M}"


class Session:
    """One logged-in browser for the whole run; every page is saved to out/."""

    def __init__(self, out: Path):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        self._cm = yahoo_context()
        self.ctx = self._cm.__enter__()
        self.page = self.ctx.new_page()
        return self

    def __exit__(self, *exc):
        return self._cm.__exit__(*exc)

    def get(self, name: str, url: str) -> str:
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(2000)
        if is_login_page(self.page.url):
            raise LoginRequired("Yahoo asked for login again.")
        html = self.page.content()
        (self.out / f"{name}.html").write_text(html, encoding="utf-8")
        time.sleep(1.2)
        return html


def player_urls(lid: str, status: str) -> dict[str, str]:
    q = f"{BASE}/{lid}/players?status={status}&pos=P&sort=AR&sdir=1"
    return {"l14": q + "&stat1=S_L14", "season": q + f"&stat1={SEASON}"}


def merge(l14: list[dict], season: list[dict]) -> list[dict]:
    by_name = {p["name"]: p for p in season}
    out = []
    for p in l14:
        s = by_name.get(p["name"])
        out.append({**p, "l14": _totals(p), "season": _totals(s) if s else None})
    return out


def _totals(p: dict) -> dict:
    keys = ["gp", "fgm", "fga", "ftm", "fta", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
    return {k: p.get(k, 0) for k in keys}


def read_league(s: Session, lg: dict) -> dict:
    lid, tid, key = lg["league_id"], lg["team_id"], lg["key"]
    mhtml, mu = get_matchup(s, lg)
    opp_id = find_team_id(mhtml, lid, mu.opp.name)

    def team_players(status: str, tag: str) -> list[dict]:
        u = player_urls(lid, status)
        l14 = parse_players(s.get(f"{key}-{tag}-l14", u["l14"]))
        season = parse_players(s.get(f"{key}-{tag}-season", u["season"]))
        return merge(l14, season)

    mine = team_players(tid, "mine")
    opp = team_players(opp_id, "opp") if opp_id else []

    fa_l14, fa_season = [], []
    for i in range(FA_PAGES):
        u = player_urls(lid, "A")
        off = f"&count={i * 25}"
        fa_l14 += parse_players(s.get(f"{key}-fa{i}-l14", u["l14"] + off))
        fa_season += parse_players(s.get(f"{key}-fa{i}-season", u["season"] + off))
    fas = merge(fa_l14, fa_season)

    stars = []
    for i in range(STAR_PAGES):
        u = f"{BASE}/{lid}/players?status=ALL&pos=P&sort=OR&sdir=1&stat1=S_L14&count={i * 25}"
        stars += parse_players(s.get(f"{key}-stars{i}", u))

    tx = parse_transactions(s.get(f"{key}-tx", f"{BASE}/{lid}/transactions?transactionsfilter=add"))
    settings = parse_settings(s.get(f"{key}-settings", f"{BASE}/{lid}/settings"))

    # Mondays: last week's final totals, so calibrate.py can score our predictions.
    week = current_week(mhtml)
    last_week = None
    if week and week > 1 and today_et().weekday() == 0:
        try:
            last_week = parse_matchup(s.get(f"{key}-matchup-w{week - 1}",
                                            f"{BASE}/{lid}/{tid}/matchup?week={week - 1}"))
        except ValueError:
            pass

    return {"league": lg, "matchup": mu, "opp_id": opp_id, "mine": mine, "opp": opp,
            "fas": fas, "stars": stars, "adds": tx, "settings": settings, "week": week, "last_week": last_week}


def read_all(out: Path | None = None) -> dict:
    with Session(out or snapshot_dir()) as s:
        return {lg["key"]: read_league(s, lg) for lg in LEAGUES}


def get_matchup(s: Session, lg: dict):
    """Matchup page, retried once: Yahoo sometimes serves a half-built page during live games."""
    url = f"{BASE}/{lg['league_id']}/{lg['team_id']}/matchup"
    html = s.get(f"{lg['key']}-matchup", url)
    try:
        return html, parse_matchup(html)
    except ValueError:
        s.page.wait_for_timeout(5000)
        html = s.get(f"{lg['key']}-matchup-retry", url)
        return html, parse_matchup(html)


def read_matchups(out: Path | None = None) -> dict:
    with Session(out or snapshot_dir()) as s:
        return {lg["key"]: get_matchup(s, lg)[1] for lg in LEAGUES}
