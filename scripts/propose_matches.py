#!/usr/bin/env python3
"""Reconciliation proposals: pair evidence into session candidates (spec §7).

Deterministic candidate generation only — this script proposes, it never
decides ambiguity. Output is data/derived/proposals.json:

  auto_merge[]   confidence >= 0.9 multi-source pairs and clean single-source
                 records -> apply_merges.py writes these session files
  ambiguous[]    everything else, each with an evidence summary Claude presents
                 conversationally during /coach review

Rules (config/athlete.yaml `matching:`):
  - photo EXIF within [workout start, workout end + photo_window_after_end_s]
  - |photo elapsed - workout duration| <= duration_tolerance_s
  - modality_map lookup mismatch LOWERS confidence, never hard-fails

Records already referenced by an existing session file are skipped, so re-runs
after ingest are no-ops (idempotent).

Usage: python3 scripts/propose_matches.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import records
from lib import sessions as sessions_lib

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = REPO_ROOT / "data" / "sessions"
SIDECAR_DIR = REPO_ROOT / "data" / "derived" / "photos"
PROPOSALS_PATH = REPO_ROOT / "data" / "derived" / "proposals.json"
CONFIG_PATH = REPO_ROOT / "config" / "athlete.yaml"

AUTO_MERGE_THRESHOLD = 0.9

# Health workout types that are not cardio sessions for this system; kept in
# derived records but excluded from proposals (mechanical filter, listed here
# so changing it is a visible, reviewable decision).
NON_CARDIO_TYPES = {
    "HKWorkoutActivityTypeTraditionalStrengthTraining",
    "HKWorkoutActivityTypeFunctionalStrengthTraining",
    "HKWorkoutActivityTypeYoga",
    "HKWorkoutActivityTypeFlexibility",
    "HKWorkoutActivityTypeMindAndBody",
    # Health Auto Export human-readable spellings
    "Strength Training",
    "Traditional Strength Training",
    "Functional Strength Training",
    "Yoga",
    "Flexibility",
}


already_claimed = sessions_lib.already_claimed
load_sessions = sessions_lib.load_sessions


def load_sidecars(sidecar_dir: Path) -> list[dict]:
    sidecars = []
    for path in sorted(sidecar_dir.glob("*.yaml")):
        sc = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            sc["_sidecar_path"] = str(path.relative_to(REPO_ROOT))
        except ValueError:  # outside the repo (tests)
            sc["_sidecar_path"] = str(path)
        sidecars.append(sc)
    return sidecars


def score_pair(workout: dict, sidecar: dict, matching: dict) -> tuple[float, list[str]]:
    """Confidence in [0,1] plus human-readable evidence notes."""
    notes = []
    start = records.parse_dt(workout["start"])
    end = records.parse_dt(workout["end"])
    exif = sidecar.get("exif_time")
    if not exif:
        return 0.0, ["photo has no EXIF timestamp"]
    photo_dt = datetime.fromisoformat(exif)
    if photo_dt.tzinfo is None and start.tzinfo is not None:
        photo_dt = photo_dt.replace(tzinfo=start.tzinfo)  # EXIF is local time

    window_end_s = matching.get("photo_window_after_end_s", 600)
    if not (start <= photo_dt <= end + _td(window_end_s)):
        return 0.0, [f"photo time {exif} outside workout window"]
    gap = (photo_dt - end).total_seconds()
    notes.append(f"photo taken {round(gap)}s after workout end" if gap >= 0
                 else f"photo taken {round(-gap)}s before workout end")
    confidence = 0.75

    # duration cross-check, when the photo has an extracted elapsed time
    elapsed = ((sidecar.get("fields") or {}).get("elapsed_time_s") or {}).get("value")
    tolerance = matching.get("duration_tolerance_s", 90)
    if elapsed and workout.get("duration_s"):
        diff = abs(elapsed - workout["duration_s"])
        if diff <= tolerance:
            confidence += 0.15
            notes.append(f"durations agree (Δ{round(diff)}s)")
        else:
            confidence -= 0.30
            notes.append(f"durations disagree (Δ{round(diff)}s > {tolerance}s)")

    # modality consistency: lowers confidence, never hard-fails (spec §7)
    machine = sidecar.get("machine")
    modality_map = matching.get("modality_map") or {}
    if machine and workout.get("workout_type"):
        expected = modality_map.get(machine) or []
        if workout["workout_type"] in expected:
            confidence += 0.10
            notes.append(f"modality consistent ({machine} → {workout['workout_type']})")
        elif expected:
            confidence -= 0.15
            notes.append(f"modality unusual ({machine} vs {workout['workout_type']}) — "
                         "if merged, /coach review should add this pairing to modality_map")
    return max(0.0, min(1.0, round(confidence, 2))), notes


def _td(seconds: float):
    from datetime import timedelta
    return timedelta(seconds=seconds)


consolidate_records = records.consolidate_records


def overlapping_session(workout: dict, sessions: list[dict], slack_s: float = 900) -> dict | None:
    """First existing session whose time range overlaps this workout record.
    Happens routinely: a photo-only session exists, then the Health export
    arrives late (spec §5) — the record must ATTACH, not become a duplicate."""
    w_start, w_end = records.parse_dt(workout["start"]), records.parse_dt(workout["end"])
    for s in sessions:
        s_start, s_end = records.parse_dt(s["start"]), records.parse_dt(s["end"])
        if w_start.tzinfo is None:
            w_start = w_start.replace(tzinfo=s_start.tzinfo)
            w_end = w_end.replace(tzinfo=s_start.tzinfo)
        if s_start.tzinfo is None:
            s_start = s_start.replace(tzinfo=w_start.tzinfo)
            s_end = s_end.replace(tzinfo=w_start.tzinfo)
        if w_start <= s_end + _td(slack_s) and s_start <= w_end + _td(slack_s):
            return s
    return None


def propose(workouts: list[dict], sidecars: list[dict], claimed: set[str],
            matching: dict, sessions: list[dict] | None = None,
            classification: dict | None = None) -> dict:
    workouts = [
        w for w in workouts
        if w["workout_type"] not in NON_CARDIO_TYPES
        and f"data/derived/workouts/{w['record_id']}.json" not in claimed
    ]
    workouts = consolidate_records(workouts)
    sidecars = [s for s in sidecars if s["_sidecar_path"] not in claimed
                and s.get("extracted")]

    # score all cross pairs
    pair_scores = []
    for w in workouts:
        for s in sidecars:
            conf, notes = score_pair(w, s, matching)
            if conf > 0:
                pair_scores.append({"workout": w, "sidecar": s,
                                    "confidence": conf, "evidence": notes})
    pair_scores.sort(key=lambda p: -p["confidence"])

    # Precision beats recall (spec §7: >=95% precision on auto-merges). A pair
    # auto-merges only when it clears the threshold AND neither side has any
    # other viable pairing — contested evidence always goes to Claude.
    viable_w, viable_s = {}, {}
    for pair in pair_scores:
        if pair["confidence"] >= 0.5:
            viable_w.setdefault(pair["workout"]["record_id"], []).append(pair)
            viable_s.setdefault(pair["sidecar"]["_sidecar_path"], []).append(pair)

    # Classify: baseline-type records (casual walks and the like) belong to the
    # weekly baseline rollup (build_baseline.py), not the session ledger —
    # UNLESS something marks them deliberate training: duration >= the
    # promotion threshold, or a viable photo pairing. Nothing is dropped;
    # whatever is routed away here is picked up by the rollup.
    cls = classification or {}
    baseline_types = set(cls.get("baseline_types") or [])
    promote_s = cls.get("promote_min_duration_s", 1800)
    baseline_routed = sorted(
        w["record_id"] for w in workouts
        if w["workout_type"] in baseline_types
        and (w.get("duration_s") or 0) < promote_s
        and w["record_id"] not in viable_w
    )
    demoted = set(baseline_routed)
    workouts = [w for w in workouts if w["record_id"] not in demoted]
    pair_scores = [p for p in pair_scores if p["workout"]["record_id"] not in demoted]

    auto, ambiguous, used_w, used_s = [], [], set(), set()
    for pair in pair_scores:
        wid = pair["workout"]["record_id"]
        sid = pair["sidecar"]["_sidecar_path"]
        if wid in used_w or sid in used_s:
            if pair["confidence"] >= 0.5:
                # keep the full picture in front of Claude: this is the losing
                # alternative of a contested entity, not an orphan
                ambiguous.append(_case(pair, "alternative pairing for contested evidence"))
                used_w.add(wid)
                used_s.add(sid)
            continue
        used_w.add(wid)
        used_s.add(sid)
        contested = len(viable_w.get(wid, [])) > 1 or len(viable_s.get(sid, [])) > 1
        if contested:
            ambiguous.append(_case(pair, "evidence contested — another viable pairing exists"))
        elif pair["confidence"] >= AUTO_MERGE_THRESHOLD:
            auto.append(_case(pair))
        else:
            ambiguous.append(_case(pair, "confidence below auto-merge threshold"))

    # unmatched workouts become single-source sessions — first-class (spec §7) —
    # unless they overlap an existing session (late-arriving source): those go
    # to Claude as attach cases, never as duplicate sessions
    for w in workouts:
        if w["record_id"] not in used_w:
            existing = overlapping_session(w, sessions or [])
            if existing:
                ambiguous.append({
                    "kind": "attach_to_session",
                    "workout": _workout_summary(w),
                    "session_id": existing["id"],
                    "confidence": None,
                    "evidence": [f"workout overlaps existing session {existing['id']} "
                                 f"({existing['start']}–{existing['end']}) — "
                                 "likely a late-arriving source for the same training"],
                })
                continue
            auto.append({
                "kind": "single_source",
                "workout": _workout_summary(w),
                "confidence": 1.0,
                "evidence": ["no matching photo/trace; Health-only session"],
            })
    # unmatched extracted photos need Claude (forgot-the-Watch case)
    for s in sidecars:
        if s["_sidecar_path"] not in used_s:
            ambiguous.append({
                "kind": "orphan_photo",
                "sidecar": s["_sidecar_path"],
                "machine": s.get("machine"),
                "exif_time": s.get("exif_time"),
                "confidence": None,
                "evidence": ["photo matches no Health workout — photo-only session, "
                             "wrong-day photo, or non-workout shot"],
            })
    return {"auto_merge": auto, "ambiguous": ambiguous,
            "baseline_routed": baseline_routed}


def _case(pair: dict, reason: str | None = None) -> dict:
    case = {
        "kind": "pair",
        "workout": _workout_summary(pair["workout"]),
        "sidecar": pair["sidecar"]["_sidecar_path"],
        "machine": pair["sidecar"].get("machine"),
        "confidence": pair["confidence"],
        "evidence": pair["evidence"],
    }
    if reason:
        case["reason"] = reason
    return case


def _workout_summary(w: dict) -> dict:
    return {k: w.get(k) for k in ("record_id", "workout_type", "start", "end",
                                  "duration_s", "kcal", "distance_m")} | {
        "hr_avg": (w.get("hr") or {}).get("avg"),
        "ref": f"data/derived/workouts/{w['record_id']}.json",
        "co_refs": w.get("co_refs") or [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workouts-dir", type=Path, default=records.WORKOUTS_DIR)
    ap.add_argument("--out", type=Path, default=PROPOSALS_PATH)
    args = ap.parse_args()

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    matching = config.get("matching") or {}
    classification = config.get("classification") or {}
    workouts = records.load_records(args.workouts_dir)
    sidecars = load_sidecars(SIDECAR_DIR) if SIDECAR_DIR.is_dir() else []
    claimed = already_claimed(SESSIONS_DIR)
    sessions = load_sessions(SESSIONS_DIR)

    proposals = propose(workouts, sidecars, claimed, matching, sessions, classification)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(proposals, indent=1) + "\n", encoding="utf-8")
    print(f"proposals: {len(proposals['auto_merge'])} auto-merge, "
          f"{len(proposals['ambiguous'])} ambiguous, "
          f"{len(proposals['baseline_routed'])} records -> baseline rollup "
          f"-> {args.out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
