"""Open Yahoo with your saved login.

How the login travels:
- On the PC, `python -m fantasy_bot.login` saves the session cookies to secrets/storage_state.json.
- In GitHub Actions, the same JSON lives in the YAHOO_STATE secret; we write it to that path first.
Playwright loads the file, so Yahoo sees an already-logged-in browser.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "secrets" / "storage_state.json"
FANTASY_HOME = "https://basketball.fantasysports.yahoo.com/nba"

# A normal desktop Chrome UA; headless Chromium's default UA says "HeadlessChrome".
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class LoginRequired(RuntimeError):
    """Yahoo sent us to the login page: the saved cookies expired."""


def ensure_state_file() -> Path:
    env_state = os.environ.get("YAHOO_STATE")
    if env_state and not STATE_PATH.exists():
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(env_state, encoding="utf-8")
    if not STATE_PATH.exists():
        raise LoginRequired("No saved Yahoo login. Run: python -m fantasy_bot.login")
    return STATE_PATH


@contextmanager
def yahoo_context(headless: bool = True):
    state = ensure_state_file()
    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(headless=headless)
        context: BrowserContext = browser.new_context(
            storage_state=str(state),
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        try:
            yield context
            # Yahoo refreshes cookies as we browse; keep the freshest copy locally.
            context.storage_state(path=str(state))
        finally:
            browser.close()


def is_login_page(url: str) -> bool:
    return "login.yahoo.com" in url
