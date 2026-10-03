#!/usr/bin/env python3
"""Compute per-session metrics from derived workout records.

Fixed math only (spec §2): time-in-zone, decoupling (Pw:HR) or HR drift,
efficiency factor, and bout detection for Tier 2 structure. Results go into
each session's `computed:` frontmatter block; HR series never leave the
derived records.

Zone bands come from config/athlete.yaml. With no LTHR/HRmax configured the
session is marked zones_source: unconfigured and time-in-zone is skipped —
scripts never guess anchors (that's a /coach setup conversation).

Decoupling is measured only for steady-capable modalities, after a warm-up,
over a minimum window (config `metrics:`, engine defaults below), and not when
a watts series shows work bouts inside that window. Each value says how it
was measured: `pw_hr` (power:HR, needs a watts series covering both halves)
or `hr_drift` (heart rate alone — meaningful only if output was held
constant, which can't be checked without a power trace).

Usage: python3 scripts/compute_metrics.py [session.md ...]   (default: all sessions)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import frontmatter, records
from lib import workspace
from build_index import MODALITIES

REPO_ROOT = workspace.root()
SESSIONS_DIR = REPO_ROOT / "data" / "sessions"
CONFIG_PATH = REPO_ROOT / "config" / "athlete.yaml"

# Decoupling settings — engineering defaults, not a cited standard. Overridden
# per workspace by config/athlete.yaml `metrics:`. The warm-up is skipped
# because HR is still climbing toward steady state there; the minimum window
# keeps short pieces from reporting a "durability" number they can't support.
METRICS_DEFAULTS = {
    "decoupling_warmup_s": 600,
    "decoupling_min_window_s": 1200,
    # every vocabulary modality except those with no steady output to hold
    "decoupling_modalities": sorted(MODALITIES - {"walk", "treadmill-walk", "sled", "mixed"}),
}
# Integer-percent band tables leave 0.01 gaps ("85-89%", "90-94%"); those are
# closed silently. Anything wider, or an overlap, is probably a config typo.
ROUNDING_GAP = 0.011
MIN_HALF_SAMPLES = 5
# A sample covers the gap to the next one, up to this cap (time-in-zone). The
# same cap decides whether an HR trace "reaches" the session's end.
HR_GAP_CAP_S = 30
# pw_hr needs watts covering at least this share of each half, else the value
# falls back to hr_drift — engineering default, not a cited standard.
MIN_WATTS_COVERAGE = 0.9
# Bout detection (Tier 2 structure; also the decoupling steadiness gate):
# excursions above 1.15 x average watts lasting 60 s+ — heuristic.
BOUT_THRESHOLD_RATIO = 1.15
MIN_BOUT_S = 60

_warned: set[str] = set()


def _warn_once(msg: str) -> None:
    if msg not in _warned:
        _warned.add(msg)
        print(f"compute_metrics: warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------- pure math

def resolve_bands(bands: dict) -> tuple[dict[str, tuple[float, float]], list[str]]:
    """Make configured zone bands contiguous. Zones are sorted by lower bound;
    each runs from its own lower bound up to (not including) the next zone's
    lower bound, and the top zone is open-ended. Lower bounds never change.

    This is the faithful reading of integer-percent tables — "z2 85-89%,
    z3 90-94%" means z2 is everything from 85% up to 90% — not a new coaching
    choice: read literally, [0.85, 0.89) and [0.90, 0.94) drop every sample
    between 89% and 90% of the anchor from all zones. Returns (bands, problems)
    where problems lists overlaps and gaps wider than ROUNDING_GAP."""
    rows = sorted(((z, float(lo), float(hi)) for z, (lo, hi) in bands.items()),
                  key=lambda r: r[1])
    resolved, problems = {}, []
    for i, (z, lo, hi) in enumerate(rows):
        if i + 1 == len(rows):
            resolved[z] = (lo, math.inf)
            break
        nz, nlo, _ = rows[i + 1]
        if hi > nlo + 1e-9:
            problems.append(f"{z} [{lo:g}, {hi:g}] overlaps {nz} (starts {nlo:g})")
        elif nlo - hi > ROUNDING_GAP:
            problems.append(f"gap {hi:g}-{nlo:g} between {z} and {nz}")
        resolved[z] = (lo, nlo)
    return resolved, problems


def zone_bounds(config: dict) -> tuple[dict[str, tuple[float, float]], str] | tuple[None, str]:
    """Resolve HR zone bands (bpm) from athlete config. Returns (bands, source).
    Bands are contiguous (see resolve_bands); suspicious tables warn once."""
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
    resolved, problems = resolve_bands(bands)
    if problems:
        _warn_once("zones.bands in config/athlete.yaml: " + "; ".join(problems)
                   + " — zones resolved to run up to the next zone's start")
    return (
        {z: (lo * anchor, hi * anchor) for z, (lo, hi) in resolved.items()},
        source,
    )


def time_in_zone(series: list[list[float]], bands: dict[str, tuple[float, float]]) -> dict[str, int]:
    """Seconds per zone. Each sample covers the gap to the next sample (capped
    at HR_GAP_CAP_S so sparse recordings don't invent zone time)."""
    tiz = {z: 0.0 for z in bands}
    for i, (t, bpm) in enumerate(series):
        dt = min(series[i + 1][0] - t, HR_GAP_CAP_S) if i + 1 < len(series) else 5
        for z, (lo, hi) in bands.items():
            if lo <= bpm < hi:
                tiz[z] += dt
                break
    return {z: round(v) for z, v in tiz.items()}


def efficiency_factor(watts_avg: float | None, hr_avg: float | None) -> float | None:
    if not watts_avg or not hr_avg:
        return None
    return round(watts_avg / hr_avg, 2)


def metrics_settings(config: dict) -> dict:
    """Engine defaults overlaid with the workspace's optional `metrics:` block."""
    settings = dict(METRICS_DEFAULTS)
    settings.update({k: v for k, v in (config.get("metrics") or {}).items()
                     if k in METRICS_DEFAULTS and v is not None})
    return settings


def _watt_spans(watt_series: list[list[float]]) -> list[tuple[float, float, float]]:
    """(from_s, to_s, watts): each watts sample holds since the previous one
    (the first since 0). That is exactly what a C2 split is — its average
    watts stamped at the split's end — and harmless for dense series."""
    spans, prev = [], 0.0
    for t, w in watt_series:
        if t > prev:
            spans.append((prev, t, w))
        prev = max(prev, t)
    return spans


def _span_mean(spans: list[tuple[float, float, float]], lo: float, hi: float) -> tuple[float | None, float]:
    """Time-weighted mean watts over [lo, hi] and the share of it covered."""
    covered = weighted = 0.0
    for a, b, w in spans:
        overlap = min(b, hi) - max(a, lo)
        if overlap > 0:
            covered += overlap
            weighted += overlap * w
    share = covered / (hi - lo) if hi > lo else 0.0
    return (weighted / covered if covered else None), share


def decoupling_pct(hr_series: list[list[float]], watt_series: list[list[float]] | None,
                   window: tuple[float, float]) -> tuple[float, str] | None:
    """First-half vs second-half drift over window (start_s, end_s), split in
    half. Returns (pct, method) or None when a half lacks HR samples.

    pw_hr: efficiency (watts/HR) lost from the first half to the second —
    true power:HR decoupling. Watts are time-weighted per half (see
    _watt_spans), and each half must be at least MIN_WATTS_COVERAGE covered.
    hr_drift (otherwise): HR2/HR1 - 1, a stand-in for decoupling only if
    output was held constant, which nothing here can verify. Positive = HR
    rose relative to output."""
    lo, hi = window
    mid = (lo + hi) / 2
    first = [b for t, b in hr_series if lo <= t < mid]
    second = [b for t, b in hr_series if mid <= t <= hi]
    if len(first) < MIN_HALF_SAMPLES or len(second) < MIN_HALF_SAMPLES:
        return None
    hr1, hr2 = _mean(first), _mean(second)
    if not hr1 or not hr2:
        return None
    if watt_series and len(watt_series) >= 2:
        spans = _watt_spans(watt_series)
        w1, cov1 = _span_mean(spans, lo, mid)
        w2, cov2 = _span_mean(spans, mid, hi)
        if w1 and w2 and min(cov1, cov2) >= MIN_WATTS_COVERAGE:
            ef1, ef2 = w1 / hr1, w2 / hr2
            return round((ef1 - ef2) / ef1 * 100, 1), "pw_hr"
    return round((hr2 - hr1) / hr1 * 100, 1), "hr_drift"


def has_work_bouts(watt_series: list[list[float]] | None, after_s: float) -> bool:
    """True when the watts series shows work bouts (detect_bouts with the
    session heuristic) after after_s. Each sample is expanded to its span so
    a 4-minute interval split counts as 4 minutes. No watts = can't tell =
    False: an HR-only session can't be checked for steadiness."""
    spans = [(max(a, after_s), b, w) for a, b, w in _watt_spans(watt_series or [])
             if b > after_s]
    if len(spans) < 2:
        return False
    avg, _ = _span_mean(spans, spans[0][0], spans[-1][1])
    points = [p for a, b, w in spans for p in ([a, w], [b, w])]
    return bool(detect_bouts(points, threshold=avg * BOUT_THRESHOLD_RATIO,
                             min_bout_s=MIN_BOUT_S))


def decoupling_fields(hr_series: list[list[float]], watt_series: list[list[float]] | None,
                      modality: str | None, settings: dict,
                      duration_s: float | None = None) -> dict:
    """The decoupling entries of `computed:`. The window runs from the end of
    the warm-up to the session's end (duration_s) when the HR trace reaches
    within HR_GAP_CAP_S of it — a 30:07 ride whose last 5-s HR sample landed
    at 29:59 is a 30-minute ride — else to the last HR sample. A null value
    always carries decoupling_note saying why (modality_excluded |
    window_too_short | not_steady | insufficient_samples) — a fact about the
    data, never a judgment about the session."""
    if modality not in settings["decoupling_modalities"]:
        return {"decoupling_pct": None, "decoupling_note": "modality_excluded"}
    start = settings["decoupling_warmup_s"]
    end = max((t for t, _ in hr_series), default=0)
    if duration_s and 0 <= duration_s - end <= HR_GAP_CAP_S:
        end = duration_s
    window_s = max(0, round(end - start))
    fields = {"decoupling_window_s": window_s}
    if window_s < settings["decoupling_min_window_s"]:
        return {"decoupling_pct": None, "decoupling_note": "window_too_short", **fields}
    if has_work_bouts(watt_series, start):
        return {"decoupling_pct": None, "decoupling_note": "not_steady", **fields}
    result = decoupling_pct(hr_series, watt_series, (start, end))
    if result is None:
        return {"decoupling_pct": None, "decoupling_note": "insufficient_samples", **fields}
    pct, method = result
    return {"decoupling_pct": pct, "decoupling_method": method, **fields}


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

    computed: dict = {}
    bands, zones_source = zone_bounds(config)
    if hr_series:
        if bands:
            computed["time_in_zone"] = time_in_zone(hr_series, bands)
        computed["zones_source"] = zones_source
        computed.update(decoupling_fields(hr_series, watt_series or None,
                                          fm.get("modality"), metrics_settings(config),
                                          fm.get("duration_s")))
    ef = efficiency_factor(fm.get("watts_avg"), fm.get("hr_avg"))
    if ef is not None:
        computed["efficiency_factor"] = ef
    if watt_series:
        watt_values = [w for _, w in watt_series]
        avg_w = _mean(watt_values)
        bouts = detect_bouts(watt_series, threshold=avg_w * BOUT_THRESHOLD_RATIO,
                             min_bout_s=MIN_BOUT_S)
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
