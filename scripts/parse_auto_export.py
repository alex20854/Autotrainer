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
        duration_s=_duration_s(_qty(w.get("duration")), start, end),
        kcal=round(kcal) if kcal is not None else None,
        distance_m=round(distance_km * 1000) if distance_km is not None else None,
        hr=hr,
    )


def _duration_s(value: float | None, start: str, end: str) -> float | None:
    """The app's duration unit varies by version (minutes or seconds).
    The two readings differ by 60x, so pick the one closer to the wall-clock
    span — unambiguous for any workout longer than a minute."""
    if value is None:
        return None
    span = (records.parse_dt(end) - records.parse_dt(start)).total_seconds()
    as_minutes, as_seconds = value * 60, value
    return as_minutes if abs(as_minutes - span) <= abs(as_seconds - span) else as_seconds


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


# Daily health metrics worth keeping (recovery + estimation signals). The
# exports carry dozens; this whitelist is the deliberate, reviewable choice.
METRIC_WHITELIST = {"resting_heart_rate", "vo2_max", "heart_rate_variability"}
METRICS_PATH = records.REPO_ROOT / "data" / "derived" / "metrics.jsonl"


def parse_metrics(files: list[Path], out_path: Path = METRICS_PATH) -> int:
    """Upsert whitelisted daily metrics into data/derived/metrics.jsonl.
    Merge (not rebuild): old raw exports may be gone, but their points stay."""
    points: dict[tuple[str, str], dict] = {}
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            pt = json.loads(line)
            points[(pt["date"], pt["name"])] = pt
    for f in files:
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for metric in (payload.get("data") or {}).get("metrics") or []:
            if metric.get("name") not in METRIC_WHITELIST:
                continue
            for pt in metric.get("data") or []:
                value = _qty(pt.get("qty") if "qty" in pt else pt.get("Avg", pt.get("avg")))
                date = str(pt.get("date"))[:10]
                if value is None or len(date) != 10:
                    continue
                points[(date, metric["name"])] = {
                    "date": date, "name": metric["name"],
                    "value": round(value, 1), "units": metric.get("units"),
                }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for key in sorted(points):
            f.write(json.dumps(points[key], separators=(",", ":")) + "\n")
    return len(points)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="*", default=["data/raw/health"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    total, all_files = 0, []
    for inp in args.inputs:
        p = Path(inp)
        files = sorted(p.glob("*.json")) if p.is_dir() else [p] if p.exists() else []
        all_files.extend(files)
        for f in files:
            total += len(parse_file(f, args.out))
    n_metrics = parse_metrics(all_files)
    print(f"auto-export: {total} workouts, {n_metrics} daily metric points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
