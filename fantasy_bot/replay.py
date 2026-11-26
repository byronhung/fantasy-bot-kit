"""Re-run the engine on a saved snapshot, no Yahoo login (for testing report/dashboard changes).

uv run python -m fantasy_bot.replay data/raw/2026-11-25_1012
"""
from __future__ import annotations

import sys
from pathlib import Path

from fantasy_bot.yahoo import reader


class _Offline:
    def __init__(self, folder: Path):
        self.folder = folder
        self.page = type("P", (), {"wait_for_timeout": staticmethod(lambda ms: None)})()

    def get(self, name: str, url: str) -> str:
        f = self.folder / f"{name}.html"
        return f.read_text(encoding="utf-8") if f.exists() else "<html></html>"


def read_snapshot(folder: Path) -> dict:
    s = _Offline(folder)
    return {lg["key"]: reader.read_league(s, lg) for lg in reader.LEAGUES}


if __name__ == "__main__":
    import fantasy_bot.run as run
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(
        p for p in (reader.ROOT / "data" / "raw").iterdir() if p.name[:2] == "20")[-1]
    print("replaying", folder)
    run.read_all = lambda: read_snapshot(folder)
    run.full_run(send=False)
