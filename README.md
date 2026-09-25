# Autotrainer — Claude Cardio Coach

A cardio coach that runs inside Claude Code. Claude does the judgment work
(reading monitor photos, programming, compliance scoring, weekly reviews);
a handful of deterministic scripts do the parsing and math; your training
history lives in plain files in a git repo you own. Full design:
`cardio-coach-spec.md`.

This repo is the **engine** — reusable, with no athlete data. Your training
lives in a separate **workspace** repo.

## Getting started

1. Get the engine and its Python dependencies (macOS Homebrew Python blocks
   global installs, so use the venv):

   ```
   git clone https://github.com/alex20854/Autotrainer.git
   cd Autotrainer
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

2. Make the `/coach` skill available. Either install the plugin
   (`/plugin marketplace add <path-or-github-repo>` then
   `/plugin install autotrainer@autotrainer`), or — for engine development —
   symlink it into your workspace:
   `ln -s <engine>/skills/coach <workspace>/.claude/skills/coach`.
   The skill finds the engine's scripts and venv by resolving its own path,
   so keep the engine checkout (with `.venv`) in place.

3. Create a workspace: in a new empty directory, run `/coach setup`. It
   scaffolds from `templates/workspace/`, wires the privacy hook, and does the
   goal/zone intake. Keep the workspace private unless you want your training
   public.

## Using it (from your workspace)

```
/coach setup    # first run: scaffold, goal intake, zones, expectations
/coach ingest   # after adding data: parse, extract photos, reconcile
/coach plan     # write next week's prescriptions
/coach review   # weekly: compliance scores, trends, adjustments
/coach ask      # anything, grounded in your ledger
```

## Feeding it data (workspace paths)

| Drop | Where | Notes |
|---|---|---|
| Monitor photos | `data/raw/photos/` | after every machine session; EXIF time is the matching key |
| Health Auto Export JSON | `data/raw/health/` | ingest is idempotent — drop exports whenever |
| Apple Health `export.xml` | `data/raw/health/` | backfill; gitignored (huge), parsed into committed derived records |
| C2 Logbook CSV | `data/raw/c2/` | opportunistic |

**Dashboard:** every ingest re-renders `dashboard.html` in the workspace — a
single self-contained file, no server. `/coach ingest` can also keep a hosted
copy as a private claude.ai artifact.

## What's in the engine

- `skills/coach/` — the skill and its playbooks
- `scripts/` — parsers, reconciliation, metrics, index, dashboard
- `knowledge/` — evidence-graded training methods (`styles/`), research
  dossier, machine console guide, VO2max reference values
- `docs/schema.md` — the data contract
- `templates/workspace/` — new-workspace skeleton

## Development

```
python3 -m pytest tests/
git config core.hooksPath scripts/githooks
cp config/privacy.local.yaml.example config/privacy.local.yaml   # then add your personal strings
```

Integration tests run against `$AUTOTRAINER_WORKSPACE` (or a sibling
`../Autotrainer_Alex`) and skip when none is present. The pre-commit hook
blocks GPS/owner EXIF, addresses, phone numbers, personal emails, and your
listed personal strings — in this repo and in workspaces that use it.
