#!/usr/bin/env python3
"""Re-derive modality for Health-only, unjudged sessions (migration helper).

When the modality vocabulary grows (docs/schema.md) — Elliptical workouts, for
example, used to fall through to `mixed` — existing single-source sessions keep
their old label because nothing re-proposes them. This rewrites such sessions
from the current apply_merges.TYPE_TO_MODALITY: modality, id and filename
change together (apply_merges.write_session removes the superseded file).

Only sessions still on the `mixed` fallback are candidates: a more specific
label on a Health-only session (say `bikeerg` with no photo) can only have
been set by hand, and the file has no other way to say so. Sessions carrying
judgment (compliance, prescription link, non-auto match) or more than one
source are never touched either. And a workout type the athlete's own
`matching.modality_map` lists under machines of *different* modalities (an
athlete who logs AirDyne rides as the Watch's "Elliptical") is undecidable from
the type alone: those sessions are reported, not relabelled — the coach decides
by hand and sets match_method: claude. Rebuild metrics/index afterwards
(ingest does).

Usage: python3 <engine>/scripts/relabel_sessions.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import frontmatter, workspace
from lib import sessions as sessions_lib
import apply_merges

REPO_ROOT = workspace.root()
SESSIONS_DIR = REPO_ROOT / "data" / "sessions"
CONFIG_PATH = REPO_ROOT / "config" / "athlete.yaml"


def ambiguous_types(modality_map: dict | None) -> dict[str, set[str]]:
    """Workout types listed under machines of more than one modality."""
    by_type: dict[str, set[str]] = {}
    for machine, types in (modality_map or {}).items():
        mod = apply_merges.MACHINE_TO_MODALITY.get(machine)
        if not mod:
            continue
        for t in types or []:
            by_type.setdefault(t, set()).add(mod)
    return {t: mods for t, mods in by_type.items() if len(mods) > 1}


def plan(sessions_dir: Path, repo_root: Path, modality_map: dict | None = None):
    """-> (changes, undecided): changes = (path, fm, body, new_modality);
    undecided = (path, workout_type, modalities the athlete's map allows)."""
    changes, undecided = [], []
    amb = ambiguous_types(modality_map)
    for path in sorted(sessions_dir.rglob("*.md")) if sessions_dir.is_dir() else []:
        fm, body = frontmatter.load(path)
        if not sessions_lib.is_upgradable(fm) or fm.get("modality") != "mixed":
            continue
        rec_path = repo_root / fm["sources"][0]["ref"]
        if not rec_path.exists():
            continue
        wtype = json.loads(rec_path.read_text(encoding="utf-8")).get("workout_type")
        new = apply_merges.TYPE_TO_MODALITY.get(wtype, "mixed")
        if new == fm.get("modality"):
            continue
        if wtype in amb:
            undecided.append((path, wtype, amb[wtype]))
            continue
        changes.append((path, fm, body, new))
    return changes, undecided


def run(sessions_dir: Path, repo_root: Path, dry_run: bool, modality_map: dict | None = None) -> int:
    changes, undecided = plan(sessions_dir, repo_root, modality_map)
    for path, fm, body, new in changes:
        print(f"  {path.stem}: {fm.get('modality')} -> {new}" + ("  (dry run)" if dry_run else ""))
        if not dry_run:
            fm["modality"] = new
            apply_merges.write_session(fm, body, sessions_dir)
    for path, wtype, mods in undecided:
        print(f"  {path.stem}: left as mixed — '{wtype}' is listed under {sorted(mods)} in "
              "matching.modality_map; decide by hand (set match_method: claude)")
    print(f"relabel: {len(changes)} session(s) {'would change' if dry_run else 'rewritten'}, "
          f"{len(undecided)} need a decision")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    workspace.require(REPO_ROOT)
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return run(SESSIONS_DIR, REPO_ROOT, args.dry_run, (cfg.get("matching") or {}).get("modality_map"))


if __name__ == "__main__":
    raise SystemExit(main())
