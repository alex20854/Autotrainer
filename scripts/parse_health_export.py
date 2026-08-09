#!/usr/bin/env python3
"""Backfill parser: Apple Health export.xml -> derived workout records.

export.xml can be hundreds of MB, so this streams with xml.etree.iterparse and
never builds the full tree. Strategy: one pass collecting Workout elements and
buffering only HeartRate records, then clipping each workout's HR samples to
its [start, end] window. Cardio-irrelevant workout types are kept too — the
proposal script decides relevance; parsers don't filter by judgment.

Idempotent: record ids derive from (source, start, type), so re-running over a
newer export overwrites in place.

Usage: python3 scripts/parse_health_export.py [export.xml] [--out DIR]
       (default input: data/raw/health/export.xml)
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from bisect import bisect_left, bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import records

HR_TYPE = "HKQuantityTypeIdentifierHeartRate"


def parse_export(xml_path: Path, out_dir: Path | None = None) -> list[dict]:
    workouts = []
    hr_samples = []  # (datetime, bpm) — export.xml is roughly chronological; sorted below

    # Clear only fully-processed top-level elements (a Workout's
    # WorkoutStatistics children must survive until the Workout's own end
    # event), and prune the accumulating root so memory stays flat on 500MB files.
    context = ET.iterparse(str(xml_path), events=("start", "end"))
    _, root = next(context)
    for event, elem in context:
        if event != "end":
            continue
        if elem.tag == "Record":
            if elem.get("type") == HR_TYPE:
                try:
                    hr_samples.append(
                        (records.parse_dt(elem.get("startDate")), float(elem.get("value")))
                    )
                except (TypeError, ValueError):
                    pass
            elem.clear()
            root.clear()
        elif elem.tag == "Workout":
            workouts.append(_workout_attrs(elem))
            elem.clear()
            root.clear()

    hr_samples.sort(key=lambda s: s[0])
    hr_times = [s[0] for s in hr_samples]

    out = []
    for w in workouts:
        start_dt, end_dt = records.parse_dt(w["start"]), records.parse_dt(w["end"])
        lo, hi = bisect_left(hr_times, start_dt), bisect_right(hr_times, end_dt)
        series = [
            [round((t - start_dt).total_seconds()), round(bpm)]
            for t, bpm in hr_samples[lo:hi]
        ]
        hr = None
        if series:
            values = [bpm for _, bpm in series]
            hr = {"avg": round(sum(values) / len(values)), "max": max(values), "series": series}
        rec = records.make_record(
            source_kind="health",
            source_file=str(_repo_rel(xml_path)),
            workout_type=w["type"],
            start=w["start"],
            end=w["end"],
            duration_s=w["duration_s"],
            kcal=w["kcal"],
            distance_m=w["distance_m"],
            hr=hr,
        )
        records.save_record(rec, out_dir)
        out.append(rec)
    return out


def _workout_attrs(elem: ET.Element) -> dict:
    duration = elem.get("duration")
    unit = (elem.get("durationUnit") or "min").lower()
    duration_s = None
    if duration:
        duration_s = float(duration) * (60 if unit == "min" else 1)
    kcal = distance = None
    # Modern exports carry energy/distance as child WorkoutStatistics
    for stat in elem.findall("WorkoutStatistics"):
        stype, total = stat.get("type", ""), stat.get("sum")
        if total is None:
            continue
        if "ActiveEnergyBurned" in stype:
            kcal = float(total)
        elif "Distance" in stype:
            distance = _to_meters(float(total), stat.get("unit") or "m")
    # Legacy attribute fallbacks
    if kcal is None and elem.get("totalEnergyBurned"):
        kcal = float(elem.get("totalEnergyBurned"))
    if distance is None and elem.get("totalDistance"):
        distance = _to_meters(float(elem.get("totalDistance")), elem.get("totalDistanceUnit") or "m")
    return {
        "type": elem.get("workoutActivityType", "unknown"),
        "start": _iso(elem.get("startDate")),
        "end": _iso(elem.get("endDate")),
        "duration_s": duration_s,
        "kcal": round(kcal) if kcal is not None else None,
        "distance_m": round(distance) if distance is not None else None,
    }


def _to_meters(value: float, unit: str) -> float:
    return value * {"km": 1000, "mi": 1609.344, "m": 1, "yd": 0.9144}.get(unit, 1)


def _iso(apple_ts: str) -> str:
    return records.parse_dt(apple_ts).isoformat()


def _repo_rel(path: Path) -> Path:
    try:
        return path.resolve().relative_to(records.REPO_ROOT)
    except ValueError:
        return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xml", nargs="?", default="data/raw/health/export.xml")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    xml_path = Path(args.xml)
    if not xml_path.exists():
        print(f"no export at {xml_path} — nothing to do")
        return 0
    recs = parse_export(xml_path, args.out)
    with_hr = sum(1 for r in recs if r["hr"])
    print(f"export.xml: {len(recs)} workouts ({with_hr} with HR series)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
