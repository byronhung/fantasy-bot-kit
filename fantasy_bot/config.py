"""Settings. Your leagues are NOT in the code: they come from

  1. the FBOT_LEAGUES environment variable (JSON), which GitHub Actions fills from the
     repository variable LEAGUES, or
  2. leagues.json in the repo root (git-ignored), written by `python -m fantasy_bot.setup leagues`.

Each league: {"key": "main", "name": "<your team name>", "league_id": "123456", "team_id": "3"}
Optional per league: "long_term_weight" (see below).
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEAGUES_FILE = ROOT / "leagues.json"


def load_leagues() -> list[dict]:
    raw = os.environ.get("FBOT_LEAGUES") or (
        LEAGUES_FILE.read_text(encoding="utf-8") if LEAGUES_FILE.exists() else "")
    if not raw.strip():
        return []
    leagues = json.loads(raw)
    for lg in leagues:
        for k in ("key", "name", "league_id", "team_id"):
            if not lg.get(k):
                raise SystemExit(f"League entry missing '{k}': {lg}")
    return leagues


LEAGUES = load_leagues()

BASE = "https://basketball.fantasysports.yahoo.com/nba"

# How much a move's rest-of-season impact counts against this week's win chance.
#   move score = (this week's win % gained) + LONG_TERM_WEIGHT * (long-term value in - long-term value out)
# Long-term value is 0..1 (half season production, half % of Yahoo leagues rostering him).
#   0    = pure weekly streaming: drop anyone if it wins this week
#   0.5  = balanced (default): dropping a keeper for a stream must win you a lot this week
#   1.0+ = protect the season: only moves that also hold up long-term
# Override per league with "long_term_weight" in that league's entry.
LONG_TERM_WEIGHT = 0.5

# 9-cat H2H. For TO, lower wins.
CATS = ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
LOWER_WINS = {"TO"}
