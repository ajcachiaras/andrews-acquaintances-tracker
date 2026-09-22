# Guillotine Watch — Andrew's Acquaintances

A weekly tracker for the 2026 season of **Andrew's Acquaintances**, a 19-team
guillotine league on Sleeper. Each week the lowest scorer is eliminated;
this page charts every team's points and how close each one sat to that
cutoff.

Open `index.html` in a browser, or enable GitHub Pages for this repo
(Settings → Pages → deploy from the `main` branch, root folder) to host it
at `https://ajcachiaras.github.io/andrews-acquaintances-tracker/`.

## Updating it each week

All the data lives in `data.js`. To add a new week:

1. Add the week number to the `weeks` array.
2. Push that week's score onto every team still alive. A team that's already
   been eliminated keeps getting `null` for later weeks — don't remove its
   entry, just leave it out of the running.

The page recomputes each week's elimination cutoff (the lowest live score),
every team's margin above it, and the chart and board below it automatically
— no other file needs to change.

## What's shown

- **Points by week** — a line for every team, with the dashed red line
  tracing the elimination cutoff week to week. Each point is colored by how
  far that score sat above the cutoff that week, from crimson (right at it)
  to gold (comfortably clear). Hover a line or point for detail.
- **The board** — teams ranked low to high for whichever week you select,
  with each team's margin above that week's cutoff.

Current through week 2. Team 10, Qadry Ismail's Womb, was the first team
eliminated, after posting the week 1 low score of 60.21.
