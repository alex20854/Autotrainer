# Autotrainer — Cardio Coach Engine

This repo is the **engine**: reusable capabilities for a Claude cardio coach —
ingest scripts, the `/coach` skill, the data contract, dashboarding, and the
evidence-graded knowledge base (training methods, workout concepts, machine
consoles, reference values). It contains **no athlete data**.

Each athlete's data lives in a separate **workspace** repo (created from
`templates/workspace/` by `/coach setup`). The maintainer's own workspace is
the private sibling checkout `../Autotrainer_Alex` — coaching sessions happen
there; engine development happens here.

Read `cardio-coach-spec.md` for the full design. The division of labor is
strict:

- **Scripts** (`scripts/`) do deterministic work only: parsing, per-second
  math, candidate matching, index rebuilds, rendering. They never make
  coaching decisions.
- **Claude** (via `skills/coach/`) does everything requiring judgment: photo
  reading, ambiguous-match adjudication, programming, compliance scoring,
  weekly reviews, conversation.

## Map

| Path | What |
|---|---|
| `skills/coach/` | the `/coach` skill; `workspace.md` = workspace file map + standing rules |
| `scripts/` | deterministic pipeline; `scripts/lib/workspace.py` resolves engine vs workspace paths |
| `docs/schema.md` | THE data contract — read before touching data formats |
| `knowledge/` | coaching KB: `styles/` (methods), `evidence.md`, `machines.md`, `reference-values.yaml` |
| `templates/workspace/` | skeleton for a new athlete workspace (blank config, goals, benchmarks) |
| `tests/` | unit tests on synthetic fixtures + integration tests on a real workspace |
| `.claude-plugin/` | plugin + marketplace manifests (distribution) |

## Engine rules

1. **Workspace-agnostic.** Scripts resolve data via `lib.workspace.root()`
   (`$AUTOTRAINER_WORKSPACE`, else nearest ancestor of cwd with
   `config/athlete.yaml`); engine assets via `workspace.ENGINE_ROOT`. Never
   hardcode an athlete's paths, anchors, equipment, or URLs.
2. **General knowledge only.** `knowledge/` holds what benefits any athlete.
   Facts about a specific athlete belong in their workspace.
3. **Schema changes are migrations.** If a data format changes, update
   `docs/schema.md` and ship a script that upgrades existing workspaces.
4. **Tests.** `python3 -m pytest tests/` — integration tests run against
   `$AUTOTRAINER_WORKSPACE` or `../Autotrainer_Alex` and skip if neither exists.
   They read the workspace; they must never write to it.
5. **Apple Photos is read-only.** `find_monitor_photos.py` may only read the
   library and export independent copies; every write goes through its
   `_guard_write()`. The allowlist test pinning its osxphotos calls may only be
   widened for read-only members, deliberately. Never use photoscript/PhotoKit
   write paths (albums, keywords, edits, deletes).

## Privacy — this repo is PUBLIC

No athlete data, ever: `.gitignore` blocks the workspace paths as a guard. The
privacy hook still runs here to catch personal strings (name, address,
employer, gym...) listed in the gitignored `config/privacy.local.yaml`.

- **Before every commit** run `python3 scripts/privacy_check.py --staged`, or
  install the hook once per clone: `git config core.hooksPath scripts/githooks`.
  The same hook serves workspaces (`core.hooksPath <engine>/scripts/githooks`).
- **Test samples of PII** (phones, addresses, emails) must be obviously fake
  and assembled at runtime so the repo-wide audit stays clean.
- **Never extract location** into derived records: parsers ignore
  route/location fields by design — keep it that way when extending them.
- **Git identity:** commit with a noreply email.

## Commands

```
python3 -m pytest tests/                         # engine tests
cd ../Autotrainer_Alex && ../Autotrainer/.venv/bin/python ../Autotrainer/scripts/ingest.py
python3 scripts/privacy_check.py                 # audit whichever repo you're in
```
