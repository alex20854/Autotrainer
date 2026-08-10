#!/usr/bin/env python3
"""Apply auto-merge proposals: write canonical session files (spec §7).

Mechanical merging only — field precedence is fixed policy, not judgment:
machine/photo data wins for watts/distance/elapsed structure, Health wins for
HR and timing anchors, every contributing source is recorded. Ambiguous cases
are NOT touched here; Claude resolves those during /coach review and writes
the session files itself.

Usage: python3 scripts/apply_merges.py [--proposals FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import frontmatter, records

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = REPO_ROOT / "data" / "sessions"
PROPOSALS_PATH = REPO_ROOT / "data" / "derived" / "proposals.json"

# Workout type -> session modality (docs/schema.md vocabulary). Covers the
# three type spellings we meet: HK identifiers (export.xml), human names
# (Health Auto Export), and c2-* (parse_c2). Photo machine identification
# (more specific) overrides this when present.
TYPE_TO_MODALITY = {
    "HKWorkoutActivityTypeRowing": "rowerg",
    "HKWorkoutActivityTypeCycling": "bike",
    "HKWorkoutActivityTypeRunning": "run",
    "HKWorkoutActivityTypeWalking": "walk",
    "HKWorkoutActivityTypeHiking": "walk",
    "HKWorkoutActivityTypeStairClimbing": "stairclimber",
    "HKWorkoutActivityTypeStairs": "stairclimber",
    "HKWorkoutActivityTypeClimbing": "versaclimber",
    "HKWorkoutActivityTypeCrossTraining": "mixed",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "mixed",
    "Rowing": "rowerg",
    "Cycling": "bike",
    "Indoor Cycling": "bike",
    "Outdoor Cycling": "bike",
    "Running": "run",
    "Outdoor Run": "run",
    "Indoor Run": "treadmill-run",
    "Walking": "walk",
    "Outdoor Walk": "walk",
    "Indoor Walk": "treadmill-walk",
    "Hiking": "walk",
    "Stair Stepper": "stairclimber",
    "c2-rowerg": "rowerg",
    "c2-rower": "rowerg",
    "c2-skierg": "skierg",
    "c2-bikeerg": "bikeerg",
}
MACHINE_TO_MODALITY = {
    "concept2-rowerg": "rowerg", "concept2-skierg": "skierg",
    "concept2-bikeerg": "bikeerg", "airdyne": "airdyne",
    "stairclimber": "stairclimber", "versaclimber": "versaclimber",
    "exercise-bike": "bike", "treadmill": "treadmill-run",
}


def session_for_case(case: dict) -> tuple[dict, str]:
    w = case["workout"]
    sidecar = None
    if case.get("sidecar"):
        sidecar = yaml.safe_load((REPO_ROOT / case["sidecar"]).read_text(encoding="utf-8"))
    fields = (sidecar or {}).get("fields") or {}

    machine = case.get("machine")
    modality = (MACHINE_TO_MODALITY.get(machine)
                or TYPE_TO_MODALITY.get(w.get("workout_type"), "mixed"))
    date = w["start"][:10]

    sources = [{
        "kind": "health" if w["ref"].split("/")[-1].startswith("health-") else "c2",
        "ref": w["ref"],
        "confidence": "high",
    }]
    # consolidated duplicate/complementary captures: recorded so re-ingest
    # sees them claimed and metrics can read HR + watt series across records
    for co in w.get("co_refs") or []:
        sources.append({"kind": co["kind"], "ref": co["ref"],
                        "confidence": "high", "role": co["role"]})
    if sidecar:
        sources.append({
            "kind": "photo",
            "ref": sidecar["photo"],
            "extraction": case["sidecar"],
            "confidence": sidecar.get("machine_confidence") or "medium",
        })

    def photo_val(name):
        return (fields.get(name) or {}).get("value")

    fm = {
        "id": None,  # filled by caller once the filename is settled
        "date": date,
        "start": w["start"],
        "end": w["end"],
        "modality": modality,
        "machine": machine,
        # monitor is authority for output/distance (spec §5); Health for HR
        "duration_s": photo_val("elapsed_time_s") or w.get("duration_s"),
        "hr_avg": w.get("hr_avg"),
        "hr_max": None,
        "watts_avg": photo_val("watts_avg"),
        "distance_m": photo_val("distance_m") or w.get("distance_m"),
        "kcal": photo_val("kcal") or w.get("kcal"),
        "sources": sources,
        "match_confidence": case.get("confidence", 1.0),
        "match_method": "auto",
        "prescription_id": None,
        "compliance": None,
        "computed": None,
    }
    # hr_max lives in the derived records, not the proposal summary; with
    # consolidated captures, any contributing record may hold the HR data
    for ref in [w["ref"]] + [co["ref"] for co in w.get("co_refs") or []]:
        rec_path = REPO_ROOT / ref
        if rec_path.exists():
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
            if (rec.get("hr") or {}).get("max"):
                fm["hr_max"] = rec["hr"]["max"]
                break

    body = ("_Auto-merged; see sources for provenance._\n"
            if case["kind"] == "pair" else
            "_Single-source session (no photo/trace matched)._\n")
    return fm, body


def write_session(fm: dict, body: str, sessions_dir: Path) -> Path:
    date, modality = fm["date"], fm["modality"]
    year_dir = sessions_dir / date[:4]
    stem = f"{date}-{modality}"
    path = year_dir / f"{stem}.md"
    n = 2
    while path.exists():
        existing, _ = frontmatter.load(path)
        if existing.get("start") == fm["start"]:
            break  # same session re-proposed -> overwrite in place (idempotent)
        path = year_dir / f"{stem}-{n}.md"
        n += 1
    fm["id"] = path.stem
    frontmatter.save(path, fm, body)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--proposals", type=Path, default=PROPOSALS_PATH)
    ap.add_argument("--sessions-dir", type=Path, default=SESSIONS_DIR)
    args = ap.parse_args()
    if not args.proposals.exists():
        print("no proposals file — run propose_matches.py first")
        return 1
    proposals = json.loads(args.proposals.read_text(encoding="utf-8"))
    written = []
    for case in proposals.get("auto_merge", []):
        fm, body = session_for_case(case)
        written.append(write_session(fm, body, args.sessions_dir))
    print(f"apply_merges: {len(written)} session files written, "
          f"{len(proposals.get('ambiguous', []))} ambiguous left for /coach review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
