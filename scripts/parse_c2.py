#!/usr/bin/env python3
"""Opportunistic parser: Concept2 Logbook CSV exports -> derived workout records.

C2 sync is flaky (spec §5) — when it works, the Logbook "Export CSV" gives the
richest trace: per-split pace/watts/HR. This targets the individual-workout CSV
("Per-Stroke" not required); the general logbook CSV (one row per workout) is
also handled. TCX/FIT are deferred (spec §14.5).

Machine type comes from the CSV's type column when present; SkiErg/BikeErg/
RowErg all export the same shape.

Usage: python3 scripts/parse_c2.py [dir_or_file ...] [--out DIR]
       (default input: data/raw/c2/)
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import records

# Logbook summary-CSV column names (Concept2 exports these headers verbatim)
SUMMARY_COLS = {"Date", "Work Time (Seconds)"}


def parse_file(path: Path, out_dir: Path | None = None) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    if SUMMARY_COLS.issubset(rows[0].keys()):
        out = [rec for row in rows if (rec := _summary_row_to_record(row, path))]
    else:
        rec = _detail_csv_to_record(rows, path)
        out = [rec] if rec else []
    for rec in out:
        records.save_record(rec, out_dir)
    return out


def _summary_row_to_record(row: dict, source: Path) -> dict | None:
    start_raw = row.get("Date")
    secs = _num(row.get("Work Time (Seconds)"))
    if not start_raw or secs is None:
        return None
    start = records.parse_dt(start_raw).isoformat()
    end = (records.parse_dt(start_raw) + timedelta(seconds=secs)).isoformat()
    distance = _num(row.get("Work Distance"))
    watts = _num(row.get("Avg Watts"))
    machine = (row.get("Type") or "rower").strip().lower()
    return records.make_record(
        source_kind="c2",
        source_file=str(_repo_rel(source)),
        workout_type=f"c2-{machine}",
        start=start,
        end=end,
        duration_s=secs,
        kcal=_num(row.get("Total Cal") or row.get("Calories")),
        distance_m=distance,
        hr=_hr_from_summary(row),
        splits=None,
        watts=[[0, watts]] if watts else None,
    )


def _hr_from_summary(row: dict) -> dict | None:
    avg = _num(row.get("Avg Heart Rate"))
    return {"avg": round(avg), "max": None, "series": []} if avg else None


def _detail_csv_to_record(rows: list[dict], source: Path) -> dict | None:
    """Per-workout split CSV: rows are splits with Time/Distance/Pace/Watts[/HR]."""
    splits = []
    for row in rows:
        t = _num(row.get("Time (seconds)") or row.get("Time"))
        if t is None:
            continue
        splits.append({
            "t_s": t,
            "distance_m": _num(row.get("Distance (meters)") or row.get("Distance")),
            "pace_s_per_500m": _num(row.get("Pace (seconds)") or row.get("Pace")),
            "watts": _num(row.get("Watts")),
            "hr": _num(row.get("Heart Rate") or row.get("Avg Heart Rate")),
        })
    if not splits:
        return None
    # Split CSVs carry no absolute timestamp; use the file's mtime date as a
    # low-confidence anchor — the proposal script treats c2 detail records as
    # duration/structure evidence, not timing evidence.
    import datetime as _dt
    mtime = _dt.datetime.fromtimestamp(source.stat().st_mtime).replace(microsecond=0)
    total_s = splits[-1]["t_s"]
    start = mtime.isoformat()
    end = (mtime + timedelta(seconds=total_s)).isoformat()
    watt_values = [s["watts"] for s in splits if s["watts"]]
    return records.make_record(
        source_kind="c2",
        source_file=str(_repo_rel(source)),
        workout_type="c2-detail",
        start=start,
        end=end,
        duration_s=total_s,
        distance_m=splits[-1]["distance_m"],
        splits=splits,
        watts=[[round(s["t_s"]), round(s["watts"])] for s in splits if s["watts"]] or None,
        hr=None,
    )


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _repo_rel(path: Path) -> Path:
    try:
        return path.resolve().relative_to(records.REPO_ROOT)
    except ValueError:
        return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="*", default=["data/raw/c2"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    total = 0
    for inp in args.inputs:
        p = Path(inp)
        files = sorted(p.glob("*.csv")) if p.is_dir() else [p] if p.exists() else []
        for f in files:
            total += len(parse_file(f, args.out))
    print(f"c2: {total} workouts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
