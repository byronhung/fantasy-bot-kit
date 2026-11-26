# How the fantasy bot works

A plain-English tour. Read this once after setup.

## What it is

A waiver-wire assistant for **Yahoo Fantasy Basketball, head-to-head, 9 categories**
(PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TO).

Every day it looks at your matchup and asks one question: **which add/drop gives me the best
chance of winning this week, without wrecking my team for the rest of the season?**

It **never touches your team.** It only suggests. You make the moves in the Yahoo app yourself.

## What you'll get, and when (Manila time)

| When | What | Do you need to act? |
|---|---|---|
| **3 PM daily** | One notification per league: score, win chance, top move | Only if it suggests a move you like |
| **7 AM daily** | Lineup warning, *only if* a starter is out or a benched player should start | Fix your lineup in Yahoo |
| **8 AM-2 PM** (US game nights) | Injury news about *your* players | Usually just FYI |
| **Every few weeks** | "Yahoo login expired" | Open Claude Code in this folder, type `/setup` |

A quiet phone is good news. The 7 AM and injury alerts only fire when something matters.

## Reading the daily notification

```
HOOPERS 5-3 · 81% · ADD Green / DROP Watson
```

- **5-3**: categories you're winning vs losing right now.
- **81%**: the bot's estimate of your chance to win the week, after the move.
- **ADD / DROP**: the best move it found. No move means "Hold": nothing worth an add today.

Tap **Open report** for the full picture (if you set up the dashboard).

## Reading the dashboard

**Top of each league:** the score, your win chance (big number), and your opponent.

**Category bars.** One bar per category, like a tug-of-war. Your color pulls one way, the
opponent's the other; the percentage is your chance to win that category by Sunday.
- **Locked**: about 85%+ yours. Don't worry about it.
- **Lost**: about 15% or less. Don't chase it.
- **Swing**: everything in between. **This is where moves matter**, so the bot targets these.

**Move cards.** Each suggested move shows:
- who to add and who to drop
- win chance before → after
- which categories it flips toward you
- **Why**: tap for the reasoning: games left this week, the player's per-game stats, and the
  long-term cost (is the guy you're dropping better for the season?)

Below that: today's lineup, injuries on your roster (with dates), and any warnings.

## How it decides (short version)

1. **Projects the rest of the week.** For every player: games left, recent per-game stats,
   injury status, and whether he actually gets a lineup slot (benched games don't count).
2. **Simulates the matchup** to get a win chance for each category and for the week.
3. **Tries every sensible add/drop** from the free agents and keeps those that raise your win
   chance, weighed against long-term value so it won't tell you to drop a star for a one-week streamer.
4. **Context the stats miss:**
   - **Star teammates returning.** If a player's last 2 weeks came while a star teammate sat out, and
     that star is back or about to be (including "Out, but practiced fully" news), it projects the
     player closer to his season numbers instead.
   - **Your opponent's adds.** It estimates how many adds your opponent will still make (from how
     active they've been) and gives them that many decent streamers, so your win % isn't too rosy.
   Both show up under **Accounted for** on the dashboard, and in a move's **Why**.
5. **Dead weeks.** If you're below about 5% to win, it stops chasing this week and suggests adds
   that set you up for **next** week instead.

## Things it doesn't know (use your own head here)

- **Very recent slumps or minute changes.** It uses about two weeks of stats, so a three-game cold
  streak or a new bench role shows up slowly.
- **Exactly who your opponent adds.** It models a typical streamer, not their actual pick.
- **Teammate returns it can't see.** It only watches the top ~100 players, and goes by the injury
  news, which can lag.
- **Category-specific long-term value.** "Long-term value" is overall value. If you rely on one
  guy for blocks, check before dropping him.

Treat it like a sharp friend who's done the math, not an autopilot.

## Tuning

- **More streaming, or more protecting your season?** Ask Claude: *"set long_term_weight to 1 for my
  league"* (higher = protect the season, 0 = pure weekly streaming, default 0.5).
- **Times are Manila time.** In a different time zone? Ask Claude to shift the schedules.
- **How accurate is it?** After a few weeks, ask Claude to run `calibrate`. It checks the bot's
  win chances against what actually happened.

## When something goes wrong

- **"Yahoo login expired"** → `/setup` in Claude Code. It only redoes the login.
- **"... failed" notification** → open Claude Code here and say *"the bot failed, check the latest
  GitHub Actions run and fix it."*
- **No 3 PM notification** → same: ask Claude to check the latest run.
- **"timer stopped"** (only if you set up the dashboard) → the timer's GitHub token expired, about once a
  year. Ask Claude to *"renew the GH_TOKEN"*. It takes 2 minutes.

## Where things live

- **Your GitHub repo** runs the bot on GitHub's servers. Your PC can be off.
- **Secrets** (Yahoo login, notification topic, dashboard link) sit in `.env`, `secrets/` and your
  repo's GitHub secrets. Never commit them or share them.
- **Dashboard link** is private by secret link. Anyone with the link can see it, so don't post it.
