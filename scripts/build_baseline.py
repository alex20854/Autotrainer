#!/usr/bin/env python3
"""Rebuild data/baseline.jsonl — the weekly baseline-activity rollup.

Baseline activity is unstructured movement (walks, hikes...) that the coach
tracks in aggregate but does not prescribe or score: active-recovery volume,
the §9 metabolic-frequency picture, week-over-week movement trends. One JSON
line per ISO week, fully regenerated on every run, never hand-edited (same
rules as index.jsonl).

Inputs: derived workout records of the configured baseline types, consolidated
(duplicate captures collapse), minus anything claimed by a session file — a
walk promoted into the ledger is a session, not baseline (no double counting).

Usage: python3 scripts/build_baseline.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import records
from lib import sessions as sessions_lib

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = REPO_ROOT / "data" / "sessions"
BASELINE_PATH = REPO_ROOT / "data" / "baseline.jsonl"
CONFIG_PATH = REPO_ROOT / "config" / "athlete.yaml"


def rollup(workouts: list[dict], claimed: set[str], classification: dict) -> list[dict]:
    """Pure aggregation: baseline-type records -> per-ISO-week summary lines."""
    baseline_types = set(classification.get("baseline_types") or [])
    candidates = records.consolidate_records([
        w for w in workouts if w["workout_type"] in baseline_types
    ])

    weeks: dict[str, dict] = {}
    for w in candidates:
        refs = [f"data/derived/workouts/{w['record_id']}.json"]
        refs += [co["ref"] for co in w.get("co_refs") or []]
        if any(ref in claimed for ref in refs):
            continue  # promoted to a session — lives in the ledger instead
        iso = records.parse_dt(w["start"]).isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        entry = weeks.setdefault(week, {
            "week": week, "count": 0, "minutes": 0.0, "distance_m": 0,
            "kcal": 0, "_hr_weighted": 0.0, "_hr_seconds": 0.0, "by_type": {},
        })
        duration = w.get("duration_s") or 0
        entry["count"] += 1
        entry["minutes"] += duration / 60
        entry["distance_m"] += round(w.get("distance_m") or 0)
        entry["kcal"] += round(w.get("kcal") or 0)
        hr_avg = (w.get("hr") or {}).get("avg")
        if hr_avg and duration:
            entry["_hr_weighted"] += hr_avg * duration
            entry["_hr_seconds"] += duration
        entry["by_type"][w["workout_type"]] = entry["by_type"].get(w["workout_type"], 0) + 1

    out = []
    for week in sorted(weeks):
        entry = weeks[week]
        hr_s = entry.pop("_hr_seconds")
        hr_w = entry.pop("_hr_weighted")
        entry["minutes"] = round(entry["minutes"])
        entry["hr_avg"] = round(hr_w / hr_s) if hr_s else None
        out.append(entry)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workouts-dir", type=Path, default=records.WORKOUTS_DIR)
    ap.add_argument("--out", type=Path, default=BASELINE_PATH)
    args = ap.parse_args()

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    classification = config.get("classification") or {}
    workouts = records.load_records(args.workouts_dir)
    claimed = sessions_lib.already_claimed(SESSIONS_DIR)

    lines = rollup(workouts, claimed, classification)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
    total_min = sum(l["minutes"] for l in lines)
    print(f"baseline.jsonl: {len(lines)} weeks, {sum(l['count'] for l in lines)} "
          f"activities, {total_min} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
