"""Status facts — what is true in a workspace right now (scripts/status.py).

Measurements only: numbers, dates, counts and booleans relative to configured
thresholds. No advice, scores or verdicts — deciding what a fact *means* is
the coach's job (Claude, via the /coach playbooks). Every function here is
pure over already-loaded data (no I/O, no clock) except `load(root)`, which
reads the workspace files and turns any missing or unreadable file into an
empty value, never an exception.

The reference date `as_of` is the newest date present in the data (index rows,
baseline weeks — read as their Monday — and metric points), never the wall
clock; only an explicit `as_of` argument changes it. Dated data after `as_of`
is ignored (sessions, benchmarks, metric points; a baseline week counts when
its Monday is <= `as_of`, so the as_of week carries that whole week's baseline
minutes). Everything else is the present state of the files whatever `as_of`
is: anchors, goal, plan.exists/latest, review.latest (a plan written ahead
for a later week is still the latest) and pipeline. An earlier `as_of`
therefore replays the dated measurements of that day, not the whole picture.

Output contract (`collect(data, as_of=None)`; other scripts and the playbooks
read this shape — change it deliberately and update docs/schema.md):

  {
    "as_of": "YYYY-MM-DD",               # null only when the workspace has no data
    "sessions": {
      "total": n,                        # index rows dated <= as_of
      "last": {"date", "modality"} | null,
      "days_since_last": n | null,
      "last_structured": {"date", "modality"} | null,
      "days_since_last_structured": n | null},
    "weeks": [                           # contiguous ISO weeks from the week of the first
                                         # index row (session) to the as_of week,
                                         # zero-filled, oldest first; baseline-only weeks
                                         # before the first session are not listed. With
                                         # no index rows: just the as_of week.
      {"week": "2026-W40",
       "sessions": n,                    # all index rows that week
       "structured_sessions": n,
       "structured_min": n,              # minutes of structured sessions
       "baseline_min": n,                # data/baseline.jsonl minutes for the week
       "by_modality_min": {modality: n}}],   # minutes of all index rows by modality
    "consistency": {
      "threshold_sessions": 3,           # status.consistency_sessions
      "weeks_meeting": n,                # weeks with structured_sessions >= threshold
      "weeks_total": n,                  # len(weeks), the in-progress as_of week included;
                                         # 0 when there are no index rows
      "current_streak_weeks": n,         # consecutive meeting weeks counted back from
                                         # the as_of week; the as_of week is skipped
                                         # when it has not (yet) met the threshold
      "longest_streak_weeks": n},
    "benchmarks": {
      "count": n,                        # benchmarks.md headings dated <= as_of
      "latest": {"date", "title"} | null,
      "age_days": n | null,              # as_of - latest.date
      "cadence_days": 42,                # status.benchmark_cadence_days
      "past_cadence": bool | null},      # age_days > cadence_days
    "anchors": {
      "hr_max", "lthr", "hr_resting",    # athlete.* values from config (null if unset)
      "power": {modality: {field: value}},   # the config's power slots, as-is
      "missing": ["lthr", "power.rowerg.ftp", ...]},
                                         # null athlete anchors, then every null field
                                         # of a power slot whose modality one of the
                                         # listed `equipment` machines maps to
                                         # (apply_merges.MACHINE_TO_MODALITY; an id that
                                         # is itself a modality name counts as that one)
    "goal": {"active": bool, "track": str | null},
                                         # the goals.md section whose '## ' heading starts
                                         # 'Active goal' has a '- Track: <value>' line
                                         # ('**Track:**' / '**Track**:' too; fenced lines
                                         # count). A value with '|' or '<' is the
                                         # template's placeholder and does not count.
    "plan": {"current_week": "2026-W40", # ISO week of as_of (plan/review: file state now)
             "exists": bool,             # plans/<current_week>.md is a file
             "latest": "2026-W38" | null},   # newest plans/*.md stem
    "review": {"latest": str | null},    # newest reports/*.md stem
    "recovery": {
      "resting_hr": {
        "latest": {"date", "value"} | null,
        "median_7d", "median_28d",       # medians of the points in the 7 / 28 days
                                         # ending at as_of (inclusive); null if none
        "delta_vs_28d",                  # latest.value - median_28d
        "n_7d", "n_28d",                 # point counts, so sparse data is visible
        "elevated_threshold_bpm": 5,     # status.resting_hr_elevated_bpm
        "days_elevated": n | null},      # consecutive most-recent points in the 28-day
                                         # window with value >= median_28d + threshold
      "hrv": {"latest", "median_7d", "median_28d", "delta_vs_28d", "n_7d", "n_28d"},
      "vo2_max": {"latest": {"date", "value"} | null}},
    "pipeline": {
      "newest_workout_end": iso | null,  # latest `end` across data/derived/workouts
      "photos_pending": n,               # data/derived/photo_finder.json pending[]
      "photos_inbox": n,                 # files in data/inbox/photos
      "ambiguous_cases": n | null}       # data/derived/proposals.json ambiguous[]
  }

Thresholds live under an optional `status:` block in config/athlete.yaml; the
defaults below apply when it is absent, and to any value of the wrong type
(the threshold in use is echoed in the output). None of them is a cited standard.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

# --- configurable thresholds (config/athlete.yaml: status.*) -----------------

DEFAULTS = {
    # Engineering default: modalities counted as baseline movement rather than
    # structured training when they reach the session ledger (promoted walks).
    "unstructured_modalities": ["walk", "treadmill-walk"],
    # Practitioner heuristic [unverified]: spec §9's minimum viable week is
    # three easy sessions plus one hard one; this counts structured sessions
    # only and does not classify intensity.
    "consistency_sessions": 3,
    # Engineering default taken from the workspace template's own benchmarks.md
    # guidance ("re-test zones every 4-6 weeks"): the upper end, 6 weeks.
    "benchmark_cadence_days": 42,
    # Practitioner heuristic [unverified]: resting HR this many bpm above its
    # 28-day median is commonly read as a recovery signal; reported, not judged.
    "resting_hr_elevated_bpm": 5,
}

ATHLETE_ANCHORS = ("hr_max", "lthr", "hr_resting")

# Benchmark log headings: '### YYYY-MM-DD - <title>' (hyphen, en or em dash).
BENCHMARK_HEADING = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\s+[-–—]\s+(.+?)\s*$")
# '- Track: x', '- **Track:** x' and '- **Track**: x'.
TRACK_LINE = re.compile(r"^\s*[-*]\s*(?:\*\*)?Track(?:\*\*)?:(?:\*\*)?\s*(.*?)\s*$",
                        re.IGNORECASE)
# The template's fill-in line lists the options ('a | b | c') or a <placeholder>.
TRACK_PLACEHOLDER = re.compile(r"[|<]")
FENCE = re.compile(r"^\s*(```|~~~)")


# --- loading (the only I/O) ----------------------------------------------------

def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_json(path: Path):
    text = _read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    for line in (_read_text(path) or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _md_stems(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.md") if p.is_file())


def load(root: Path) -> dict:
    """Read every workspace file the facts need. Missing -> empty/None."""
    root = Path(root)
    try:
        config = yaml.safe_load(_read_text(root / "config" / "athlete.yaml") or "") or {}
    except yaml.YAMLError:
        config = {}
    if not isinstance(config, dict):
        config = {}

    workout_ends = []
    workouts_dir = root / "data" / "derived" / "workouts"
    if workouts_dir.is_dir():
        for path in sorted(workouts_dir.glob("*.json")):
            rec = _read_json(path)
            if isinstance(rec, dict) and rec.get("end"):
                workout_ends.append(str(rec["end"]))

    inbox = root / "data" / "inbox" / "photos"
    inbox_count = (sum(1 for p in inbox.iterdir() if p.is_file() and not p.name.startswith("."))
                   if inbox.is_dir() else 0)

    return {
        "config": config,
        "index": _read_jsonl(root / "data" / "index.jsonl"),
        "baseline": _read_jsonl(root / "data" / "baseline.jsonl"),
        "metrics": _read_jsonl(root / "data" / "derived" / "metrics.jsonl"),
        "benchmarks_md": _read_text(root / "benchmarks.md"),
        "goals_md": _read_text(root / "goals.md"),
        "plans": _md_stems(root / "plans"),
        "reports": _md_stems(root / "reports"),
        "workout_ends": workout_ends,
        "photo_finder": _read_json(root / "data" / "derived" / "photo_finder.json"),
        "proposals": _read_json(root / "data" / "derived" / "proposals.json"),
        "photos_inbox": inbox_count,
    }


# --- pure helpers ----------------------------------------------------------------

def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def thresholds(config: dict) -> dict:
    """DEFAULTS overlaid with config/athlete.yaml's optional status: block.

    An override is kept only when its type fits: a number for the numeric
    thresholds (a quoted "3" is not one), a list of strings — or one string,
    read as a one-item list — for unstructured_modalities. Anything else
    falls back to the default rather than miscounting or raising."""
    out = {k: list(v) if isinstance(v, list) else v for k, v in DEFAULTS.items()}
    block = (config or {}).get("status")
    if not isinstance(block, dict):
        return out
    for key, value in block.items():
        if key not in DEFAULTS or value is None:
            continue
        if key == "unstructured_modalities":
            if isinstance(value, str):
                out[key] = [value]
            elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                out[key] = list(value)
        elif _number(value):
            out[key] = value
    return out


def iso_week(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_monday(week: str) -> date | None:
    m = re.match(r"^(\d{4})-W(\d{2})$", week or "")
    if not m:
        return None
    try:
        return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        return None


def _to_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _iso_weeks_between(first: date, last: date) -> list[str]:
    weeks, d = [], first - timedelta(days=first.weekday())
    while d <= last:
        weeks.append(iso_week(d))
        d += timedelta(days=7)
    return weeks


def _minutes(seconds: float) -> int:
    return round(seconds / 60)


def _round1(value):
    return None if value is None else round(value, 1)


def reference_date(data: dict) -> date | None:
    """Newest date present in index rows, baseline weeks (Monday) and metrics."""
    dates = [_to_date(r.get("date")) for r in data.get("index") or []]
    dates += [week_monday(b.get("week")) for b in data.get("baseline") or []]
    dates += [_to_date(m.get("date")) for m in data.get("metrics") or []]
    dates = [d for d in dates if d]
    return max(dates) if dates else None


# --- fact groups -----------------------------------------------------------------

def _rows(data: dict, as_of: date) -> list[dict]:
    rows = []
    for r in data.get("index") or []:
        d = _to_date(r.get("date"))
        if d and d <= as_of:
            rows.append({**r, "_date": d})
    rows.sort(key=lambda r: (r["_date"], str(r.get("start") or "")))
    return rows


def session_facts(rows: list[dict], unstructured: set[str], as_of: date) -> dict:
    structured = [r for r in rows if r.get("modality") not in unstructured]

    def brief(r):
        return {"date": r["_date"].isoformat(), "modality": r.get("modality")} if r else None

    last = rows[-1] if rows else None
    last_s = structured[-1] if structured else None
    return {
        "total": len(rows),
        "last": brief(last),
        "days_since_last": (as_of - last["_date"]).days if last else None,
        "last_structured": brief(last_s),
        "days_since_last_structured": (as_of - last_s["_date"]).days if last_s else None,
    }


def week_facts(rows: list[dict], baseline: list[dict], unstructured: set[str],
               as_of: date) -> list[dict]:
    baseline_min = {}
    for b in baseline:
        monday = week_monday(b.get("week"))
        if monday and monday <= as_of:
            baseline_min[b["week"]] = baseline_min.get(b["week"], 0) + (b.get("minutes") or 0)
    # Start at the first session, not the first baseline week: a full Health
    # export can put years of walks in baseline.jsonl before any training.
    first = rows[0]["_date"] if rows else as_of
    acc = {w: {"sessions": 0, "structured": 0, "structured_s": 0.0, "by_mod_s": {}}
           for w in _iso_weeks_between(first, as_of)}
    for r in rows:
        entry = acc[iso_week(r["_date"])]
        seconds = r.get("duration_s") or 0
        entry["sessions"] += 1
        modality = r.get("modality") or "unknown"
        entry["by_mod_s"][modality] = entry["by_mod_s"].get(modality, 0) + seconds
        if r.get("modality") not in unstructured:
            entry["structured"] += 1
            entry["structured_s"] += seconds
    return [{
        "week": week,
        "sessions": e["sessions"],
        "structured_sessions": e["structured"],
        "structured_min": _minutes(e["structured_s"]),
        "baseline_min": round(baseline_min.get(week, 0)),
        "by_modality_min": {m: _minutes(s) for m, s in sorted(e["by_mod_s"].items())},
    } for week, e in acc.items()]


def consistency_facts(weeks: list[dict], threshold: int) -> dict:
    meets = [w["structured_sessions"] >= threshold for w in weeks]
    longest = run = 0
    for ok in meets:
        run = run + 1 if ok else 0
        longest = max(longest, run)
    tail = meets[:-1] if meets and not meets[-1] else meets  # as_of week may be incomplete
    current = 0
    for ok in reversed(tail):
        if not ok:
            break
        current += 1
    return {"threshold_sessions": threshold, "weeks_meeting": sum(meets),
            "weeks_total": len(weeks), "current_streak_weeks": current,
            "longest_streak_weeks": longest}


def _outside_fences(text: str):
    """Yield the lines of a markdown text that are not inside ``` / ~~~ fences."""
    fenced = False
    for line in (text or "").splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield line


def parse_benchmarks(text: str | None) -> list[dict]:
    """Dated benchmark headings in file order: [{date, title}]."""
    out = []
    for line in _outside_fences(text or ""):
        m = BENCHMARK_HEADING.match(line)
        if m and _to_date(m.group(1)):
            out.append({"date": m.group(1), "title": m.group(2)})
    return out


def benchmark_facts(text: str | None, cadence: int, as_of: date) -> dict:
    entries = [b for b in parse_benchmarks(text) if _to_date(b["date"]) <= as_of]
    latest = None
    for b in entries:  # newest date wins; first in file order on a tie
        if latest is None or b["date"] > latest["date"]:
            latest = b
    age = (as_of - _to_date(latest["date"])).days if latest else None
    return {"count": len(entries), "latest": latest, "age_days": age,
            "cadence_days": cadence, "past_cadence": (age > cadence) if age is not None else None}


def anchor_facts(config: dict, machine_to_modality: dict) -> dict:
    athlete = config.get("athlete") or {}
    power = config.get("power") or {}
    power = {m: dict(slot) for m, slot in power.items() if isinstance(slot, dict)}
    missing = [a for a in ATHLETE_ANCHORS if athlete.get(a) is None]
    used = {machine_to_modality.get(m, m) for m in config.get("equipment") or []}
    for modality in sorted(m for m in used if m in power):
        missing += [f"power.{modality}.{f}" for f, v in sorted(power[modality].items()) if v is None]
    return {**{a: athlete.get(a) for a in ATHLETE_ANCHORS}, "power": power, "missing": missing}


def goal_facts(text: str | None) -> dict:
    """First filled '- Track:' line in the 'Active goal' section. Fenced lines
    are read too (a coach may fill the template's fenced block in place); only
    a heading outside a fence changes the section."""
    in_section = fenced = False
    for line in (text or "").splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced and line.startswith("## "):
            in_section = line[3:].strip().lower().startswith("active goal")
            continue
        if in_section:
            m = TRACK_LINE.match(line)
            if m and m.group(1) and not TRACK_PLACEHOLDER.search(m.group(1)):
                return {"active": True, "track": m.group(1)}
    return {"active": False, "track": None}


def _series(metrics: list[dict], name: str, as_of: date) -> list[tuple[date, float]]:
    by_day = {}
    for m in metrics:
        d = _to_date(m.get("date"))
        if m.get("name") == name and d and d <= as_of and isinstance(m.get("value"), (int, float)):
            by_day[d] = float(m["value"])
    return sorted(by_day.items())


def recovery_series_facts(points: list[tuple[date, float]], as_of: date) -> dict:
    w7 = [v for d, v in points if (as_of - d).days < 7]
    w28 = [v for d, v in points if (as_of - d).days < 28]
    latest = points[-1] if points else None
    med7 = statistics.median(w7) if w7 else None
    med28 = statistics.median(w28) if w28 else None
    return {
        "latest": {"date": latest[0].isoformat(), "value": latest[1]} if latest else None,
        "median_7d": _round1(med7), "median_28d": _round1(med28),
        "delta_vs_28d": _round1(latest[1] - med28) if latest and med28 is not None else None,
        "n_7d": len(w7), "n_28d": len(w28),
    }


def days_elevated(points: list[tuple[date, float]], median_28d, threshold, as_of: date):
    if median_28d is None:
        return None
    count = 0
    for d, v in reversed(points):
        if (as_of - d).days >= 28 or v < median_28d + threshold:
            break
        count += 1
    return count


def recovery_facts(metrics: list[dict], elevated_bpm, as_of: date) -> dict:
    rhr_points = _series(metrics, "resting_heart_rate", as_of)
    rhr = recovery_series_facts(rhr_points, as_of)
    rhr["elevated_threshold_bpm"] = elevated_bpm
    rhr["days_elevated"] = days_elevated(rhr_points, rhr["median_28d"], elevated_bpm, as_of)
    vo2 = _series(metrics, "vo2_max", as_of)
    return {
        "resting_hr": rhr,
        "hrv": recovery_series_facts(_series(metrics, "heart_rate_variability", as_of), as_of),
        "vo2_max": {"latest": {"date": vo2[-1][0].isoformat(), "value": vo2[-1][1]} if vo2 else None},
    }


def pipeline_facts(data: dict) -> dict:
    newest = None
    for end in data.get("workout_ends") or []:
        try:
            ts = datetime.fromisoformat(end)
            key = ts.timestamp()
        except (TypeError, ValueError):
            continue
        if newest is None or key > newest[0]:
            newest = (key, end)
    finder = data.get("photo_finder")
    pending = finder.get("pending") if isinstance(finder, dict) else None
    proposals = data.get("proposals")
    ambiguous = proposals.get("ambiguous") if isinstance(proposals, dict) else None
    return {
        "newest_workout_end": newest[1] if newest else None,
        "photos_pending": len(pending) if isinstance(pending, list) else 0,
        "photos_inbox": data.get("photos_inbox") or 0,
        "ambiguous_cases": len(ambiguous) if isinstance(ambiguous, list) else None,
    }


def _machine_to_modality() -> dict:
    try:
        from apply_merges import MACHINE_TO_MODALITY  # scripts/ on sys.path
        return MACHINE_TO_MODALITY
    except ImportError:
        return {}


def collect(data: dict, as_of=None, machine_to_modality: dict | None = None) -> dict:
    """The full facts dict (see the module docstring for the contract)."""
    config = data.get("config") or {}
    limits = thresholds(config)
    as_of = _to_date(as_of) if as_of is not None else reference_date(data)
    if machine_to_modality is None:
        machine_to_modality = _machine_to_modality()
    anchors = anchor_facts(config, machine_to_modality)
    goal = goal_facts(data.get("goals_md"))
    plans, reports = data.get("plans") or [], data.get("reports") or []
    pipeline = pipeline_facts(data)
    if as_of is None:  # an empty workspace: nothing dated to measure against
        return {"as_of": None, "sessions": session_facts([], set(), date.min),
                "weeks": [], "consistency": consistency_facts([], limits["consistency_sessions"]),
                "benchmarks": {"count": 0, "latest": None, "age_days": None,
                               "cadence_days": limits["benchmark_cadence_days"],
                               "past_cadence": None},
                "anchors": anchors, "goal": goal,
                "plan": {"current_week": None, "exists": False,
                         "latest": plans[-1] if plans else None},
                "review": {"latest": reports[-1] if reports else None},
                "recovery": recovery_facts([], limits["resting_hr_elevated_bpm"], date.min),
                "pipeline": pipeline}

    unstructured = set(limits["unstructured_modalities"] or [])
    rows = _rows(data, as_of)
    weeks = week_facts(rows, data.get("baseline") or [], unstructured, as_of)
    current_week = iso_week(as_of)
    return {
        "as_of": as_of.isoformat(),
        "sessions": session_facts(rows, unstructured, as_of),
        "weeks": weeks,
        "consistency": consistency_facts(weeks if rows else [], limits["consistency_sessions"]),
        "benchmarks": benchmark_facts(data.get("benchmarks_md"),
                                      limits["benchmark_cadence_days"], as_of),
        "anchors": anchors,
        "goal": goal,
        "plan": {"current_week": current_week, "exists": current_week in plans,
                 "latest": plans[-1] if plans else None},
        "review": {"latest": reports[-1] if reports else None},
        "recovery": recovery_facts(data.get("metrics") or [],
                                   limits["resting_hr_elevated_bpm"], as_of),
        "pipeline": pipeline,
    }
