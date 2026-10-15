#!/usr/bin/env python3
"""Rebuild data.js (and the "current through" lines) from Sleeper.

Run with no arguments to refresh the tracker:

    python update_tracker.py

The script is idempotent and rebuilds every week from scratch on each run, so a
missed Tuesday heals itself on the next one. Standard library only -- Sleeper's
read API needs no auth and no packages.

Flags:
    --dry-run   print what would change, write nothing
    --rebuild   discard every recorded week and re-read them all from Sleeper.
                Destructive: a finished week can have changed upstream.
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

SEASON = None  # set from Sleeper state during build()

ROOT = Path(__file__).resolve().parent
DATA_JS = ROOT / "data.js"
LINEUPS_JS = ROOT / "lineups.js"
README = ROOT / "README.md"
CACHE = ROOT / ".cache"
DRIFT_LOG = ROOT / "drift.log"
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


def league_meta():
    """Starter slot labels in order (QB, RB, RB, WR, WR, FLEX x3) and this
    league's scoring table."""
    league = get("/league/%s" % LEAGUE_ID)
    slots = [p for p in (league.get("roster_positions") or []) if p not in ("BN", "IR", "TAXI")]
    return slots, (league.get("scoring_settings") or {})


def score_line(stats, scoring):
    """Fantasy points for a stat line under this league's scoring.

    Verified against a full week: applied to Sleeper's actual stats it
    reproduces all 156 of that week's real player scores to the cent, which is
    what makes it trustworthy applied to projections.
    """
    return sum(scoring.get(k, 0) * v for k, v in stats.items() if isinstance(v, (int, float)))


def projected_points(season, week, scoring):
    """Expected points per player for a finished week, cached forever -- a past
    week's projection never changes."""
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / ("proj-%s-%d.json" % (season, week))
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))

    raw = get("/projections/nfl/regular/%s/%d" % (season, week))
    out = {}
    for pid, stats in (raw or {}).items():
        if isinstance(stats, dict):
            out[pid] = round(score_line(stats, scoring), 2)
    cached.write_text(json.dumps(out), encoding="utf-8")
    log("  projections week %d: %d players" % (week, len(out)))
    return out


def build_lineups(rows_by_week, points, team_ids, players, slots, season, scoring, weeks):
    """Per team, per week: who started, what they scored against what they were
    projected to score, and what sat on the bench. Keyed week -> team ->
    {t: total, s: [[slot, name, nflteam, pts, proj]], b: [[pos, ...]]}."""
    out = {}
    for w, rows in rows_by_week.items():
        try:
            proj = projected_points(season, w, scoring)
        except SystemExit:
            raise
        except Exception as e:
            log("WARNING: no projections for week %d (%s) -- lineups lose their colour." % (w, e))
            proj = {}
        week_entry = {}
        for tid in team_ids:
            wi = weeks.index(w)
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
                    s.append([slot, "(empty)", "", 0.0, None])
                    continue
                name, pos, nfl = players.get(str(pid), [str(pid), "", ""])
                s.append([slot, name, nfl, pts, proj.get(str(pid))])

            started = {str(p) for p in starters}
            b = []
            for pid in (row.get("players") or []):
                if str(pid) in started:
                    continue
                name, pos, nfl = players.get(str(pid), [str(pid), "", ""])
                pts = ppts.get(str(pid))
                b.append([pos or "", name, nfl,
                          round(float(pts), 2) if pts is not None else 0.0,
                          proj.get(str(pid))])
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
        "//   starter: [slot, player, nfl team, points, projected]",
        "//   bench:   [position, player, nfl team, points, projected]",
        "//",
        "// Projected points are Sleeper's weekly projection scored under this",
        "// league's own settings, not a generic half-PPR number.",
        "",
        "const LEAGUE_LINEUPS = {",
    ]
    weeks = sorted(lineups, key=int)
    for wn, w in enumerate(weeks):
        head.append('  "%s": {' % w)
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


INDEX = ROOT / "index.html"


