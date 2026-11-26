"""Yahoo login: once at setup, then again whenever Yahoo expires the session (every few weeks).

    uv run python -m fantasy_bot.login

Google/Yahoo sign-in blocks browsers driven by automation ("This browser may not be
secure"). So we start your *real* Chrome as a normal process, with its own throwaway
profile and a local debugging port, and nothing attached while you log in. Once a tab
reaches the fantasy site, we read the cookies over Chrome's debugging port (plain
websocket, no Playwright attach: that can hang on Chrome's sign-in pages) and save the
Yahoo ones to secrets/storage_state.json.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

from fantasy_bot.yahoo.browser import FANTASY_HOME, ROOT, STATE_PATH, is_login_page

PORT = 9333
PROFILE = ROOT / "secrets" / "chrome-login-profile"
TIMEOUT_S = 600


def find_chrome() -> str:
    candidates: list[str | Path] = []
    system = platform.system()
    if system == "Windows":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"),
                     os.environ.get("LOCALAPPDATA")):
            if base:
                candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    elif system == "Darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        candidates.append(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for c in candidates:
        if Path(c).exists():
            return str(c)
    raise SystemExit("Google Chrome not found. Install Chrome, or set CHROME_PATH to its executable.")


def _get(path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as r:
        return json.load(r)


def _cdp(ws_url: str, method: str, params: dict | None = None) -> dict:
    ws = websocket.create_connection(ws_url, timeout=15, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["result"]
    finally:
        ws.close()


def to_storage_state(cdp_cookies: list[dict]) -> dict:
    """Chrome DevTools cookies -> Playwright storage_state, Yahoo domains only.
    (Only Yahoo's cookies are needed, and the full set is too big for a GitHub secret.)"""
    cookies = []
    for c in cdp_cookies:
        if "yahoo" not in c.get("domain", ""):
            continue
        same_site = c.get("sameSite") if c.get("sameSite") in ("Strict", "Lax", "None") else "Lax"
        cookies.append({
            "name": c["name"], "value": c["value"], "domain": c["domain"], "path": c.get("path", "/"),
            "expires": -1 if c.get("session") else c.get("expires", -1),
            "httpOnly": bool(c.get("httpOnly")), "secure": bool(c.get("secure")), "sameSite": same_site,
        })
    return {"cookies": cookies, "origins": []}


def _landed() -> bool:
    try:
        pages = _get("/json/list")
    except OSError:
        return False
    return any("fantasysports.yahoo.com" in p.get("url", "") and not is_login_page(p.get("url", ""))
               for p in pages if p.get("type") == "page")


def main() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    chrome = subprocess.Popen([
        os.environ.get("CHROME_PATH") or find_chrome(),
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://login.yahoo.com/?done=" + FANTASY_HOME,
    ])
    print("A Chrome window opened. Log into Yahoo there (any 2-step check included).")
    print("Waiting up to 10 minutes; this finishes by itself once you reach Yahoo Fantasy.")
    try:
        deadline = time.time() + TIMEOUT_S
        while time.time() < deadline:
            if _landed():
                time.sleep(4)  # let the landing page finish setting cookies
                cookies = _cdp(_get("/json/version")["webSocketDebuggerUrl"], "Storage.getCookies")["cookies"]
                state = to_storage_state(cookies)
                if not any(c["domain"].endswith("yahoo.com") for c in state["cookies"]):
                    raise SystemExit("Reached Yahoo Fantasy but found no Yahoo cookies. Try again.")
                STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
                print(f"Saved your Yahoo login ({len(state['cookies'])} cookies) to {STATE_PATH}")
                return
            time.sleep(1.5)
        raise SystemExit("Timed out waiting for the Yahoo login.")
    finally:
        chrome.terminate()


if __name__ == "__main__":
    main()
