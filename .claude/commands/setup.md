---
description: Set up the fantasy bot for your Yahoo leagues (guided, ~15 min)
---
Set up this fantasy bot for me, step by step. Explain each step in one or two plain sentences
before running it, run the commands yourself, and stop to let me act whenever a step needs me
(a login, the phone, a GitHub or Cloudflare page). Never print or repeat secrets, tokens, the
ntfy topic beyond the one time I need it, or the dashboard link.

Do the steps in order, and skip any that `uv run python -m fantasy_bot.setup status` shows as done:

1. **Tools.** Check `uv`, `gh` (logged in: `gh auth status`), and Google Chrome are installed; if not,
   tell me exactly how to install them for my OS. Check this folder is MY OWN private GitHub repo
   (`gh repo view`). If it isn't a git repo at all (e.g. it came from a zip), make it one:
   `git init -b master`, `git add -A`, `git commit -m "Initial copy"`,
   `gh repo create fantasy-bot --private --source . --push`. If it's someone else's repo (I cloned the
   public kit), detach it with `git remote remove origin`, then create my own private repo the same way.
   Then run `uv sync` and `uv run playwright install chromium`.
2. **Yahoo login.** Run `uv run python -m fantasy_bot.setup login`. A Chrome window opens: tell me to log
   into Yahoo there and wait. It finishes by itself.
3. **Leagues.** Run `uv run python -m fantasy_bot.setup leagues`. Show me the leagues it found and ask
   which to keep; if not all, rerun with `--only <ids>`.
4. **Phone pushes.** Run `uv run python -m fantasy_bot.setup topic`. Tell me to install the free ntfy app
   and subscribe to that exact topic name. When I say done, run `... setup push-test` and confirm I got it.
5. **Test run.** Run `uv run python -m fantasy_bot.setup test` and summarize the report in a few lines
   (my win chance per league and the top move) so I can sanity-check it against Yahoo.
6. **Cloud.** Run `uv run python -m fantasy_bot.setup github`. If GitHub says Actions aren't enabled yet,
   tell me to open the repo's Actions tab and enable workflows, then rerun. Watch the first run with
   `gh run watch` and tell me if it passed.
7. **Optional, recommended: dashboard + on-time runs.** Explain: GitHub's built-in timer can run hours
   late, so a free Cloudflare Worker starts the jobs on time and also hosts a private dashboard. If I
   want it: check Node.js is installed (`node -v`; it provides `npx`), I make a free Cloudflare account, then run `! npx wrangler login` here (Windows PowerShell:
   `! npx.cmd wrangler login`). Then run `... setup cloudflare` and walk me through its GitHub-token
   step (I create the token and paste it myself, in my own terminal). Then run `... setup timer-on`.
8. Finish with a short summary: what runs when, where pushes arrive, and that every few weeks Yahoo
   logs me out, and then I just run `/setup` again (it only redoes the login and the github step).
   Then point me to GUIDE.md, which explains how to read the notifications and dashboard.
