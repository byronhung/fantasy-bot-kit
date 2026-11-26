# Fantasy bot: notes for Claude

Yahoo Fantasy Basketball (H2H 9-cat) waiver advisor. Python 3.12 + uv. Runs on GitHub Actions;
optional Cloudflare Worker (cloudflare/) serves the dashboard and fires the workflows on time.

## First-time setup
If `uv run python -m fantasy_bot.setup status` shows unchecked items, follow `.claude/commands/setup.md`.

## Layout
- `fantasy_bot/yahoo/` read Yahoo pages through a saved login (Playwright), parse HTML
- `fantasy_bot/nba/` ESPN schedule + injuries
- `fantasy_bot/engine/` projection, category win odds, move search (`recommend.py`)
- `fantasy_bot/report/` push text, dashboard JSON, ntfy
- `fantasy_bot/run.py` entry: `--mode full|check|watch`, `--no-send`
- `fantasy_bot/setup.py` guided setup steps; `login.py` Yahoo login via real Chrome
- `site/index.html` dashboard; `cloudflare/` Worker (secret-link access, cron -> workflow_dispatch)
- Leagues come from `leagues.json` (local, git-ignored) or the repo variable `LEAGUES` (Actions).

## Rules
- Never commit `.env`, `secrets/`, `leagues.json`, `data/`. Never print secrets or the dashboard key.
- The bot only recommends moves. Don't automate adds/drops on Yahoo.
- Answering "why this move / what if X": rerun the engine (`uv run python -m fantasy_bot.replay`
  or `build_plan` on the latest `data/raw/` snapshot) and explain from its numbers, not from memory.
- Tests: `uv run pytest`.

## Common asks (GUIDE.md points users here)
- **"Re-login" / login expired:** `setup login`, then `setup github`.
- **Renew the timer token (GH_TOKEN):** the user makes a new fine-grained token (this repo only; Actions:
  Read and write, Contents: Read-only; 1 year) and pastes it themselves into
  `npx wrangler secret put GH_TOKEN --name <CF_WORKER_NAME from .env>` run in `cloudflare/` (Windows: `npx.cmd`).
- **Change long-term weight:** edit `long_term_weight` for that league in `leagues.json`, then `setup github`.
- **Different time zone:** schedules are UTC, written for Manila (UTC+8). Change all of them together:
  the `cron:` lines in the 3 workflows, `crons` in `cloudflare/wrangler.toml`, the matching keys in
  `BY_CRON` in `cloudflare/worker.js`, and the late-run gate hours in `check.yml`; then `setup cloudflare`
  to redeploy. Keep the check ~1 h before the first US tip-off and the watch window over US game nights.
- **A run failed:** `gh run list` / `gh run view <id> --log-failed`; failed runs keep Yahoo snapshots as an
  artifact for 7 days (`gh run download`), replay them with `fantasy_bot.replay`.
- **How accurate is it:** `uv run python -m fantasy_bot.calibrate` (needs a few finished weeks).
