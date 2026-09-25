# /coach setup — Intake, Zones, Expectations

Conversational intake. Outcome: `goals.md` has an active goal,
`config/athlete.yaml` has (at least bootstrap) anchors, a field test is
scheduled, and the athlete has heard honest §9 timelines.

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

## 1. Goal intake

Ask, conversationally (not as a form):
- What are you actually training for? Map to a track — general CV
  health/longevity, metabolic health & performance, Hyrox/competition — or
  define a custom track. `goals.md` describes the tracks.
- Constraints: sessions/week realistically available, session length, equipment
  actually accessible this season (cross-check `config/athlete.yaml:
  equipment`), injuries/limitations, upcoming events.
- If Hyrox: is there a base? A race date before the base exists is the
  programming error the coach catches (spec §9) — say so and sequence
  base-first.

Write the result to `goals.md` (Active goal section, template provided there).

## 2. Zone anchoring

- If benchmarks exist in `benchmarks.md`, derive anchors from them.
- Else bootstrap: ask age and any known max-HR observations; set provisional
  `hr_max` (observed max if available, else 220−age flagged as formula),
  provisional `lthr` null, and — if the athlete wants MAF framing — `maf_cap`.
  Write to `config/athlete.yaml`, clearly marking formula values as
  bootstrap-only in conversation.
- Schedule the first field LTHR/FTP test into the first plan (default
  modality: BikeErg unless the athlete prefers another — cleanest watts,
  technique-independent). Protocol is in `benchmarks.md`.

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
