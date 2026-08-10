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


# ---------------------------------------------------------------- consolidation

OVERLAP_FRACTION = 0.5  # records sharing >=50% of the shorter one's time are the same bout


def _overlap_s(a: dict, b: dict) -> float:
    a_s, a_e = parse_dt(a["start"]), parse_dt(a["end"])
    b_s, b_e = parse_dt(b["start"]), parse_dt(b["end"])
    if a_s.tzinfo is None and b_s.tzinfo is not None:
        a_s, a_e = a_s.replace(tzinfo=b_s.tzinfo), a_e.replace(tzinfo=b_s.tzinfo)
    if b_s.tzinfo is None and a_s.tzinfo is not None:
        b_s, b_e = b_s.replace(tzinfo=a_s.tzinfo), b_e.replace(tzinfo=a_s.tzinfo)
    return (min(a_e, b_e) - max(a_s, b_s)).total_seconds()


def _same_bout(a: dict, b: dict) -> bool:
    shorter = min(a.get("duration_s") or 0, b.get("duration_s") or 0)
    return shorter > 0 and _overlap_s(a, b) >= OVERLAP_FRACTION * shorter


def _richness(w: dict) -> tuple:
    hr = w.get("hr") or {}
    return (len(hr.get("series") or []), 1 if hr else 0,
            sum(x is not None for x in (w.get("kcal"), w.get("distance_m"))))


def consolidate_records(workouts: list[dict]) -> list[dict]:
    """Collapse records that capture the SAME training bout (deterministic).

    The same workout legitimately arrives multiple times: export.xml backfill
    AND Health Auto Export (different type spellings, timestamps off by
    seconds), Watch AND iPhone, Health AND a C2 trace. Same source kind ->
    duplicate captures: keep the richest (longest HR series), carry the rest
    as role=duplicate refs. Different kinds -> complementary evidence: one
    merged entry, machine record winning duration/distance/watts and Health
    winning HR/kcal/timing (spec §5). Future telemetry parsers get this merge
    for free by emitting normalized records.
    """
    groups: list[list[dict]] = []
    for w in sorted(workouts, key=lambda w: w["start"]):
        for group in groups:
            if any(_same_bout(w, other) for other in group):
                group.append(w)
                break
        else:
            groups.append([w])

    out = []
    for group in groups:
        if len(group) == 1:
            out.append(group[0])
            continue
        best_by_kind: dict[str, dict] = {}
        for w in group:
            best = best_by_kind.get(w["source_kind"])
            if best is None or _richness(w) > _richness(best):
                best_by_kind[w["source_kind"]] = w
        machine, health = best_by_kind.get("c2"), best_by_kind.get("health")
        primary = machine or health or group[0]
        merged = dict(primary)
        if machine and health:
            # Health anchors absolute timing + HR; machine keeps output fields
            merged["start"], merged["end"] = health["start"], health["end"]
            merged["hr"] = health.get("hr")
            if merged.get("kcal") is None:
                merged["kcal"] = health.get("kcal")
        merged["co_refs"] = [
            {"kind": w["source_kind"],
             "ref": f"data/derived/workouts/{w['record_id']}.json",
             "role": "complement" if w["source_kind"] != primary["source_kind"] else "duplicate"}
            for w in group if w["record_id"] != primary["record_id"]
        ]
        out.append(merged)
    return out
