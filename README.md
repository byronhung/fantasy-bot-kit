# Fantasy bot

A daily waiver advisor for **Yahoo Fantasy Basketball, head-to-head 9-category leagues**.

Every day it reads your matchups, projects the rest of the week (games left, injuries,
lineup slots), works out which categories you can still win or flip, and recommends the
add/drop moves that raise your chance of winning the week, balanced against long-term
value. It never makes moves for you: you get a push notification and decide.

- **3 PM Manila time (07:00 UTC):** daily report. One line per league on your phone, plus a dashboard.
- **7 AM Manila:** lineup check before tip-off (a starter ruled out, an idle starter with a bench player playing).
- **During games:** injury news for your players.

It runs on GitHub Actions, so your computer can be off.

## Set it up (about 15 minutes, with Claude Code)

1. Get the code: on GitHub click **Code → Download ZIP** and unzip it (or unzip the folder you were sent).
   Cloning works too; setup gives you your own private copy either way.
2. Open the folder in Claude Code.
3. Type **`/setup`**. Claude makes your private GitHub repo if needed, then walks you through every step.

**New here? Read [GUIDE.md](GUIDE.md)**: what the bot sends you and how to read it.

You'll need: a GitHub account with the `gh` CLI, Google Chrome, and the free **ntfy** app on your phone.

### Doing it by hand

```
uv sync
uv run playwright install chromium
uv run python -m fantasy_bot.setup login      # log into Yahoo in the Chrome window that opens
uv run python -m fantasy_bot.setup leagues    # finds your H2H leagues -> leagues.json
uv run python -m fantasy_bot.setup topic      # your private push topic; subscribe to it in ntfy
uv run python -m fantasy_bot.setup test       # full report on your PC, nothing sent
uv run python -m fantasy_bot.setup github     # stores login, topic, leagues as repo secrets/variables
uv run python -m fantasy_bot.setup push-test  # test push to your phone
```

Optional, recommended: **dashboard + on-time runs** (GitHub's own timer often runs hours late):

```
npx wrangler login                            # Windows PowerShell: npx.cmd wrangler login
uv run python -m fantasy_bot.setup cloudflare # then follow its last step (a GitHub token)
uv run python -m fantasy_bot.setup timer-on
```

## Every few weeks: Yahoo login expires

You'll get a push: "Yahoo login expired". Then:

```
uv run python -m fantasy_bot.setup login
uv run python -m fantasy_bot.setup github
```

## Tuning

- `fantasy_bot/config.py` -> `LONG_TERM_WEIGHT`: 0 = pure weekly streaming, 0.5 = balanced (default),
  1+ = protect your season. Per league: add `"long_term_weight": 1.0` to that league in `leagues.json`
  (and rerun the `github` step).
- Rerun the engine on the last saved snapshot, offline: `uv run python -m fantasy_bot.replay`
- How honest are its win percentages? `uv run python -m fantasy_bot.calibrate` (after a few weeks).

## Notes

- Reads Yahoo through your own logged-in session (Yahoo's API needs weeks of approval).
  Keep it to your own account; it's a light, twice-a-day footprint.
- Secrets live only in `.env`, `secrets/` (both git-ignored) and your repo's GitHub secrets.
