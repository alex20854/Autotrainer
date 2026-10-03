# /coach setup — Intake, Zones, Expectations

Conversational intake. Outcome: `goals.md` has an active goal,
`config/athlete.yaml` has (at least bootstrap) anchors, a field test is
scheduled (once `adapt.md` §1's intensity gate is met, if the athlete is
coming back from a layoff), and the athlete has heard honest §9 timelines.

## 0. New workspace (only if `config/athlete.yaml` is missing)

The current directory isn't a workspace yet. Confirm with the athlete that
this directory should become their training workspace (it should be its own
git repo, not inside the engine), then scaffold it from the engine template:

```
cp -Rn "$ENGINE/templates/workspace/." .
git init -q 2>/dev/null; git config core.hooksPath "$ENGINE/scripts/githooks"
```

Ask whether they want the workspace repo public or private (training data can
be public by choice; recommend private), and have them fill
`config/privacy.local.yaml` with personal strings the privacy hook must block.
Record the engine path and any hosted-dashboard URL in the workspace
`CLAUDE.md` as they come up.

## 0.5 Read before asking

Run `"$PY" "$ENGINE/scripts/status.py" --json --as-of <today>` and read
`config/athlete.yaml` and `benchmarks.md`. Present what the ledger already
shows as proposed defaults, phrased as confirmations that quote status values
directly ("Last 4 weeks: 120 / 95 / 0 / 60 structured minutes, BikeErg most
weeks — is that your normal?"), not questions and not your own averages:

- Training by modality and weekly volume, quoted per week from the last few
  `weeks[]` (`by_modality_min`, `structured_min`, `baseline_min`), and
  consistency (`consistency`).
- Days since the last structured session (`days_since_last_structured`).
- Which anchors exist (`anchors`, `anchors.missing`), whether their benchmark
  notes say sub-maximal or limiter-affected (then they are floors), and how
  old the newest benchmark is (`benchmarks.age_days`, `past_cadence`).
- The equipment list in `config/athlete.yaml`.
- Recovery numbers (`recovery`) as context only.

Skip what is empty (a new workspace has no ledger) — then ask instead. If
`adapt.md` §1 (recency and recent volume) puts the athlete on a re-entry
rung, the first plan is a re-entry block, and the retest waits for that
section's intensity gate, not the block's calendar end.

## 1. Goal intake

Ask, conversationally (not as a form), ONLY what data cannot answer:
- What are you actually training for? Map to a track — general CV
  health/longevity, metabolic health & performance, Hyrox/competition — or
  define a custom track. `goals.md` describes the tracks. Any event date?
- Realistic days per week and session length; injuries or limitations;
  strength days (so hard cardio does not land beside them).
- Which machines from the equipment list are in rotation this season. For
  any machine new to the athlete: one console photo and one Watch workout
  type they will always use for it (`adapt.md` §5).
- If Hyrox: is there a base? A race date before the base exists is the
  programming error the coach catches (spec §9) — say so and sequence
  base-first.

Write the result to `goals.md` (Active goal section, template provided there).

## 2. Zone anchoring

- If anchors already exist (0.5), confirm them rather than re-deriving;
  describe floor anchors as "at least". If benchmarks exist in
  `benchmarks.md` without anchors, derive anchors from them.
- Else bootstrap: ask age and any known max-HR observations; set provisional
  `hr_max` (observed max if available, else 220−age flagged as formula),
  provisional `lthr` null, and — if the athlete wants MAF framing — `maf_cap`.
  Write to `config/athlete.yaml`, clearly marking formula values as
  bootstrap-only in conversation.
- Schedule a field LTHR/FTP test when none exists or `past_cadence` is true
  — into the first plan, or, when `adapt.md` §1's intensity gate is not yet
  met, the first week after it is (0.5). Default
  modality: BikeErg unless the athlete prefers another — cleanest watts,
  technique-independent. Protocol is in `benchmarks.md`.

## 3. Expectation-setting (§9)

From the goal track's styles, walk through the four dose-response fields of
each core method (`$ENGINE/knowledge/styles/*.md` frontmatter): minimum effective
dose, when *this system's own metrics* will show benefit (and which metric),
the consistency bar, and decay/maintenance. Close with the track's
time-to-value summary from `goals.md` so the athlete knows what the first 8-12
weeks will and won't show.

## 4. Wire-up check (once, if not done)

Confirm the data pipeline basics: Health Auto Export configured (Premium
automation → iCloud folder synced into `data/raw/health/`), photo habit
(monitor photo after every machine session), and where C2 exports land when
sync works (`data/raw/c2/`). Note anything unresolved in `goals.md` under the
active goal.
