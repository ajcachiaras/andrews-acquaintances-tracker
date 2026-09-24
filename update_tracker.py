#!/usr/bin/env python3
"""Rebuild data.js (and the "current through" lines) from Sleeper.

Run with no arguments to refresh the tracker:

    python update_tracker.py

The script is idempotent and rebuilds every week from scratch on each run, so a
missed Tuesday heals itself on the next one. Standard library only -- Sleeper's
read API needs no auth and no packages.

Flags:
    --dry-run   print what would change, write nothing
    --force     write even if the rebuild would drop weeks (see the abort below)
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

LEAGUE_ID = "1357848429371338752"
API = "https://api.sleeper.app/v1"
MAX_WEEK = 18

ROOT = Path(__file__).resolve().parent
DATA_JS = ROOT / "data.js"
LINEUPS_JS = ROOT / "lineups.js"
README = ROOT / "README.md"
CACHE = ROOT / ".cache"
PLAYER_CACHE_HOURS = 24


def log(msg):
    print(msg, flush=True)


def get(path, attempts=4):
    """GET a Sleeper endpoint, retrying on transient failures."""
    url = API + path
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "guillotine-watch/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if i == attempts - 1:
                raise SystemExit("FAILED: %s after %d attempts: %s" % (url, attempts, e))
            wait = 2 ** i
            log("  retry %d/%d on %s in %ds (%s)" % (i + 1, attempts - 1, path, wait, e))
            time.sleep(wait)


def roster_is_empty(row):
    """True when Sleeper has cleared a roster, which it does after a cut.

    Two shapes show up in practice: starters as a list of '0' placeholders the
    week after the cut, and starters as null in later weeks. Sleeper applies
    this lazily -- a team cut on Monday night can still look rostered on
    Tuesday -- so it is only ever used to confirm past weeks, never to decide
    the current one.
    """
    starters = row.get("starters")
    if not starters:
        return True
    return all(s in (None, "0", 0) for s in starters)


def score_of(row):
    """Commissioner overrides live in custom_points and win when set."""
    custom = row.get("custom_points")
    return float(custom if custom is not None else row.get("points") or 0.0)


def player_index():
    """Sleeper's whole player dictionary: ~14 MB, and their docs ask callers to
    pull it at most once a day, so it is cached on disk and only ever fetched
    when there is a new week to write lineups for."""
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / "players.json"
    if cached.exists():
        age_h = (time.time() - cached.stat().st_mtime) / 3600
        if age_h < PLAYER_CACHE_HOURS:
            log("  player index: cache hit (%.1fh old)" % age_h)
            return json.loads(cached.read_text(encoding="utf-8"))

    log("  player index: fetching from Sleeper (~14 MB)")
    data = get("/players/nfl")
    slim = {}
    for pid, p in data.items():
        if not isinstance(p, dict):
            continue
        name = p.get("full_name")
        if not name:
            name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        slim[pid] = [name or pid, p.get("position") or "", p.get("team") or "FA"]
    cached.write_text(json.dumps(slim), encoding="utf-8")
    log("  player index: cached %d players" % len(slim))
    return slim


def starter_slots():
    """Lineup slot labels in starter order, e.g. QB, RB, RB, WR, WR, FLEX x3."""
    league = get("/league/%s" % LEAGUE_ID)
    return [p for p in (league.get("roster_positions") or []) if p not in ("BN", "IR", "TAXI")]


def build_lineups(rows_by_week, points, team_ids, players, slots):
    """Per team, per week: who started, what they scored, and what sat on the
    bench. Keyed week -> team -> {t: total, s: [[slot, name, nflteam, pts]],
    b: [[pos, name, nflteam, pts]]}."""
    out = {}
    for w, rows in rows_by_week.items():
        week_entry = {}
        for tid in team_ids:
            wi = w - 1
            if points[tid][wi] is None:
                continue  # already cut; no lineup to show
            row = rows.get(tid)
            if not row:
                continue
            starters = row.get("starters") or []
            spts = row.get("starters_points") or []
            ppts = row.get("players_points") or {}

            s = []
            for i, pid in enumerate(starters):
                slot = slots[i] if i < len(slots) else "FLEX"
                pts = round(float(spts[i]), 2) if i < len(spts) and spts[i] is not None else 0.0
                if pid in (None, "0", 0):
                    s.append([slot, "(empty)", "", 0.0])
                    continue
                name, pos, nfl = players.get(str(pid), [str(pid), "", ""])
                s.append([slot, name, nfl, pts])

            started = {str(p) for p in starters}
            b = []
            for pid in (row.get("players") or []):
                if str(pid) in started:
                    continue
                name, pos, nfl = players.get(str(pid), [str(pid), "", ""])
                pts = ppts.get(str(pid))
                b.append([pos or "", name, nfl, round(float(pts), 2) if pts is not None else 0.0])
            b.sort(key=lambda r: -r[3])

            week_entry[tid] = {"t": points[tid][wi], "s": s, "b": b}
        out[w] = week_entry
    return out


def render_lineups_js(lineups):
    head = [
        "// Per-week lineups for Andrew's Acquaintances -- generated by",
        "// update_tracker.py from Sleeper. Do not edit by hand.",
        "//",
        "// week -> team id -> { t: total, s: starters, b: bench }",
        "//   starter: [slot, player, nfl team, points]",
        "//   bench:   [position, player, nfl team, points]",
        "",
        "const LEAGUE_LINEUPS = {",
    ]
    weeks = sorted(lineups)
    for wn, w in enumerate(weeks):
        head.append('  "%d": {' % w)
        tids = sorted(lineups[w], key=int)
        for tn, tid in enumerate(tids):
            e = lineups[w][tid]
            head.append('    "%s": {"t": %.2f,' % (tid, e["t"]))
            head.append('      "s": %s,' % json.dumps(e["s"], ensure_ascii=False))
            head.append('      "b": %s}%s' % (json.dumps(e["b"], ensure_ascii=False),
                                              "" if tn == len(tids) - 1 else ","))
        head.append("  }%s" % ("" if wn == len(weeks) - 1 else ","))
    head.append("};")
    return "\n".join(head) + "\n"


def parse_data_js(text):
    """Pull the pieces of data.js worth preserving across a rebuild.

    Team names are kept exactly as they sit in the file: they are hand-curated
    (straight apostrophes, casing) and differ from Sleeper's own strings.
    """
    header = text.split("const LEAGUE_DATA")[0]

    m = re.search(r"teams:\s*\{(.*?)\n  \}", text, re.S)
    if not m:
        raise SystemExit("could not find the teams block in data.js")
    teams_body = m.group(1)
    team_ids = re.findall(r'"(\d+)":', teams_body)

    m = re.search(r"weeks:\s*\[([^\]]*)\]", text)
    existing_weeks = [int(w) for w in re.findall(r"\d+", m.group(1))] if m else []

    names = dict(re.findall(r'"(\d+)":\s*"((?:[^"\\]|\\.)*)"', teams_body))
    return header, teams_body, team_ids, existing_weeks, names


def build(team_ids, names):
    """Walk the season week by week, applying the guillotine as we go."""
    state = get("/state/nfl")
    current_week = int(state["week"])
    log("Sleeper reports week %d (display_week %s); weeks 1-%d are candidates."
        % (current_week, state.get("display_week"), current_week - 1))

    alive = set(team_ids)
    weeks, eliminations, warnings = [], [], []
    points = {tid: [] for tid in team_ids}
    rows_by_week = {}

    for w in range(1, MAX_WEEK + 1):
        if w >= current_week:
            log("week %d: current or upcoming week, stopping." % w)
            break

        rows = {str(r["roster_id"]): r for r in get("/league/%s/matchups/%d" % (LEAGUE_ID, w))}
        missing = alive - rows.keys()
        if missing:
            warnings.append("week %d: no matchup row for roster(s) %s" % (w, sorted(missing)))
            break

        live = {tid: score_of(rows[tid]) for tid in alive}
        if max(live.values()) <= 0:
            log("week %d: no team has scored, stopping." % w)
            break

        for tid in team_ids:
            if tid not in alive and not roster_is_empty(rows[tid]):
                warnings.append("week %d: %s was cut earlier but still has a roster"
                                % (w, names.get(tid, tid)))
            elif tid in alive and roster_is_empty(rows[tid]):
                warnings.append("week %d: %s is listed alive but has an empty roster"
                                % (w, names.get(tid, tid)))

        weeks.append(w)
        rows_by_week[w] = rows
        for tid in team_ids:
            points[tid].append(round(live[tid], 2) if tid in alive else None)

        low = min(live.values())
        cut = sorted(tid for tid, s in live.items() if s == low)
        if len(cut) > 1:
            warnings.append(
                "week %d: TIE at %.2f between %s -- took roster %s; check the league tiebreaker"
                % (w, low, ", ".join(names.get(t, t) for t in cut), cut[0]))
        victim = cut[0]
        alive.discard(victim)
        eliminations.append((w, victim, low))
        log("week %d: low %.2f -- %s eliminated (%d left)"
            % (w, low, names.get(victim, victim), len(alive)))

    return weeks, points, eliminations, warnings, rows_by_week


def render_data_js(header, teams_body, team_ids, weeks, points, eliminations):
    lines = [header.rstrip("\n"), "", "const LEAGUE_DATA = {"]
    lines.append('  generated: "%s",' % date.today().isoformat())
    lines.append("  weeks: [%s]," % ", ".join(str(w) for w in weeks))
    # Team id -> the week its season ended. Stated rather than inferred: the
    # week a team is cut, it still has that week's score, so the page cannot
    # tell "lowest score, eliminated" from "lowest score, survived" on its own.
    elim = ", ".join('"%s": %d' % (tid, w) for w, tid, _ in eliminations)
    lines.append("  eliminated: {%s}," % elim)
    lines.append("  teams: {" + teams_body + "\n  },")
    lines.append("  points: {")
    for i, tid in enumerate(team_ids):
        vals = ", ".join("null" if v is None else "%.2f" % v for v in points[tid])
        comma = "" if i == len(team_ids) - 1 else ","
        key = ('"%s":' % tid).ljust(6)
        lines.append("    %s[%s]%s" % (key, vals, comma))
    lines.append("  }")
    lines.append("};")
    return "\n".join(lines) + "\n"


def render_readme_tail(weeks, eliminations, names):
    last = weeks[-1] if weeks else 0
    out = ["Current through week %d." % last, ""]
    if not eliminations:
        out.append("No team has been eliminated yet.")
    else:
        out.append("| Week | Eliminated | Low score |")
        out.append("|---|---|---|")
        for w, tid, low in eliminations:
            out.append("| %d | %s | %.2f |" % (w, names.get(tid, tid), low))
    out.append("")
    out.append("<!-- This section and data.js are rewritten by update_tracker.py; "
               "edit that script, not these lines. -->")
    return "\n".join(out) + "\n"


def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    text = DATA_JS.read_text(encoding="utf-8")
    header, teams_body, team_ids, existing_weeks, names = parse_data_js(text)
    log("data.js currently holds %d week(s): %s" % (len(existing_weeks), existing_weeks))

    weeks, points, eliminations, warnings, rows_by_week = build(team_ids, names)

    for w in warnings:
        log("WARNING: " + w)

    if not weeks:
        raise SystemExit("ABORT: no completed weeks found -- leaving data.js alone.")

    if len(weeks) < len(existing_weeks) and not force:
        raise SystemExit(
            "ABORT: rebuild produced %d week(s) but data.js already has %d. Sleeper's week "
            "counter may not have rolled over yet. Leaving the file alone -- rerun later, or "
            "pass --force if this is intended." % (len(weeks), len(existing_weeks)))

    new_data = render_data_js(header, teams_body, team_ids, weeks, points, eliminations)

    # Compare without the date stamp. It is today's date, so leaving it in the
    # comparison means a run on any new day always "differs" and commits --
    # which buried the first real week under a date-only commit.
    def without_stamp(s):
        return re.sub(r'^  generated: "[^"]*",\n', "", s, flags=re.M)

    if without_stamp(new_data) == without_stamp(text) and LINEUPS_JS.exists():
        log("No change -- already current through week %d." % weeks[-1])
        return 0

    if dry_run:
        log("--dry-run: data.js would become:\n")
        log(new_data)
        log("--dry-run: lineups.js would be rebuilt for weeks %s." % weeks)
        return 0

    DATA_JS.write_text(new_data, encoding="utf-8")
    log("Wrote data.js -- through week %d." % weeks[-1])

    # Lineups are only built when there is something new to write -- they cost
    # a 14 MB player-index fetch on a cold cache.
    try:
        lineups = build_lineups(rows_by_week, points, team_ids, player_index(), starter_slots())
        LINEUPS_JS.write_text(render_lineups_js(lineups), encoding="utf-8")
        log("Wrote lineups.js -- %d week(s), %.0f KB."
            % (len(lineups), LINEUPS_JS.stat().st_size / 1024))
    except SystemExit:
        raise
    except Exception as e:
        # A lineup failure must not cost us the scores, which are the point.
        log("WARNING: could not rebuild lineups.js (%s) -- scores are still current." % e)

    rtext = README.read_text(encoding="utf-8")
    idx = rtext.find("Current through week")
    if idx != -1:
        README.write_text(rtext[:idx] + render_readme_tail(weeks, eliminations, names),
                          encoding="utf-8")
        log("Updated README.md.")
    else:
        log("WARNING: could not find the 'Current through week' line in README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
