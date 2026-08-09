#!/usr/bin/env python3
"""Rebuild data/index.jsonl from session frontmatter.

The index is derived, never hand-edited (spec §6). One JSON line per session,
sorted by (date, start), so Claude can answer whole-history questions without
opening hundreds of files.

Usage: python3 scripts/build_index.py [--strict]
  --strict  validate frontmatter against the schema contract and exit non-zero
            on any violation (used by tests and CI-of-one).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import frontmatter

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = REPO_ROOT / "data" / "sessions"
INDEX_PATH = REPO_ROOT / "data" / "index.jsonl"

REQUIRED = ["id", "date", "modality", "duration_s", "sources", "match_confidence"]
MODALITIES = {
    "rowerg", "skierg", "bikeerg", "airdyne", "stairclimber", "versaclimber",
    "bike", "treadmill-run", "treadmill-walk", "run", "sled", "mixed",
}
SOURCE_KINDS = {"health", "photo", "c2", "user"}


def validate(fm: dict, path: Path) -> list[str]:
    errors = []
    for field in REQUIRED:
        if fm.get(field) is None:
            errors.append(f"{path}: missing required field '{field}'")
    if fm.get("id") and fm["id"] != path.stem:
        errors.append(f"{path}: id '{fm['id']}' != filename stem '{path.stem}'")
    if fm.get("modality") and fm["modality"] not in MODALITIES:
        errors.append(f"{path}: unknown modality '{fm['modality']}'")
    for src in fm.get("sources") or []:
        if src.get("kind") not in SOURCE_KINDS:
            errors.append(f"{path}: unknown source kind '{src.get('kind')}'")
    mc = fm.get("match_confidence")
    if mc is not None and not (0 <= mc <= 1):
        errors.append(f"{path}: match_confidence {mc} outside [0,1]")
    return errors


def index_line(fm: dict, path: Path) -> dict:
    compliance = fm.get("compliance") or {}
    computed = fm.get("computed") or {}
    tiz = computed.get("time_in_zone") or {}
    return {
        "id": fm.get("id"),
        "date": str(fm.get("date")),
        "start": fm.get("start"),
        "modality": fm.get("modality"),
        "machine": fm.get("machine"),
        "duration_s": fm.get("duration_s"),
        "hr_avg": fm.get("hr_avg"),
        "hr_max": fm.get("hr_max"),
        "watts_avg": fm.get("watts_avg"),
        "distance_m": fm.get("distance_m"),
        "kcal": fm.get("kcal"),
        "source_kinds": [s.get("kind") for s in fm.get("sources") or []],
        "match_confidence": fm.get("match_confidence"),
        "prescription_id": fm.get("prescription_id"),
        "tier": compliance.get("tier"),
        "compliance_score": compliance.get("score"),
        "tiz_z2_s": tiz.get("z2"),
        "decoupling_pct": computed.get("decoupling_pct"),
        "efficiency_factor": computed.get("efficiency_factor"),
        "file": _repo_rel(path),
    }


def _repo_rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:  # outside the repo (tests)
        return str(path)


def build(sessions_dir: Path = SESSIONS_DIR, index_path: Path = INDEX_PATH,
          strict: bool = False) -> tuple[int, list[str]]:
    entries, errors = [], []
    for path in sorted(sessions_dir.rglob("*.md")):
        try:
            fm, _ = frontmatter.load(path)
        except frontmatter.FrontmatterError as e:
            errors.append(f"{path}: {e}")
            continue
        errors.extend(validate(fm, path))
        entries.append(index_line(fm, path))
    entries.sort(key=lambda e: (e["date"], e["start"] or ""))
    if not (strict and errors):
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    return len(entries), errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="fail on schema violations")
    args = ap.parse_args()
    count, errors = build(strict=args.strict)
    for err in errors:
        print(err, file=sys.stderr)
    if args.strict and errors:
        return 1
    print(f"index.jsonl: {count} sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
