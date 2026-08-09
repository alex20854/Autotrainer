"""Derived workout records — the normalized format all sources feed (schema.md).

A record is a plain dict persisted as JSON in data/derived/workouts/. The
record_id is deterministic (source kind + start + type slug) so re-running any
parser over the same raw data overwrites the same files: ingest is idempotent.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKOUTS_DIR = REPO_ROOT / "data" / "derived" / "workouts"

FIELDS = [
    "record_id", "source_kind", "source_file", "workout_type",
    "start", "end", "duration_s", "kcal", "distance_m",
    "hr", "splits", "watts",
]


def slugify(value: str) -> str:
    value = re.sub(r"^HKWorkoutActivityType", "", value or "unknown")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return value or "unknown"


def record_id(source_kind: str, start: str, workout_type: str) -> str:
    ts = re.sub(r"[:]", "", start[:19]).replace("T", "T")
    return f"{source_kind}-{ts}-{slugify(workout_type)}"


def make_record(*, source_kind: str, source_file: str, workout_type: str,
                start: str, end: str, duration_s: float | None = None,
                kcal: float | None = None, distance_m: float | None = None,
                hr: dict | None = None, splits: list | None = None,
                watts: list | None = None) -> dict:
    if duration_s is None:
        duration_s = (parse_dt(end) - parse_dt(start)).total_seconds()
    return {
        "record_id": record_id(source_kind, start, workout_type),
        "source_kind": source_kind,
        "source_file": source_file,
        "workout_type": workout_type,
        "start": start,
        "end": end,
        "duration_s": round(duration_s),
        "kcal": kcal,
        "distance_m": distance_m,
        "hr": hr,
        "splits": splits,
        "watts": watts,
    }


def parse_dt(value: str) -> datetime:
    """Parse the timestamp formats we meet: RFC3339 and Apple's 'YYYY-MM-DD HH:MM:SS -0400'."""
    value = value.strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) ([+-]\d{4})$", value)
    if m:
        value = f"{m.group(1)}T{m.group(2)}{m.group(3)[:3]}:{m.group(3)[3:]}"
    return datetime.fromisoformat(value)


def save_record(record: dict, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or WORKOUTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{record['record_id']}.json"
    path.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def load_records(records_dir: Path | None = None) -> list[dict]:
    records_dir = records_dir or WORKOUTS_DIR
    records = []
    if records_dir.is_dir():
        for path in sorted(records_dir.glob("*.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))
    return records
