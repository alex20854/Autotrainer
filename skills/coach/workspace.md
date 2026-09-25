# Workspace — File Map and Standing Rules

Every athlete has their own **workspace** repo (the current working directory
during coaching). The **engine** (`$ENGINE`, see SKILL.md) is shared and holds
no athlete data. The workspace is your durable memory: anything worth
remembering across sessions must be written to a file in it.

## Map

| Workspace path | What | Who writes it |
|---|---|---|
| `config/athlete.yaml` | zone anchors, equipment, matching config | you (`setup`, reviews) |
| `data/inbox/photos/` | photo-finder candidates awaiting your review (gitignored) | `find_monitor_photos.py` |
| `data/raw/` | immutable inputs (photos, exports); health/ is gitignored | never modified, only added |
| `data/derived/workouts/` | normalized per-workout JSON incl. HR series | parser scripts |
| `data/derived/photos/` | photo-extraction sidecars | prep script (EXIF) + you (vision) |
| `data/sessions/` | canonical session files | `apply_merges.py` (auto) + you (ambiguous) |
| `data/index.jsonl` | generated whole-history index | `build_index.py` only |
| `data/derived/photo_finder.json` | finder state: last scan, promoted/rejected photo UUIDs | `find_monitor_photos.py` only |
| `data/baseline.jsonl` | generated weekly rollup of unstructured movement | `build_baseline.py` only |
| `plans/`, `reports/` | weekly plans and reviews | you |
| `goals.md`, `benchmarks.md` | goal state, dated test results | you |
| `dashboard.html` | rendered dashboard | `build_dashboard.py` only |
| `CLAUDE.md` | workspace notes: engine path, hosted dashboard URL, athlete-specific context | you |

Engine references: data contract `$ENGINE/docs/schema.md` (read before
touching data), full design `$ENGINE/cardio-coach-spec.md`, coaching knowledge
`$ENGINE/knowledge/`.

**Where new knowledge goes.** General, reusable coaching knowledge (methods,
evidence, machine console layouts, reference values) belongs in
`$ENGINE/knowledge/` — it benefits every athlete. Facts about *this* athlete
(test limiters, preferences, injuries) belong in the workspace (`benchmarks.md`,
`goals.md`, session notes, workspace `CLAUDE.md`). Never write athlete data
into the engine.

## Rules that keep the system healthy

1. **Never inline HR series** into sessions, reports, or your context. Scripts
   summarize; you read summaries (`computed:` blocks, index.jsonl).
2. **Answer whole-history questions from `data/index.jsonl`**, not by opening
   hundreds of session files.
3. **Raw is immutable.** Fix problems downstream (sidecars, sessions), never by
   editing raw files.
4. `compliance:` blocks are yours alone; `computed:` blocks belong to
   `compute_metrics.py` alone.
5. Wrist-HR caveats (spec §5): never verify bouts < 2 min by HR peaks; photo
   beats Watch for treadmill speed/incline; grip work corrupts wrist HR.
6. Coaching guardrails: no diagnosis, conservative progression, deload on
   illness signals, state the verification tier with every prescription,
   distinguish RCT-grade claims from practitioner consensus.

## Privacy

Whether a workspace is public is the athlete's choice; the engine is public.
Either way, never extract location into derived records or sessions (no GPS
routes, no gym coordinates) — parsers ignore location fields by design. The
pre-commit hook (`git config core.hooksPath $ENGINE/scripts/githooks`) runs
`privacy_check.py` against personal strings in the workspace's gitignored
`config/privacy.local.yaml`; `privacy_check.py --strip-gps` rewrites photo
EXIF in place (the one sanctioned mutation of `data/raw/`).