def stamp_assets(stamp):
    """Version the data script tags so a browser can't pair a fresh index.html
    with a cached data.js. GitHub Pages serves both with max-age, and the two
    files have to agree about their shape."""
    if not INDEX.exists():
        return
    text = INDEX.read_text(encoding="utf-8")
    new = re.sub(r'(<script src="(?:data|lineups)\.js)(?:\?v=[^"]*)?(">)',
                 lambda m: "%s?v=%s%s" % (m.group(1), stamp, m.group(2)), text)
    if new != text:
        INDEX.write_text(new, encoding="utf-8")
        log("Stamped index.html script tags with ?v=%s." % stamp)


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

    points = {}
    if "points:" in text:
        for tid, vals in re.findall(r'"(\d+)":\s*\[([^\]]*)\]', text.split("points:")[1]):
            points[tid] = [None if v.strip() == "null" else float(v) for v in vals.split(",")]

    elim = {}
    m = re.search(r"eliminated:\s*\{([^}]*)\}", text)
    if m:
        elim = {tid: int(w) for tid, w in re.findall(r'"(\d+)":\s*(\d+)', m.group(1))}

    return header, teams_body, team_ids, existing_weeks, names, points, elim


def parse_lineups_js():
    """Recorded lineups, keyed by week as a string. The emitted file is
    JSON-shaped on purpose so that it can be read back and preserved."""
    if not LINEUPS_JS.exists():
        return {}
    text = LINEUPS_JS.read_text(encoding="utf-8")
    try:
        blob = text[text.index("{", text.index("LEAGUE_LINEUPS")):].rstrip().rstrip(";")
        return json.loads(blob)
    except (ValueError, json.JSONDecodeError) as e:
        log("WARNING: could not read lineups.js (%s) -- it will be rebuilt." % e)
        return {}


def check_drift(team_ids, names, recorded_weeks, recorded_points):
    """Re-read the weeks already on file and report where Sleeper no longer
    agrees with what we recorded.

    Sleeper rewrites a finished week's `starters` array when the league's
    roster settings change, and recomputes that week's points from it. Week 5
    lost 19.65 points for one team this way -- a real starter was pushed onto
    the bench -- and it changed which team the guillotine took. So a recorded
    week is never overwritten from the API; the divergence is reported instead.
    """
    drift = []
    for i, w in enumerate(recorded_weeks):
        try:
            rows = {str(r["roster_id"]): r for r in get("/league/%s/matchups/%d" % (LEAGUE_ID, w))}
        except SystemExit:
            log("WARNING: could not re-read week %d to check it; skipping." % w)
            continue
        for tid in team_ids:
            was = (recorded_points.get(tid) or [None] * len(recorded_weeks))[i]
            if was is None or tid not in rows:
                continue
            now = round(score_of(rows[tid]), 2)
            if abs(now - was) > 0.02:
                drift.append((w, tid, was, now))
    return drift


def build(team_ids, names, recorded_weeks, recorded_points, recorded_elim):
    """Add any week that has finished since the last run.

    Append-only by design: weeks already on file are kept exactly as they were
    first recorded, right after they finished, while the league's roster layout
    still matched what was played.
    """
    global SEASON
    state = get("/state/nfl")
    SEASON = state.get("season")
    current_week = int(state["week"])

    alive = set(team_ids) - set(recorded_elim)
    start = (max(recorded_weeks) + 1) if recorded_weeks else 1
    log("Sleeper reports week %d; %d week(s) on file, looking for week %d onward."
        % (current_week, len(recorded_weeks), start))

    weeks, eliminations, warnings = [], [], []
    points = {tid: [] for tid in team_ids}
    rows_by_week = {}

    for w in range(start, MAX_WEEK + 1):
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


