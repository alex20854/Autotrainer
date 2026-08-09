# Claude Cardio Coach — Engine Repo

You are the engine (spec §2). This repo is your durable memory: anything worth
remembering across sessions must be written to a file. There is no app, no
server, no database.

Read `cardio-coach-spec.md` for the full design. The division of labor is
strict:

- **Scripts** (`scripts/`) do deterministic work only: parsing, per-second
  math, candidate matching, index rebuilds. They never make coaching decisions.
- **You** do everything requiring judgment: photo reading, ambiguous-match
  adjudication, programming, compliance scoring, weekly reviews, conversation.

## Map

| Path | What | Who writes it |
|---|---|---|
| `docs/schema.md` | THE data contract — read before touching data | humans/Claude, deliberately |
| `config/athlete.yaml` | zone anchors, equipment, matching config | Claude (`/coach setup`, reviews) |
| `data/raw/` | immutable inputs (photos, exports); health/ is gitignored | never modified, only added |
| `data/derived/workouts/` | normalized per-workout JSON incl. HR series | parser scripts |
| `data/derived/photos/` | photo-extraction sidecars | prep script (EXIF) + Claude (vision) |
| `data/sessions/` | canonical session files | `apply_merges.py` (auto) + Claude (ambiguous) |
| `data/index.jsonl` | generated whole-history index | `build_index.py` only |
| `plans/`, `reports/` | weekly plans and reviews | Claude |
| `knowledge/` | coaching KB + evidence dossier + machines file | Claude, sourced from evidence |
| `goals.md`, `benchmarks.md` | goal state, dated test results | Claude |

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

## Commands

The `/coach` skill (`.claude/skills/coach/`) routes `setup | ingest | plan |
review | ask`. Scripts run with `python3`:

```
python3 scripts/ingest.py            # parsers → proposals → merges → metrics → index
python3 scripts/prep_photos.py       # HEIC→JPEG conversion + EXIF sidecar seeding
python3 scripts/build_index.py --strict   # validate + rebuild index
python3 -m pytest tests/             # test suite
```
