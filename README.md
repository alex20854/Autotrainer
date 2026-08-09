# Autotrainer — Claude Cardio Coach

Claude *is* the engine: this repo is the durable memory of a cardio coaching
system — flat files, a handful of deterministic scripts, and Claude Code
skills for everything requiring judgment. Full design: `cardio-coach-spec.md`.

## Using it

Talk to the coach in Claude Code:

```
/coach setup    # first run: goal intake, zones, expectations
/coach ingest   # after adding data: parse, extract photos, reconcile
/coach plan     # write next week's prescriptions
/coach review   # weekly: compliance scores, trends, adjustments
/coach ask      # anything, grounded in your ledger
```

## Feeding it data

| Drop | Where | Notes |
|---|---|---|
| Monitor photos | `data/raw/photos/` | after every machine session; EXIF time is the matching key |
| Health Auto Export JSON | `data/raw/health/` | iCloud folder sync; arrives when it arrives — ingest is idempotent |
| Apple Health `export.xml` | `data/raw/health/` | backfill; gitignored (huge), parsed into committed derived records |
| C2 Logbook CSV | `data/raw/c2/` | opportunistic, when sync worked |

Then `/coach ingest`.

## Layout

`CLAUDE.md` is the operating manual (file map, rules). `docs/schema.md` is the
data contract. `config/athlete.yaml` holds zone anchors. Sessions live in
`data/sessions/`, the generated index in `data/index.jsonl`, plans and weekly
reviews in `plans/` and `reports/`, the evidence-graded coaching knowledge
base in `knowledge/`.

## Development

```
pip install -r requirements.txt
python3 -m pytest tests/
```

## Privacy (public repo)

One-time per clone:

```
git config core.hooksPath scripts/githooks        # pre-commit privacy check
cp config/privacy.local.yaml.example config/privacy.local.yaml   # then edit
```

The check blocks commits containing GPS/owner EXIF, addresses, phone numbers,
personal emails, or your listed personal strings. Details in `CLAUDE.md`.
