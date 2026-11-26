"""Guided setup, one step at a time (Claude Code's /setup runs these in order).

  uv run python -m fantasy_bot.setup status        what's done, what's next
  uv run python -m fantasy_bot.setup login         Yahoo login in your Chrome (same as fantasy_bot.login)
  uv run python -m fantasy_bot.setup leagues       find your Yahoo H2H leagues -> leagues.json
        [--only 123456,654321]                     keep just these league ids
  uv run python -m fantasy_bot.setup topic         make your private ntfy push topic (.env)
  uv run python -m fantasy_bot.setup test          full report on your PC, nothing sent
  uv run python -m fantasy_bot.setup github        store login/topic/leagues in your GitHub repo
  uv run python -m fantasy_bot.setup push-test     send a test push to your phone
  uv run python -m fantasy_bot.setup cloudflare    optional: dashboard + on-time timer (after `npx wrangler login`)
  uv run python -m fantasy_bot.setup timer-on      after you add the GitHub token: verify, then use the on-time timer
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import secrets
import shutil
import string
import subprocess
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from fantasy_bot.config import BASE, LEAGUES_FILE, ROOT
from fantasy_bot.yahoo.browser import FANTASY_HOME, STATE_PATH

ENV_FILE = ROOT / ".env"
CF_DIR = ROOT / "cloudflare"
VIEW_KEY_FILE = ROOT / "secrets" / "view_key.txt"
TEAM_LINK = re.compile(r"/nba/(\d+)/(\d+)/?$")

sys.stdout.reconfigure(encoding="utf-8")


def say(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def need(tool: str) -> str:
    path = shutil.which(tool + (".cmd" if platform.system() == "Windows" and tool == "npx" else "")) or shutil.which(tool)
    if not path:
        raise SystemExit(f"'{tool}' isn't installed or isn't on PATH. Install it, then rerun this step.")
    return path


def slug(s: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return out or "league"


def rand(n: int) -> str:
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def env_get(key: str) -> str | None:
    load_dotenv(ENV_FILE)
    return os.environ.get(key)


def env_set(key: str, value: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [l for l in lines if not l.startswith(key + "=")] + [f"{key}={value}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def repo_name() -> str:
    r = run([need("gh"), "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=ROOT)
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit("Couldn't find this folder's GitHub repo. Run `gh auth login`, and make sure this "
                         "folder is your own private GitHub repo of the bot (/setup step 1 creates it).\n" + r.stderr)
    return r.stdout.strip()


def league_problem(settings: dict[str, str]) -> str | None:
    """Why the bot can't handle this league, or None. It supports H2H categories with the
    standard 9 Yahoo categories (FG% FT% 3PTM PTS REB AST ST BLK TO)."""
    from fantasy_bot.config import CATS
    if "Head-to-Head - Categories" not in settings.get("Scoring Type", ""):
        return "not head-to-head categories"
    listed = settings.get("Players Stat Categories")
    if listed:
        cats = set(re.findall(r"\(([^)]+)\)", listed))
        if cats != set(CATS):
            extra, missing = sorted(cats - set(CATS)), sorted(set(CATS) - cats)
            return "non-standard categories" + (f" (extra: {', '.join(extra)})" if extra else "")                 + (f" (missing: {', '.join(missing)})" if missing else "")
    return None


# ---------- steps ----------

def step_leagues(only: str | None) -> None:
    from fantasy_bot.yahoo.parse import parse_settings
    from fantasy_bot.yahoo.reader import Session
    keep = {x.strip() for x in only.split(",")} if only else None
    say("Opening Yahoo Fantasy with your saved login to find your leagues...")
    with Session(ROOT / "data" / "raw" / "setup") as s:
        s.get("home", FANTASY_HOME)
        teams: dict[str, tuple[str, str]] = {}
        for a in s.page.locator("a[href*='/nba/']").all():
            href = (a.get_attribute("href") or "").split("?")[0]
            m = TEAM_LINK.search(href)
            text = (a.inner_text() or "").strip()
            if m and text and m.group(1) not in teams:
                teams[m.group(1)] = (m.group(2), text)
        if not teams:
            raise SystemExit("No basketball teams found on your Yahoo account for this season.")
        found = []
        for lid, (tid, team) in teams.items():
            st = parse_settings(s.get(f"settings-{lid}", f"{BASE}/{lid}/settings"))
            found.append({"league_id": lid, "team_id": tid, "team": team, "problem": league_problem(st),
                          "league": st.get("League Name", "?"), "scoring": st.get("Scoring Type", "?")})
    say("\nYour Yahoo basketball leagues:")
    for f in found:
        say(f"  {f['league_id']:>8}  team '{f['team']}' in '{f['league']}'  [{f['scoring']}]"
            + (f"  <- {f['problem']}, skipped" if f["problem"] else ""))
    chosen = [f for f in found if not f["problem"] and (keep is None or f["league_id"] in keep)]
    if not chosen:
        raise SystemExit("No supported leagues selected. The bot only handles head-to-head leagues with the "
                         "standard 9 categories (FG% FT% 3PTM PTS REB AST ST BLK TO).")
    used, leagues = set(), []
    for f in chosen:
        key = slug(f["team"])
        while key in used:
            key += "_" + f["league_id"][-3:]
        used.add(key)
        leagues.append({"key": key, "name": f["team"], "league_id": f["league_id"], "team_id": f["team_id"]})
    LEAGUES_FILE.write_text(json.dumps(leagues, indent=1), encoding="utf-8")
    say(f"\nSaved {len(leagues)} league(s) to leagues.json: " + ", ".join(l["name"] for l in leagues))
    say("To keep only some, rerun with --only <league ids, comma-separated>.")


def step_topic() -> None:
    if env_get("NTFY_TOPIC"):
        say(f"Push topic already set: {os.environ['NTFY_TOPIC']}")
    else:
        env_set("NTFY_TOPIC", "fbot-" + rand(24))
        say(f"Made your private push topic: {os.environ['NTFY_TOPIC']}")
    say("On your phone: install the ntfy app, tap +, and subscribe to exactly that topic name. "
        "Anyone with the name can read your pushes, so don't share it.")


def step_push_test() -> None:
    from fantasy_bot.report.notify import push
    if not env_get("NTFY_TOPIC"):
        raise SystemExit("No push topic yet. Run the 'topic' step first.")
    push("Setup test: if you can read this, pushes work.", title="Fantasy bot: test")
    say("Sent a test push. Check your phone's ntfy app.")


def step_test() -> None:
    if not LEAGUES_FILE.exists():
        raise SystemExit("No leagues.json yet. Run the 'leagues' step first.")
    say("Running a full report on this PC (nothing is sent). Takes 2-4 minutes...")
    r = subprocess.run([sys.executable, "-m", "fantasy_bot.run", "--mode", "full", "--no-send"], cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit("The test run failed: see the error above.")


def step_github() -> None:
    gh = need("gh")
    repo = repo_name()
    if not STATE_PATH.exists():
        raise SystemExit("No Yahoo login saved yet. Run the 'login' step first.")
    if not LEAGUES_FILE.exists():
        raise SystemExit("No leagues.json yet. Run the 'leagues' step first.")
    if not env_get("NTFY_TOPIC"):
        raise SystemExit("No push topic yet. Run the 'topic' step first.")
    state = STATE_PATH.read_text(encoding="utf-8")
    if len(state) > 45_000:
        raise SystemExit("Saved login is too big for a GitHub secret. Rerun the 'login' step (it keeps only Yahoo cookies).")
    leagues = json.dumps(json.loads(LEAGUES_FILE.read_text(encoding="utf-8")))
    for name, value in (("YAHOO_STATE", state), ("NTFY_TOPIC", os.environ["NTFY_TOPIC"])):
        r = run([gh, "secret", "set", name, "-R", repo], input=value)
        if r.returncode:
            raise SystemExit(f"Couldn't set {name}: {r.stderr}")
    r = run([gh, "variable", "set", "LEAGUES", "-R", repo, "--body", leagues])
    if r.returncode:
        raise SystemExit(f"Couldn't set LEAGUES: {r.stderr}")
    say(f"Stored your Yahoo login, push topic and leagues in {repo}.")
    say("Starting a first cloud run (no push)...")
    r = run([gh, "workflow", "run", "daily.yml", "-R", repo, "-f", "send=false"])
    say("Started. Watch it with: gh run watch" if r.returncode == 0 else
        "Couldn't start it yet (Actions may still be warming up on a new repo). In GitHub open the "
        "Actions tab, enable workflows if asked, then run 'daily report' by hand.\n" + r.stderr)


def _wrangler_token() -> str:
    home = Path.home()
    for p in (Path(os.environ.get("APPDATA", "")) / "xdg.config/.wrangler/config/default.toml",
              home / "Library/Preferences/.wrangler/config/default.toml",
              home / ".config/.wrangler/config/default.toml",
              home / ".wrangler/config/default.toml"):
        if p.exists():
            m = re.search(r'oauth_token\s*=\s*"([^"]+)"', p.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
    raise SystemExit("Not logged into Cloudflare. Run `npx wrangler login` (Windows: `npx.cmd wrangler login`) first.")


def _cf(method: str, path: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"https://api.cloudflare.com/client/v4{path}", method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                          "User-Agent": "fantasy-bot-setup"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def step_cloudflare() -> None:
    npx, gh = need("npx"), need("gh")
    repo = repo_name()
    token = _wrangler_token()
    accounts = _cf("GET", "/accounts", token).get("result") or []
    if not accounts:
        raise SystemExit("Couldn't read your Cloudflare account. Rerun `npx wrangler login`.")
    acct = accounts[0]["id"]
    env = {**os.environ, "CLOUDFLARE_ACCOUNT_ID": acct}

    sub = (_cf("GET", f"/accounts/{acct}/workers/subdomain", token).get("result") or {}).get("subdomain")
    if not sub:
        sub = "fbot-" + rand(6)
        res = _cf("PUT", f"/accounts/{acct}/workers/subdomain", token, {"subdomain": sub})
        if not res.get("success"):
            raise SystemExit(f"Couldn't register a workers.dev subdomain: {res.get('errors')}")
    if not env_get("CF_WORKER_NAME"):
        name = "fbot-board-" + rand(4)
        env_set("CF_WORKER_NAME", name)
    name = os.environ["CF_WORKER_NAME"]
    # The timer starts the workflows on the repo's main branch, whatever it's called (master/main).
    b = run([gh, "repo", "view", repo, "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"])
    branch = b.stdout.strip() if b.returncode == 0 and b.stdout.strip() else "master"
    say(f"Timer will run the bot from branch '{branch}'.")
    # Your worker name / repo / branch go in at deploy time, so wrangler.toml stays generic.
    you = ["--config", "wrangler.toml", "--name", name]

    say(f"Deploying the dashboard + timer as Worker '{name}'...")
    r = run([npx, "--yes", "wrangler@4", "deploy", *you, "--var", f"REPO:{repo}", "--var", f"BRANCH:{branch}"], cwd=CF_DIR, env=env)
    if r.returncode:
        raise SystemExit("Deploy failed:\n" + r.stdout[-2000:] + r.stderr[-2000:])

    if not VIEW_KEY_FILE.exists():
        VIEW_KEY_FILE.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    key = VIEW_KEY_FILE.read_text(encoding="utf-8").strip()
    r = run([npx, "--yes", "wrangler@4", "secret", "put", "VIEW_KEY", *you],
            cwd=CF_DIR, env=env, input=key)
    if r.returncode:
        raise SystemExit("Couldn't store the dashboard key:\n" + r.stderr[-1500:])
    url = f"https://{name}.{sub}.workers.dev/?k={key}"
    env_set("CF_DASH_URL", url)
    r = run([gh, "secret", "set", "REPORT_URL", "-R", repo], input=url)
    if r.returncode:
        raise SystemExit("Couldn't store REPORT_URL in GitHub: " + r.stderr)
    say("Dashboard deployed and locked behind a secret link (it's in your pushes' 'Open report' button).")
    say("\nLAST STEP (yours, about 2 minutes): give the timer a GitHub token.")
    say("  1. github.com -> Settings -> Developer settings -> Fine-grained tokens -> Generate new token")
    say(f"     Repository access: Only select repositories -> {repo}")
    say("     Permissions: Actions = Read and write, Contents = Read-only.")
    say("     Expiration: the longest it offers (1 year). If it expires the bot still sends the 3 PM report,")
    say("     but late, and the lineup/injury alerts stop; the 3 PM push will warn you.")
    say("  2. Copy the token, then in a terminal (Windows: Command Prompt or PowerShell):")
    say(f"       cd {CF_DIR}")
    say(f"       npx wrangler secret put GH_TOKEN --name {name}        (Windows PowerShell: npx.cmd ...)")
    say("     and paste the token when asked.")
    say("  3. Back here: uv run python -m fantasy_bot.setup timer-on")
    say("     (checks the token works, then switches GitHub's own late timers off)")


def step_timer_on() -> None:
    gh = need("gh")
    repo = repo_name()
    url = env_get("CF_DASH_URL")
    if not url:
        raise SystemExit("Run the 'cloudflare' step first.")
    base, key = url.split("/?k=")
    req = urllib.request.Request(f"{base}/report.json",  # Cloudflare 403s the default Python UA
                                 headers={"Cookie": f"fb={key}", "User-Agent": "fantasy-bot-setup"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ok = r.status == 200 and json.load(r).get("leagues") is not None
    except Exception:
        ok = False
    if not ok:
        raise SystemExit("The dashboard can't read your report yet. Either GH_TOKEN isn't set (or lacks "
                         "Contents: Read-only), or no daily report has run since setup: run 'daily report' "
                         "once in the Actions tab, wait for it to finish, then retry this step.")
    r = run([gh, "variable", "set", "CF_TIMER", "-R", repo, "--body", "on"])
    if r.returncode:
        raise SystemExit("Couldn't set CF_TIMER: " + r.stderr)
    say("Token works. The Cloudflare timer now runs everything on time; GitHub's late timers are off.")
    say("Your dashboard: tap 'Open report' on any push (keep that link private).")


def step_status() -> None:
    checks = [
        ("Yahoo login saved", STATE_PATH.exists(), "login"),
        ("Leagues chosen (leagues.json)", LEAGUES_FILE.exists(), "leagues"),
        ("Push topic (.env)", bool(env_get("NTFY_TOPIC")), "topic"),
    ]
    gh = shutil.which("gh")
    if gh:
        r = run([gh, "secret", "list", "--json", "name", "-q", ".[].name"], cwd=ROOT)
        names = set(r.stdout.split()) if r.returncode == 0 else set()
        checks.append(("GitHub secrets set", {"YAHOO_STATE", "NTFY_TOPIC"} <= names, "github"))
        checks.append(("Dashboard (optional)", "REPORT_URL" in names, "cloudflare"))
    else:
        checks.append(("GitHub CLI installed (gh)", False, "install gh, then `gh auth login`"))
    for label, ok, step in checks:
        say(f"  [{'x' if ok else ' '}] {label}" + ("" if ok else f"   -> next: {step}"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["status", "login", "leagues", "topic", "test", "github", "push-test",
                                     "cloudflare", "timer-on"])
    ap.add_argument("--only", help="leagues step: comma-separated league ids to keep")
    a = ap.parse_args()
    if a.step == "login":
        from fantasy_bot.login import main as login
        login()
    elif a.step == "leagues":
        step_leagues(a.only)
    else:
        {"status": step_status, "topic": step_topic, "test": step_test, "github": step_github,
         "push-test": step_push_test, "cloudflare": step_cloudflare, "timer-on": step_timer_on}[a.step]()


if __name__ == "__main__":
    main()
