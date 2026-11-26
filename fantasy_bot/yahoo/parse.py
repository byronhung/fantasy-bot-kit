"""Turn saved Yahoo HTML into plain data. Pure functions: no network, easy to test."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from selectolax.lexbor import LexborHTMLParser

from fantasy_bot.config import CATS


@dataclass
class TeamLine:
    name: str
    stats: dict[str, float]          # CATS -> value
    fgm_a: tuple[int, int] | None = None
    ftm_a: tuple[int, int] | None = None
    cats_won: int | None = None


@dataclass
class Matchup:
    me: TeamLine
    opp: TeamLine
    my_players: list[dict] = field(default_factory=list)
    opp_players: list[dict] = field(default_factory=list)


def _num(s: str) -> float | None:
    s = s.strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _made_att(s: str) -> tuple[int, int] | None:
    m = re.match(r"(\d+)/(\d+)", s.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


# Yahoo glues status + team into the player cell: "Andrew NembhardQNew Player NoteIND - PG,SG"
_PLAYER = re.compile(
    r"^(?P<name>.+?)(?:Video Forecast)?(?P<status>GTD|INJ|O|Q|D|DTD|NA|SUSP|P)?(?:Video Forecast)?"
    r"(?:New )?Player Note"
    r"(?P<team>[A-Z]{2,4}) - (?P<pos>(?:PG|SG|SF|PF|G|F|C)(?:,(?:PG|SG|SF|PF|G|F|C))*)"
    r"(?P<rest>.*)$"
)


def parse_player_cell(text: str) -> dict:
    m = _PLAYER.match(text)
    if not m:
        return {"name": text, "status": None, "team": None, "pos": None, "game": None}
    rest = m.group("rest").strip() or None
    return {
        "name": m.group("name").strip(),
        "status": m.group("status"),
        "team": m.group("team"),
        "pos": m.group("pos"),
        "game": rest,  # e.g. "W, 102-99 @ MIN" or a start time
    }


def _pid(node) -> str | None:
    a = node.css_first("[data-ys-playerid]") if node is not None else None
    return a.attributes.get("data-ys-playerid") if a else None


def short_key(name: str) -> str:
    """'Anthony Black' / 'A. Black' -> 'a black' (first initial + rest), for matching Yahoo's
    abbreviated names (new matchup layout) against full names."""
    from fantasy_bot.nba.injuries import norm   # accents, punctuation, Jr/III suffixes
    s = norm(name).split()
    return f"{s[0][0]} {' '.join(s[1:])}" if len(s) > 1 else (s[0] if s else "")


class SlotLookup:
    """Find a player's matchup-page slot by Yahoo player id, then full name, then 'A. Black' form
    (the newer matchup layout only shows abbreviated names)."""

    def __init__(self, matchup_players: list[dict]):
        self.by_pid = {p["pid"]: p["slot"] for p in matchup_players if p.get("pid")}
        self.by_name = {p["name"]: p["slot"] for p in matchup_players}
        self.by_short = {short_key(p["name"]): p["slot"] for p in matchup_players}

    def get(self, p: dict) -> str | None:
        if p.get("pid") in self.by_pid:
            return self.by_pid[p["pid"]]
        return self.by_name.get(p["name"], self.by_short.get(short_key(p["name"])))


_STAT_COLS = ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
_ICONS = re.compile(r"[-]")  # Yahoo's icon-font characters (sort arrows etc.)


def _clean(s: str) -> str:
    return _ICONS.sub("", s).strip()


def parse_settings(html: str) -> dict[str, str]:
    """League settings page -> {'Max Acquisitions per Week': '4', 'Roster Positions': 'PG, SG, ...', ...}"""
    t = LexborHTMLParser(html)
    out = {}
    for tr in t.css("table tr"):
        c = [x.text(strip=True) for x in tr.css("th,td")]
        if len(c) == 2 and c[0]:
            out[c[0].rstrip(":").strip()] = c[1]
    return out


def parse_players(html: str) -> list[dict]:
    """Yahoo 'players' list page (FA list, or filtered to one team).

    Returns per player: name, status, team, pos, roster (FA / 'W (Nov 21)' / team name),
    gp, rank_now, and totals: fgm, fga, ftm, fta + counting stats.
    """
    t = LexborHTMLParser(html)
    tb = t.css_first("table")
    if tb is None:
        return []
    rows = tb.css("tr")
    if len(rows) < 3:
        return []
    head = [_clean(c.text(strip=True)) for c in rows[1].css("th,td")]
    idx = {h.split(":")[0]: i for i, h in enumerate(head)}
    out = []
    for tr in rows[2:]:
        nodes = tr.css("th,td")
        cells = [c.text(strip=True) for c in nodes]
        if len(cells) < len(head):
            continue
        p = parse_player_cell(cells[idx["Players"]])
        if not p.get("team"):
            continue
        p["pid"] = _pid(nodes[idx["Players"]])
        fg = _made_att(cells[idx["FGM/A*"]].replace(".0", "")) if "FGM/A*" in idx else None
        ft = _made_att(cells[idx["FTM/A*"]].replace(".0", "")) if "FTM/A*" in idx else None
        gp = _num(cells[idx["GP*"]]) if "GP*" in idx else None
        p.update({
            "opp_next": cells[idx["Opp"]] if "Opp" in idx else "",
            "roster": cells[idx["Roster Status"]] if "Roster Status" in idx else "",
            "gp": int(gp) if gp else 0,
            "rank_now": _num(cells[idx["Current"]]) if "Current" in idx else None,
            "rank_pre": _num(cells[idx["Pre-Season"]]) if "Pre-Season" in idx else None,
            "pct_ros": _num(cells[idx["% Ros"]].rstrip("%")) if "% Ros" in idx else None,
            "fgm": fg[0] if fg else 0, "fga": fg[1] if fg else 0,
            "ftm": ft[0] if ft else 0, "fta": ft[1] if ft else 0,
        })
        for c in _STAT_COLS:
            p[c] = _num(cells[idx[c]]) or 0.0
        out.append(p)
    return out


_TX_DATE = re.compile(r"([A-Z][a-z]{2} \d{1,2}), (\d{1,2}:\d{2} [ap]m)$")


def parse_transactions(html: str) -> list[dict]:
    """Transactions page filtered to adds. -> [{player, kind, team, when}]"""
    t = LexborHTMLParser(html)
    out = []
    tb = t.css_first("table")
    if tb is None:
        return out
    for tr in tb.css("tr"):
        cells = [c.text(strip=True) for c in tr.css("td")]
        if len(cells) < 3:
            continue
        who, mgr = cells[-2], cells[-1]
        m = _TX_DATE.search(mgr)
        if not m:
            continue
        kind = "Waiver" if who.endswith("Waiver") else "Free Agent" if "Free Age" in who else "?"
        out.append({
            "player": who, "kind": kind,
            "team": mgr[: m.start()].strip(),
            "date": m.group(1), "time": m.group(2),
        })
    return out


def find_team_id(html: str, league_id: str, team_name: str) -> str | None:
    t = LexborHTMLParser(html)
    pat = re.compile(rf"/nba/{league_id}/(\d+)/?$")
    for a in t.css("a"):
        href = (a.attributes.get("href") or "").split("?")[0]
        m = pat.search(href)
        if m and a.text(strip=True) == team_name:
            return m.group(1)
    return None


def current_week(html: str) -> int | None:
    """Matchup page links carry the week: '/matchup?week=6&date=...'."""
    m = re.search(r"matchup\?week=(\d+)&", html)
    return int(m.group(1)) if m else None


def parse_matchup(html: str) -> Matchup:
    t = LexborHTMLParser(html)
    totals = None
    for tb in t.css("table"):
        head = [c.text(strip=True) for c in tb.css("tr")[0].css("th,td")] if tb.css("tr") else []
        # Classic layout has FGM/A* columns; the newer (live/game-day) layout has Team ... Score only.
        if len(tb.css("tr")) >= 3 and ("FGM/A*" in head or (head[:2] == ["Team", "FG%"] and "Score" in head)):
            totals = tb
            break
    if totals is None:
        title = t.css_first("title")
        raise ValueError(f"matchup totals table not found (page: {title.text(strip=True) if title else '?'})")

    head = [c.text(strip=True) for c in totals.css("tr")[0].css("th,td")]
    lines = []
    for tr in totals.css("tr")[1:3]:
        cells = [c.text(strip=True) for c in tr.css("th,td")]
        row = dict(zip(head, cells))
        stats = {c: _num(row.get(c, "")) for c in CATS}
        won = _num(cells[-1]) if len(cells) > len(CATS) + 3 else None
        fgm_a, ftm_a = _made_att(row.get("FGM/A*", "")), _made_att(row.get("FTM/A*", ""))
        if fgm_a is None:
            fgm_a, ftm_a = estimate_shots(stats)
        if "Score" in row:
            won = _num(row["Score"])
        lines.append(TeamLine(
            name=row.get("Team") or cells[0], stats=stats, fgm_a=fgm_a, ftm_a=ftm_a,
            cats_won=int(won) if won is not None else None,
        ))

    mu = Matchup(me=lines[0], opp=lines[1])

    pt = t.css_first("#statTable3")
    if pt:
        for tr in pt.css("tr")[1:]:
            nodes = tr.css("th,td")
            cells = [c.text(strip=True) for c in nodes]
            if len(cells) < 23:
                continue
            # mine: slot 0, player 1, stats 2-10 | opponent: slot 13, player 14, stats 15-23
            for slot_i, dest in ((0, mu.my_players), (13, mu.opp_players)):
                slot, cell = cells[slot_i], slot_i + 1
                if not cells[cell]:
                    continue
                p = parse_player_cell(cells[cell])
                p["slot"], p["pid"] = slot, _pid(nodes[cell])
                p["stats"] = {c: _num(v) for c, v in zip(CATS, cells[cell + 1:cell + 10])}
                dest.append(p)
        return mu
    for tb in t.css("table"):   # newer layout: Player, 9 cats, Pos, Player, 9 cats
        rows = tb.css("tr")
        head = [c.text(strip=True) for c in rows[0].css("th,td")] if rows else []
        if head[:1] != ["Player"] or "Pos" not in head:
            continue
        for tr in rows[1:]:
            nodes = tr.css("td")
            if len(nodes) < 21:
                continue
            slot = nodes[10].text(strip=True)
            for i, dest in ((0, mu.my_players), (11, mu.opp_players)):
                p = parse_new_player_cell(nodes[i])
                if p:
                    p["slot"] = slot
                    p["stats"] = {c: _num(nodes[i + 1 + k].text(strip=True)) for k, c in enumerate(CATS)}
                    dest.append(p)
        break
    return mu


def parse_new_player_cell(td) -> dict | None:
    """Newer matchup layout: <a playernote>A. Black</a><span>ORL - PG,SG</span><abbr title=..>O</abbr>"""
    a = td.css_first("a.playernote")
    if a is None or not a.text(strip=True):
        return None
    tp = next((s.text(strip=True) for s in td.css("span") if re.match(r"^[A-Z]{2,4} - ", s.text(strip=True))), "")
    team, _, pos = tp.partition(" - ")
    ab = td.css_first("abbr")
    return {"name": a.text(strip=True), "short_name": True, "pid": a.attributes.get("data-ys-playerid"),
            "team": team or None, "pos": pos or None, "status": ab.text(strip=True) if ab else None, "game": None}


def estimate_shots(stats: dict) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """The newer layout shows FG%/FT% but not makes/attempts. Back them out of points:
    PTS - 3PTM = 2*FGM + FTM, with FGM = FG% x FGA and FTA ~ 0.27 x FGA (NBA-typical)."""
    fg, ft, pts, tpm = stats.get("FG%"), stats.get("FT%"), stats.get("PTS"), stats.get("3PTM")
    if not fg or pts is None or tpm is None:
        return None, None
    ft = ft or 0.78
    fga = (pts - tpm) / (2 * fg + 0.27 * ft)
    fta = 0.27 * fga
    return (round(fg * fga), round(fga)), (round(ft * fta), round(fta))
