#!/usr/bin/env python3
"""Compute per-session metrics from derived workout records.

Fixed math only (spec §2): time-in-zone, decoupling (Pw:HR), efficiency factor,
and bout detection for Tier 2 structure. Results go into each session's
`computed:` frontmatter block; HR series never leave the derived records.

Zone bands come from config/athlete.yaml. With no LTHR/HRmax configured the
session is marked zones_source: unconfigured and time-in-zone is skipped —
scripts never guess anchors (that's a /coach setup conversation).

Usage: python3 scripts/compute_metrics.py [session.md ...]   (default: all sessions)
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
CONFIG_PATH = REPO_ROOT / "config" / "athlete.yaml"


# ---------------------------------------------------------------- pure math

def zone_bounds(config: dict) -> tuple[dict[str, tuple[float, float]], str] | tuple[None, str]:
    """Resolve HR zone bands (bpm) from athlete config. Returns (bands, source)."""
    athlete = config.get("athlete") or {}
    zones = config.get("zones") or {}
    bands = zones.get("bands") or {}
    lthr, hr_max = athlete.get("lthr"), athlete.get("hr_max")
    if lthr:
        anchor, source = lthr, "lthr"
    elif hr_max:
        # bootstrap fallback: approximate LTHR as 90% HRmax so the same
        # pct_lthr bands apply; flagged so Claude reports it as provisional
        anchor, source = hr_max * 0.90, "bootstrap"
    else:
        return None, "unconfigured"
    return (
        {z: (lo * anchor, hi * anchor) for z, (lo, hi) in bands.items()},
        source,
    )


def time_in_zone(series: list[list[float]], bands: dict[str, tuple[float, float]]) -> dict[str, int]:
    """Seconds per zone. Each sample covers the gap to the next sample (capped
    at 30 s so sparse recordings don't invent zone time)."""
    tiz = {z: 0.0 for z in bands}
    for i, (t, bpm) in enumerate(series):
        dt = min(series[i + 1][0] - t, 30) if i + 1 < len(series) else 5
        for z, (lo, hi) in bands.items():
            if lo <= bpm < hi:
                tiz[z] += dt
                break
    return {z: round(v) for z, v in tiz.items()}


def efficiency_factor(watts_avg: float | None, hr_avg: float | None) -> float | None:
    if not watts_avg or not hr_avg:
        return None
    return round(watts_avg / hr_avg, 2)


def decoupling_pct(hr_series: list[list[float]], watt_series: list[list[float]] | None,
                   duration_s: float) -> float | None:
    """Pw:HR drift: efficiency (output/HR) in the first half vs the second.
    With no watt series, falls back to pure HR drift (HR2/HR1 - 1), which is
    valid for steady constant-output work — the caller only computes this for
    sessions, and Claude only *interprets* it for steady-state prescriptions."""
    if len(hr_series) < 10 or duration_s <= 0:
        return None
    half = duration_s / 2
    hr1 = _mean([b for t, b in hr_series if t < half])
    hr2 = _mean([b for t, b in hr_series if t >= half])
    if not hr1 or not hr2:
        return None
    if watt_series and len(watt_series) >= 2:
        w1 = _mean([w for t, w in watt_series if t < half])
        w2 = _mean([w for t, w in watt_series if t >= half])
        if not w1 or not w2:
            return None
        ef1, ef2 = w1 / hr1, w2 / hr2
        drift = (ef1 - ef2) / ef1
    else:
        drift = (hr2 - hr1) / hr1
    return round(drift * 100, 1)


def detect_bouts(series: list[list[float]], threshold: float,
                 min_bout_s: float = 60) -> list[dict]:
    """Threshold-crossing segmentation over a [t, value] series (watts or HR).
    Returns [{start_s, end_s, avg}] for excursions above threshold lasting at
    least min_bout_s. Deterministic structure evidence for Tier 2 — judging
    whether the bouts match the prescription stays with Claude."""
    bouts, current = [], None
    for t, v in series:
        if v >= threshold:
            if current is None:
                current = {"start_s": t, "values": []}
            current["values"].append(v)
            current["end_s"] = t
        elif current is not None:
            _close_bout(bouts, current, min_bout_s)
            current = None
    if current is not None:
        _close_bout(bouts, current, min_bout_s)
    return bouts


def _close_bout(bouts: list, current: dict, min_bout_s: float) -> None:
    if current["end_s"] - current["start_s"] >= min_bout_s:
        bouts.append({
            "start_s": round(current["start_s"]),
            "end_s": round(current["end_s"]),
            "avg": round(_mean(current["values"]), 1),
        })


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


# ------------------------------------------------------------- session glue

def compute_for_session(session_path: Path, config: dict,
                        workouts_dir: Path | None = None) -> dict | None:
    fm, _ = frontmatter.load(session_path)
    hr_series, watt_series = [], []
    for src in fm.get("sources") or []:
        ref = src.get("ref") or ""
        if not ref.startswith("data/derived/workouts/"):
            continue
        rec_path = (workouts_dir or records.WORKOUTS_DIR) / Path(ref).name
        if not rec_path.exists():
            continue
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        if (rec.get("hr") or {}).get("series"):
            hr_series = rec["hr"]["series"]
        if rec.get("watts") and len(rec["watts"]) > 1:
            watt_series = rec["watts"]

    duration = fm.get("duration_s") or 0
    computed: dict = {}
    bands, zones_source = zone_bounds(config)
    if hr_series:
        if bands:
            computed["time_in_zone"] = time_in_zone(hr_series, bands)
        computed["zones_source"] = zones_source
        dec = decoupling_pct(hr_series, watt_series or None, duration)
        if dec is not None:
            computed["decoupling_pct"] = dec
    ef = efficiency_factor(fm.get("watts_avg"), fm.get("hr_avg"))
    if ef is not None:
        computed["efficiency_factor"] = ef
    if watt_series:
        watt_values = [w for _, w in watt_series]
        avg_w = _mean(watt_values)
        bouts = detect_bouts(watt_series, threshold=avg_w * 1.15, min_bout_s=60)
        if bouts:
            computed["bouts"] = len(bouts)

    if not computed:
        return None
    frontmatter.update(session_path, {"computed": computed})
    return computed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sessions", nargs="*", help="session files (default: all)")
    args = ap.parse_args()
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    paths = [Path(s) for s in args.sessions] or sorted(SESSIONS_DIR.rglob("*.md"))
    done = 0
    for path in paths:
        if compute_for_session(path, config) is not None:
            done += 1
    print(f"metrics: computed for {done}/{len(paths)} sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
