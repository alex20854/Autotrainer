#!/usr/bin/env python3
"""Ingest orchestrator: the deterministic backbone of /coach ingest.

Runs, in order:
  1. parse_health_export   (backfill export.xml, if present)
  2. parse_auto_export     (ongoing Health Auto Export JSON)
  3. parse_c2              (opportunistic C2 CSVs)
  4. prep_photos           (HEIC conversion + EXIF sidecars)
  5. propose_matches       (candidate pairing + baseline routing)
  6. apply_merges          (write auto-merge session files)
  7. build_baseline        (weekly baseline-activity rollup)
  8. compute_metrics       (time-in-zone, decoupling, EF, bouts)
  9. build_index           (regenerate index.jsonl)
 10. build_dashboard       (re-render dashboard.html)

Everything is idempotent — safe to re-run any time new raw files appear.
After this, Claude's judgment work remains: vision-extract pending photos
(then re-run from step 5), and resolve ambiguous cases during /coach review.

Usage: python3 scripts/ingest.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

STEPS = [
    "parse_health_export.py",
    "parse_auto_export.py",
    "parse_c2.py",
    "prep_photos.py",
    "propose_matches.py",
    "apply_merges.py",
    "build_baseline.py",
    "compute_metrics.py",
    "build_index.py",
    "build_dashboard.py",
]


def main() -> int:
    for step in STEPS:
        result = subprocess.run([sys.executable, str(SCRIPTS / step)])
        if result.returncode != 0:
            print(f"ingest: {step} failed (exit {result.returncode})", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
