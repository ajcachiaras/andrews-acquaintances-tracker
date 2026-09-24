# Guillotine Watch — Andrew's Acquaintances

A weekly tracker for the 2026 season of **Andrew's Acquaintances**, a 19-team
guillotine league on Sleeper. Each week the lowest scorer is eliminated;
this page charts every team's points and how close each one sat to that
cutoff.

Open `index.html` in a browser, or enable GitHub Pages for this repo
(Settings → Pages → deploy from the `main` branch, root folder) to host it
at `https://ajcachiaras.github.io/andrews-acquaintances-tracker/`.

## Updating it each week

This runs itself. A Windows scheduled task, **Guillotine Watch weekly update**,
runs `update.ps1`, which pulls the finished week from Sleeper, rewrites
`data.js`, commits and pushes. Logs land in `logs/update-YYYY-MM-DD.log` (last
20 kept).

It fires **Tuesday at 9:00 AM Pacific**, the morning after Monday Night
Football, and again **Wednesday at 9:00 AM** as a backstop. The second run is a
no-op whenever the first one worked. It exists because the script won't record a
week until Sleeper's own week counter has rolled past it; if that rollover ever
lands after 9 AM Tuesday, Tuesday's run aborts without touching the data and
Wednesday's picks it up, instead of the site sitting stale for a week.

To run it by hand:

```powershell
powershell -ExecutionPolicy Bypass -File .\update.ps1
```

Add `-DryRun` to see what a pull would change without touching anything, or
`-NoPush` to commit locally only.

### How the pull works

`update_tracker.py` reads Sleeper's public API — no auth, no packages, standard
library only — and **rebuilds every week from scratch on each run** rather than
appending. That makes it idempotent: running it twice changes nothing the second
time, and a missed Tuesday heals itself on the next run.

Each week it takes the lowest score among teams still alive and records that
team as cut. It can't read elimination off Sleeper directly: Sleeper clears a
cut team's roster only after the fact, so a team eliminated Monday night still
looks rostered on Tuesday morning. Cleared rosters are used to *confirm* earlier
weeks, and any disagreement is logged as a warning.

`generated` in `data.js` is the date the data last **changed**, not the last
time it was checked — the logs are the record of runs. It's compared out before
deciding whether anything moved, because it holds today's date, so leaving it in
meant every run on a new day looked like a change and committed one.

Two guards keep a bad run from destroying good data:

- If the rebuild produces **fewer** weeks than `data.js` already holds — which
  is what a not-yet-rolled-over Sleeper week counter looks like — it aborts and
  leaves the file alone. Pass `--force` to override.
- A week is only accepted once Sleeper has moved past it, so an in-progress
  Sunday is never recorded as final.

Team names in `data.js` are preserved verbatim across rebuilds; they're
hand-curated and differ from Sleeper's own strings. `weeks`, `points`,
`eliminated` and `generated` are regenerated.

`lineups.js` is written alongside it, holding every team's starters and bench
per week. It needs player *names*, which come from Sleeper's full player
dictionary — about 14 MB, and their docs ask callers to pull it at most once a
day. So it's cached in `.cache/` (gitignored, 24h) and only fetched when there's
actually a new week to write. If that fetch fails the run still keeps the
scores, which are the point; the page falls back to "lineup detail isn't
available" and everything else works.

To edit a week by hand anyway, change `data.js` — the page recomputes each
week's cutoff, every team's margin above it, and the chart and board from it.

## What's shown

- **Points by week** — a line for every team, with the dashed red line
  tracing the elimination cutoff week to week. Each point is colored by how
  far that score sat above the cutoff that week, from crimson (right at it)
  to gold (comfortably clear). Hover a line or point for detail.
- **The board** — teams ranked low to high for whichever week you select,
  with each team's margin above that week's cutoff.
- **Lineups** — click any team, on the board or on the chart, for that week's
  starting lineup with each player's points, the bench behind it, and how many
  points were left there. The best and worst starter are tinted. Close with the
  ×, Escape, or a click outside.

Current through week 2.

| Week | Eliminated | Low score |
|---|---|---|
| 1 | Qadry Ismail's Womb | 60.21 |
| 2 | Max's team | 46.47 |

<!-- This section and data.js are rewritten by update_tracker.py; edit that script, not these lines. -->
