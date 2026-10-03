#!/usr/bin/env python3
"""Print the workspace's status facts — what is true right now.

Read-only and deterministic: measurements, dates, counts and booleans relative
to configured thresholds (scripts/lib/facts.py documents the JSON contract).
No advice or verdicts; the coach interprets. The reference date is the newest
date in the data, never the wall clock, unless --as-of sets it.

Usage: python3 scripts/status.py [--json] [--as-of YYYY-MM-DD]
  --json    the full facts dict (sorted keys, stable across runs)
  default   a brief of at most 15 lines
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import facts as facts_lib
from lib import workspace


def _num(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _signed(value) -> str:
    return "n/a" if value is None else (("+" if value > 0 else "") + _num(value))


def _count(n: int, unit: str) -> str:
    return f"{n} {unit}{'' if n == 1 else 's'}"


def _days(n: int) -> str:
    return f"{_count(n, 'day')} ago"


def brief(f: dict) -> list[str]:
    """The facts as at most 15 plain lines (numbers, dates, names only)."""
    if f["as_of"] is None:
        return ["as of: no dated data in this workspace",
                f"anchors missing: {', '.join(f['anchors']['missing']) or 'none'}",
                f"goal: {f['goal']['track'] or 'none'}"]
    s, c, b = f["sessions"], f["consistency"], f["benchmarks"]
    lines = [f"as of {f['as_of']}"]
    if s["last"]:
        lines.append(f"sessions: {s['total']} total; last session: {_days(s['days_since_last'])} "
                     f"({s['last']['modality']}, {s['last']['date']})")
    else:
        lines.append("sessions: 0 total")
    if s["last_structured"]:
        ls = s["last_structured"]
        lines.append(f"last structured session: {_days(s['days_since_last_structured'])} "
                     f"({ls['modality']}, {ls['date']})")
    else:
        lines.append("last structured session: none")
    lines.append(f"weeks with >={c['threshold_sessions']} structured sessions: "
                 f"{c['weeks_meeting']} of {c['weeks_total']}; current streak "
                 f"{c['current_streak_weeks']}; longest {c['longest_streak_weeks']}")
    if f["weeks"]:
        w = f["weeks"][-1]
        lines.append(f"week {w['week']}: {w['structured_sessions']} structured sessions, "
                     f"{w['structured_min']} structured min, {w['baseline_min']} baseline min")
    if b["latest"]:
        lines.append(f"newest benchmark: {b['latest']['date']} ({b['age_days']} days; "
                     f"configured cadence {b['cadence_days']}); {b['count']} recorded")
    else:
        lines.append("benchmarks recorded: 0")
    lines.append(f"anchors missing: {', '.join(f['anchors']['missing']) or 'none'}")
    lines.append(f"goal: {f['goal']['track'] or 'none'}")
    p = f["plan"]
    lines.append(f"plan for {p['current_week']}: {'present' if p['exists'] else 'none'}; "
                 f"latest plan: {p['latest'] or 'none'}; latest review: "
                 f"{f['review']['latest'] or 'none'}")
    r = f["recovery"]
    rhr, hrv = r["resting_hr"], r["hrv"]
    if rhr["latest"]:
        above = f"at or above +{_num(rhr['elevated_threshold_bpm'])}"
        elevated = (f"days {above}: n/a (no 28-day median)" if rhr["days_elevated"] is None
                    else f"{_count(rhr['days_elevated'], 'day')} {above}")
        lines.append(f"resting HR: {_num(rhr['latest']['value'])} latest ({rhr['latest']['date']}); "
                     f"7-day median {_num(rhr['median_7d'])} (n={rhr['n_7d']}); 28-day median "
                     f"{_num(rhr['median_28d'])} (n={rhr['n_28d']}); {elevated}")
    else:
        lines.append("resting HR: no points")
    if hrv["latest"]:
        lines.append(f"HRV: {_num(hrv['latest']['value'])} latest ({hrv['latest']['date']}); "
                     f"7-day median {_num(hrv['median_7d'])} (n={hrv['n_7d']}); 28-day median "
                     f"{_num(hrv['median_28d'])} (n={hrv['n_28d']}); delta "
                     f"{_signed(hrv['delta_vs_28d'])}")
    else:
        lines.append("HRV: no points")
    vo2 = r["vo2_max"]["latest"]
    lines.append(f"VO2max: {_num(vo2['value'])} latest ({vo2['date']})" if vo2 else "VO2max: no points")
    pl = f["pipeline"]
    amb = "n/a" if pl["ambiguous_cases"] is None else pl["ambiguous_cases"]
    lines.append(f"pipeline: newest workout end {pl['newest_workout_end'] or 'none'}; photos pending "
                 f"{pl['photos_pending']}; inbox photos {pl['photos_inbox']}; ambiguous cases {amb}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print the full facts dict")
    ap.add_argument("--as-of", type=date.fromisoformat, metavar="YYYY-MM-DD",
                    help="reference date (default: newest date in the data)")
    args = ap.parse_args(argv)

    root = workspace.root()
    workspace.require(root)
    result = facts_lib.collect(facts_lib.load(root), as_of=args.as_of)
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print("\n".join(brief(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
