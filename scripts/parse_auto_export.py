#!/usr/bin/env python3
"""Ongoing parser: Health Auto Export JSON files -> derived workout records.

Health Auto Export (Premium automation) drops JSON into an iCloud Drive folder
the user syncs into data/raw/health/. Arrival is periodic and unreliable (iOS
exports only while unlocked — spec §5), so this parser is pull-based and
idempotent: it scans every *.json present and overwrites records in place.

The app's "Workouts" export shape (data.workouts[]) is the target; each workout
carries summary fields plus optional heartRateData samples. Field variants seen
across app versions are tolerated — missing fields become null, never errors.

Usage: python3 scripts/parse_auto_export.py [dir_or_file ...] [--out DIR]
       (default input: data/raw/health/)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import records


def parse_file(path: Path, out_dir: Path | None = None) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"skipping {path}: not valid JSON ({e})", file=sys.stderr)
        return []
    workouts = (payload.get("data") or {}).get("workouts") or []
    out = []
    for w in workouts:
        rec = _to_record(w, path)
        if rec:
            records.save_record(rec, out_dir)
            out.append(rec)
    return out


def _to_record(w: dict, source: Path) -> dict | None:
    start, end = w.get("start"), w.get("end")
    if not start or not end:
        return None
    start, end = records.parse_dt(start).isoformat(), records.parse_dt(end).isoformat()

    series = []
    for sample in w.get("heartRateData") or []:
        ts = sample.get("date") or sample.get("timestamp")
        bpm = _qty(sample.get("qty") if "qty" in sample else sample.get("Avg", sample.get("avg")))
        if ts is None or bpm is None:
            continue
        offset = (records.parse_dt(ts) - records.parse_dt(start)).total_seconds()
        series.append([round(offset), round(bpm)])
    series.sort()

    hr = None
    if series:
        values = [bpm for _, bpm in series]
        hr = {"avg": round(sum(values) / len(values)), "max": max(values), "series": series}
    else:
        avg, mx = _qty(w.get("avgHeartRate")), _qty(w.get("maxHeartRate"))
        if avg or mx:
            hr = {"avg": round(avg) if avg else None, "max": round(mx) if mx else None, "series": []}

    kcal = _qty(w.get("activeEnergyBurned") or w.get("activeEnergy"))
    distance_km = _qty(w.get("distance"))

    return records.make_record(
        source_kind="health",
        source_file=str(_repo_rel(source)),
        workout_type=w.get("name") or w.get("workoutActivityType") or "unknown",
        start=start,
        end=end,
        duration_s=_qty(w.get("duration")) * 60 if w.get("duration") else None,
        kcal=round(kcal) if kcal is not None else None,
        distance_m=round(distance_km * 1000) if distance_km is not None else None,
        hr=hr,
    )


def _qty(value) -> float | None:
    """Auto Export wraps numbers as {"qty": x, "units": "..."} in some versions."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("qty")
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
    ap.add_argument("inputs", nargs="*", default=["data/raw/health"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    total = 0
    for inp in args.inputs:
        p = Path(inp)
        files = sorted(p.glob("*.json")) if p.is_dir() else [p] if p.exists() else []
        for f in files:
            total += len(parse_file(f, args.out))
    print(f"auto-export: {total} workouts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
