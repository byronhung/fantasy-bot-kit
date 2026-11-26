"""ESPN's public injury feed: status + beat-writer note per player, updated through game nights."""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.request

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"


def norm(name: str) -> str:
    """'Nikola Jokić' / 'Nikola Jokic' / 'Trey Murphy III' -> comparable key."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[.'’]", "", s.lower())
    s = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", s.strip())
    return re.sub(r"\s+", " ", s)


def fetch() -> dict[str, dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    out = {}
    for team in data.get("injuries", []):
        for i in team.get("injuries", []):
            a = i.get("athlete", {})
            out[norm(a.get("displayName", ""))] = {
                "name": a.get("displayName", ""),
                "status": i.get("status", ""),          # "Out", "Day-To-Day", ...
                "short": i.get("shortComment", ""),
                "long": i.get("longComment", ""),
                "date": i.get("date", ""),
                "team": team.get("displayName", ""),
            }
    return out


def to_yahoo_status(espn_status: str) -> str | None:
    s = espn_status.lower()
    if s.startswith("out"):
        return "O"
    if "day-to-day" in s or "questionable" in s:
        return "GTD"
    if "doubtful" in s:
        return "D"
    return None