def record_drift(drift, names):
    """Write divergences to a committed file. The first time this happened the
    only trace was a log line nobody read, and a week's scores stayed wrong for
    a fortnight."""
    if not drift:
        return
    lines = ["", "## Checked %s" % date.today().isoformat(), "",
             "Sleeper now reports different scores for weeks already on file. "
             "The recorded values were kept.", "",
             "| Week | Team | Recorded | Sleeper now | Delta |", "|---|---|---|---|---|"]
    for w, tid, was, now in drift:
        lines.append("| %d | %s | %.2f | %.2f | %+.2f |" % (w, names.get(tid, tid), was, now, now - was))
    head = ("# Upstream drift\n\nWeeks are frozen once recorded, so this file is "
            "the record of Sleeper changing its mind about a finished week.\n")
    prior = DRIFT_LOG.read_text(encoding="utf-8") if DRIFT_LOG.exists() else head
    DRIFT_LOG.write_text(prior.rstrip("\n") + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def main():
    dry_run = "--dry-run" in sys.argv
    rebuild = "--rebuild" in sys.argv

    text = DATA_JS.read_text(encoding="utf-8")
    (header, teams_body, team_ids, recorded_weeks, names,
     recorded_points, recorded_elim) = parse_data_js(text)
    recorded_lineups = parse_lineups_js()

    if rebuild:
        log("--rebuild: discarding %d recorded week(s) and re-reading them all. "
            "Finished weeks can have changed upstream." % len(recorded_weeks))
        recorded_weeks, recorded_points, recorded_elim, recorded_lineups = [], {}, {}, {}

    log("data.js holds %d week(s): %s" % (len(recorded_weeks), recorded_weeks))

    drift = [] if rebuild else check_drift(team_ids, names, recorded_weeks, recorded_points)
    for w, tid, was, now in drift:
        log("DRIFT: week %d %s was %.2f, Sleeper now says %.2f -- keeping %.2f."
            % (w, names.get(tid, tid), was, now, was))
    if drift:
        log("DRIFT: %d recorded value(s) changed upstream; see drift.log. "
            "Recorded weeks were NOT overwritten." % len(drift))

    new_weeks, new_points, eliminations, warnings, rows_by_week = build(
        team_ids, names, recorded_weeks, recorded_points, recorded_elim)

    for w in warnings:
        log("WARNING: " + w)

    # Recorded weeks first, then anything that finished since.
    weeks = recorded_weeks + new_weeks
    if not weeks:
        raise SystemExit("ABORT: no completed weeks found -- leaving data.js alone.")
    points = {}
    for tid in team_ids:
        prior = (recorded_points.get(tid) or [None] * len(recorded_weeks))[:len(recorded_weeks)]
        points[tid] = prior + new_points[tid]
    elim_all = []
    for tid, w in sorted(recorded_elim.items(), key=lambda kv: kv[1]):
        low = points[tid][weeks.index(w)] if w in weeks else None
        elim_all.append((w, tid, low if low is not None else 0.0))
    elim_all += list(eliminations)

    new_data = render_data_js(header, teams_body, team_ids, weeks, points, elim_all)

    # Compare without the date stamp. It is today's date, so leaving it in the
    # comparison means a run on any new day always "differs" and commits --
    # which buried the first real week under a date-only commit.
    def without_stamp(s):
        return re.sub(r'^  generated: "[^"]*",\n', "", s, flags=re.M)

    unchanged = without_stamp(new_data) == without_stamp(text) and LINEUPS_JS.exists()
    if unchanged and not drift:
        log("No change -- already current through week %d." % weeks[-1])
        return 0

    if dry_run:
        log("--dry-run: %d new week(s) %s, %d drift row(s). Nothing written."
            % (len(new_weeks), new_weeks, len(drift)))
        return 0

    record_drift(drift, names)
    if unchanged:
        log("No new week, but drift was recorded in drift.log.")
        return 0

    DATA_JS.write_text(new_data, encoding="utf-8")
    log("Wrote data.js -- through week %d." % weeks[-1])

    # Only the new weeks are built; the rest are carried over exactly as they
    # were first recorded. Lineups cost a 14 MB player-index fetch cold.
    try:
        slots, scoring = league_meta()
        fresh = build_lineups(rows_by_week, points, team_ids,
                              player_index(), slots, SEASON, scoring, weeks)
        merged = dict(recorded_lineups)
        for w, entry in fresh.items():
            merged[str(w)] = entry
        LINEUPS_JS.write_text(render_lineups_js(merged), encoding="utf-8")
        log("Wrote lineups.js -- %d week(s) (%d carried over, %d new), %.0f KB."
            % (len(merged), len(recorded_lineups), len(fresh), LINEUPS_JS.stat().st_size / 1024))
        stamp_assets(date.today().isoformat())
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
