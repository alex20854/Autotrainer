# Data Schema — The Contract

This file defines every structured format in the engine. Scripts and skills both
conform to it. Change it deliberately: the frontmatter schema is the migration
contract (spec §6) — if SQLite ever happens, it maps from these fields.

## Session file

Path: `data/sessions/YYYY/YYYY-MM-DD-<modality>[-<slug>][-N].md`
(`-N` disambiguates two same-modality sessions on one day). The session `id` is
the filename stem.

```yaml
---
id: 2026-08-08-bikeerg-z2
date: 2026-08-08
start: "2026-08-08T06:15:03-04:00"   # RFC3339, local time with offset
end: "2026-08-08T07:01:44-04:00"
modality: bikeerg                     # controlled vocabulary, see below
machine: concept2-bikeerg             # optional, more specific than modality
duration_s: 2801                      # active duration (best source)
hr_avg: 132                           # null when no HR source
hr_max: 147
watts_avg: 185                        # null when no power source
distance_m: 21400
kcal: 410
sources:                              # provenance — which evidence built this session
  - kind: health                      # health | photo | c2 | user
    ref: data/derived/workouts/health-2026-08-08T061503-cycling.json
    confidence: high                  # high | medium | low
  - kind: health                      # same bout captured twice (export.xml +
    ref: data/derived/workouts/health-2026-08-08T061505-indoor-cycling.json
    confidence: high                  # Auto Export; Watch + iPhone): recorded
    role: duplicate                   # with role duplicate|complement so
  - kind: photo                       # re-ingest sees the record claimed
    ref: data/raw/photos/IMG_4231.jpeg
    extraction: data/derived/photos/IMG_4231.yaml
    confidence: high
match_confidence: 0.95                # 0–1, from the proposal script or Claude
match_method: auto                    # auto | claude (Claude decided) | manual (the athlete edited) — automatic passes rewrite only auto
prescription_id: 2026-W32-2           # null for unprescribed sessions
compliance:                           # written by Claude during /coach review
  tier: 1                             # 1 | 2 | 3 (spec §8)
  score: 0.92                         # 0–1
  components: {duration: 1.0, time_in_zone: 0.88, decoupling_ok: true}
computed:                             # written by scripts/compute_metrics.py
  time_in_zone: {z1: 120, z2: 2380, z3: 240, z4: 0, z5: 0}   # seconds, HR zones
  zones_source: lthr                  # lthr | bootstrap (0.9 x hr_max) | unconfigured
  decoupling_pct: 3.1                 # % second half vs first, after the warm-up; null = not measured
  decoupling_method: pw_hr            # pw_hr (watts/HR) | hr_drift (HR alone); absent when null
  decoupling_window_s: 2201           # seconds measured (warm-up end -> session end); absent for modality_excluded
  # decoupling_note: window_too_short # present only when decoupling_pct is null (see below)
  efficiency_factor: 1.40             # avg watts / avg HR
  bouts: 4                            # detected work bouts (Tier 2), omitted for steady state
---

Free-form body: athlete notes, RPE, Claude's observations from review.
```

Rules:

- **HR series never appear here** — only summaries. Series live in derived
  workout records (below).
- `null` is a legal value for any metric a source didn't provide. Missing
  sources are normal (spec §5: best available evidence).
- `compliance` is only ever written by Claude (judgment). `computed` is only
  ever written by `compute_metrics.py` (math). Scripts never touch `compliance`.
- **Time-in-zone** uses contiguous bands: zones sorted by lower bound, each
  running up to (not including) the next zone's lower bound, the top zone
  open-ended. That is the faithful reading of integer-percent tables ("85–89%"
  means everything below 90%); every HR sample lands in exactly one zone, so
  zone totals equal the HR trace duration (gaps capped at 30 s). Overlapping
  bands, or gaps wider than the 0.01 rounding gap, warn on stderr.
- **Decoupling** is measured only for modalities in
  `metrics.decoupling_modalities` (default: all but walk, treadmill-walk, sled,
  mixed), over `[start + decoupling_warmup_s, end]` split in half (defaults
  600 s warm-up, 1200 s minimum window — engineering defaults, not a cited
  standard). `end` is the session's `duration_s` when the HR trace reaches
  within 30 s of it (so a 30:07 ride whose last 5-s sample lands at 29:59
  still counts as 30 minutes), else the last HR sample. `pw_hr` = efficiency
  (watts/HR) lost from the first half to the second, when a watts series
  covers at least 90% of each half; each watts sample holds since the
  previous one (a C2 split's average watts is stamped at its end), weighted by
  time per half. `hr_drift` = second-half vs first-half average HR, which
  equals decoupling only if output was held constant (unverifiable without a
  power trace). Positive = HR rose relative to output. A null value carries
  `decoupling_note` and has no `decoupling_method`: `modality_excluded` (no
  `decoupling_window_s` either), `window_too_short` (too short to judge
  durability — not a failure), `not_steady` (the watts series shows work
  bouts after the warm-up — the same detection as `bouts`, 60 s+ above
  1.15 x average watts, a heuristic), or `insufficient_samples` (a half has
  under 5 HR samples, e.g. a dropout). HR-only sessions can't be checked for
  steadiness, which is one more reason `hr_drift` is not decoupling. These
  fields are recomputed on every ingest, so adding them needed no migration.

### Modality vocabulary

`rowerg | skierg | bikeerg | airdyne | stairclimber | versaclimber | bike |
treadmill-run | treadmill-walk | run | walk | sled | elliptical | mixed`

Growing the vocabulary: add the label to `build_index.MODALITIES`, the
workout types to `apply_merges.TYPE_TO_MODALITY` (and the machine id to
`MACHINE_TO_MODALITY`), then run `scripts/relabel_sessions.py` in each
workspace so Health-only sessions that fell through to `mixed` pick up the new
label. It leaves judged sessions alone, and it refuses to decide for a type the
athlete's own `matching.modality_map` lists under machines of different
modalities (e.g. an athlete who logs AirDyne rides as the Watch's "Elliptical"):
those stay `mixed` until the coach decides by hand.

Add new values here first, then use them.

## baseline.jsonl

Path: `data/baseline.jsonl`. Generated by `scripts/build_baseline.py` — never
hand-edited. The weekly rollup of **baseline activity**: unstructured movement
(walks, hikes — `config/athlete.yaml: classification.baseline_types`) that the
coach tracks in aggregate but never prescribes or scores. A baseline-type
record is *promoted* to the session ledger instead when its duration reaches
`promote_min_duration_s` or a monitor photo pairs with it; records claimed by
sessions never appear here (no double counting). One JSON object per ISO week:

**Late-arriving sources.** A Health-only session written by `apply_merges`
(`match_method: auto`, one `health` source, no `compliance`, no `prescription_id`)
is *upgradable*: if a monitor photo later pairs cleanly with its record,
`propose_matches` proposes the pair and `apply_merges` rewrites the session in
place — the id changes if the modality does (`…-bike` → `…-bikeerg`) and the
superseded file is removed. Sessions carrying judgment are never rewritten; a
late source for those surfaces as an `attach_to_session` case.

```json
{"week": "2026-W32", "count": 5, "minutes": 118, "distance_m": 9200,
 "kcal": 410, "by_type": {"Outdoor Walk": 5}, "hr_avg": 96}
```

`hr_avg` is duration-weighted across activities that carried HR, else null.

## index.jsonl

Path: `data/index.jsonl`. Generated by `scripts/build_index.py` — never
hand-edited. One JSON object per session, sorted by (date, start), containing
the frontmatter scalars flattened:

```json
{"id": "...", "date": "...", "start": "...", "modality": "...", "machine": "...",
 "duration_s": 0, "hr_avg": 0, "hr_max": 0, "watts_avg": 0, "distance_m": 0,
 "kcal": 0, "source_kinds": ["health", "photo"], "match_confidence": 0.95,
 "prescription_id": null, "tier": 1, "compliance_score": 0.92,
 "tiz_z2_s": 2380, "decoupling_pct": 3.1, "decoupling_method": "pw_hr",
 "decoupling_note": null, "efficiency_factor": 1.4,
 "file": "data/sessions/2026/2026-08-08-bikeerg-z2.md"}
```

`decoupling_method` travels with `decoupling_pct` (`pw_hr` | `hr_drift` |
null) so an HR-drift value is never read as power:HR decoupling, and
`decoupling_note` says why a null is null (`modality_excluded` |
`window_too_short` | `not_steady` | `insufficient_samples`; null when a value
exists) so "too short to judge" is readable without opening the session.

Claude answers whole-history questions from this file, not by opening sessions.

## Derived workout record

Path: `data/derived/workouts/<record_id>.json`. Produced by the parsers; the
normalized common format all sources feed (spec §5). Committed to git — since
raw health exports are gitignored for size, these records are the durable form
of the HR data.

```json
{
  "record_id": "health-2026-08-08T061503-cycling",
  "source_kind": "health",
  "source_file": "data/raw/health/HealthAutoExport-2026-08-08.json",
  "workout_type": "HKWorkoutActivityTypeCycling",
  "start": "2026-08-08T06:15:03-04:00",
  "end": "2026-08-08T07:01:44-04:00",
  "duration_s": 2801,
  "kcal": 410,
  "distance_m": null,
  "hr": {"avg": 132, "max": 147, "series": [[0, 98], [5, 101]]},
  "splits": null,
  "watts": null
}
```

- `record_id` = `<source_kind>-<start compressed to YYYY-MM-DDTHHMMSS>-<type slug>`.
  Deterministic → re-running any parser on the same raw data overwrites the same
  file (idempotent ingest, no duplicates). A capture from a *different* raw
  file replaces a stored record only if strictly richer (more HR samples, then
  more fields) — overlapping or older exports never downgrade a record.
- `hr.series` is `[offset_seconds_from_start, bpm]` pairs. C2 records may also
  carry `splits` (list of `{t_s, distance_m, pace_s_per_500m, watts}`) and
  `watts` (series like `hr.series`).

## metrics.jsonl

Path: `data/derived/metrics.jsonl`. Whitelisted daily health metrics
(`resting_heart_rate`, `vo2_max`, `heart_rate_variability`) upserted from
Health Auto Export files by `parse_auto_export.py` — one line per (date,
metric), merged so points survive after old raw exports are deleted:

```json
{"date":"2026-08-11","name":"resting_heart_rate","value":52.0,"units":"count/min"}
```

Recovery signals for reviews (resting-HR / HRV spikes) and estimation inputs
(Apple's VO2max) live here.

## Status facts

Produced on demand by `scripts/status.py` (code and the exact JSON contract:
`scripts/lib/facts.py` module docstring). Nothing is stored: it is a read-only
view over the files above, so playbooks and the dashboard read facts instead
of computing them by hand. `--json` prints the dict with sorted keys,
byte-stable across runs; the default output is a brief of at most 15 lines.
Facts only — measurements, dates, counts and booleans against configured
thresholds; never advice, scores or verdicts.

- **Reference date.** `as_of` is the newest date in the data (index rows,
  baseline weeks, metric points), never the wall clock. `--as-of YYYY-MM-DD`
  overrides it (playbooks pass today's date so a stale ledger shows as
  stale); dated data after `as_of` is ignored, while goal, plan, review,
  anchors and pipeline always reflect the current files.
- **sessions / weeks / consistency.** A structured session is an index row
  whose modality is not in `status.unstructured_modalities`. `weeks` are
  contiguous ISO weeks from the first session's week to the `as_of` week,
  zero-filled, oldest first; `baseline_min` comes from `baseline.jsonl`.
  `consistency` counts weeks with at least `status.consistency_sessions`
  structured sessions; the current streak skips an `as_of` week that has not
  met the threshold yet.
- **benchmarks.** Headings in `benchmarks.md` of the form
  `### YYYY-MM-DD — <title>` (hyphen, en or em dash) outside code fences;
  `past_cadence` is `age_days > status.benchmark_cadence_days`.
- **anchors.missing.** Null `hr_max` / `lthr` / `hr_resting`, plus each null
  field of a `power.<modality>` slot that a machine in `equipment` maps to.
- **goal / plan / review.** `goal.active` needs a filled `- Track:` line in
  the `## Active goal` section of `goals.md`; `plan.exists` is
  `plans/<ISO week of as_of>.md`; `latest` values are the newest file stems.
- **recovery.** Latest value, 7- and 28-day medians (with `n`), the delta to
  the 28-day median, and `days_elevated`: consecutive most-recent resting-HR
  days at or above the 28-day median plus `status.resting_hr_elevated_bpm`.
- **pipeline.** Newest workout end, pending and inbox photo counts, ambiguous
  reconciliation cases.

The thresholds are engineering defaults or practitioner heuristics
[unverified], overridable under an optional `status:` block in
`config/athlete.yaml`; a wrong-typed override falls back to the default.

## Photo extraction sidecar

Path: `data/derived/photos/<photo stem>.yaml`. EXIF fields are written by
`scripts/prep_photos.py`; everything else is written by Claude vision during
`/coach ingest`. A photo with no sidecar (or `extracted: false`) is pending.

```yaml
photo: data/raw/photos/IMG_4231.jpeg
converted: data/derived/photos_converted/IMG_4231.jpg   # only for HEIC originals
exif_time: "2026-08-08T07:03:12"     # with the camera's UTC offset; naive only if it recorded none
extracted: true
machine: concept2-bikeerg            # Claude's read of the console
machine_confidence: high
fields:                              # per-field value + confidence
  elapsed_time_s: {value: 2700, confidence: high}
  distance_m: {value: 21400, confidence: high}
  watts_avg: {value: 185, confidence: medium}
  kcal: {value: 410, confidence: high}
splits: []                           # if the console shows them
notes: ""
```

## Plan file

Path: `plans/YYYY-Www.md` (ISO week). Prescription IDs are `YYYY-Www-N` where N
is the workout slot (1-based); sessions echo the ID in `prescription_id`.

```yaml
---
week: 2026-W33
goal_track: general-cv-health
prescriptions:
  - id: 2026-W33-1
    style: zone2               # matches a knowledge/styles/ entry stem
    tier: 1
    modality: bikeerg
    scheduled_day: mon
    targets: {duration_s: 3600, hr_band: [118, 138], watts_ceiling: 190}
  - id: 2026-W33-2
    style: norwegian-4x4
    tier: 2
    modality: bikeerg
    scheduled_day: thu
    targets: {bouts: 4, bout_s: 240, recovery_s: 180, watts_band: [250, 275]}
---

Human-readable prescriptions: the what, the why, and the §9 time-to-benefit
context for each.
```

Plan frontmatter also carries (additive):

- `status`: `active` | `draft`. `draft` is a provisional block written while
  there is no active goal (a re-entry block from `skills/coach/adapt.md`).
  Draft plans are never compliance-scored, and their body says so. Absent
  means `active`.
- `goal_track`: the active goal's track id from `goals.md`, or `pending` when
  `status: draft`.
- `targets` may carry `hr_ceiling` (bpm): an HR cap for easy or HR-only work
  (re-entry, machines without power anchors). No script reads plan targets
  yet; the vocabulary is the contract for a future plan-vs-actual script.

## config/athlete.yaml

Machine-readable zone anchors and matching config. Updated by `/coach setup`
and after benchmark retests; `benchmarks.md` is the dated human log the values
came from. See the file itself for field documentation.

- `athlete.anchors_note` (optional string): a short note on the anchors'
  standing in the coach's own words (e.g. `floor - re-test pending`). The
  dashboard shows it verbatim after the anchors in its subtitle; no script
  interprets it. Unset means no note. Additive, so no migration.

## dashboard.html

Path: `dashboard.html` at the workspace root. Generated by
`scripts/build_dashboard.py` on every ingest, never hand-edited: a pure,
self-contained rendering (inline CSS/SVG, no external requests) of
`index.jsonl`, `baseline.jsonl`, `metrics.jsonl`, session `computed:` blocks,
`config/athlete.yaml` and `benchmarks.md`. Byte-identical for identical
inputs; nothing reads the wall clock.

- **Data through** is the status facts' `as_of` (the newest date in the data).
  "Training, last 7 days" and "Baseline this week" are counted back from the
  newest session date instead (daily health metrics usually run ahead of
  workout exports); both tiles are omitted when there are no sessions.
- **Benchmarks table**: one row per dated `benchmarks.md` heading, by the same
  heading rule as the status facts (`### YYYY-MM-DD - <title>`, hyphen, en or
  em dash), with that section's first `- Result:` line (`—` when absent).
- **Anchor tiles** (FTP, LTHR, Zone 2) appear only for anchors that are set.
  Their note is `benchmark <date>` from the newest dated `benchmarks.md`
  heading whose title mentions LTHR or FTP (case-insensitive), else empty.
- **VO2max estimates** carry only the general method caveat for their method
  from `knowledge/reference-values.yaml` (`method_caveats`). What they mean
  for one athlete belongs in that athlete's `benchmarks.md`.
- **Empty states**: with no sessions the per-session charts are omitted and
  the page says `no sessions yet` (likewise `no benchmarks yet`,
  `no baseline activity yet`).

## Timezone rules

- Health sources carry explicit UTC offsets → preserved as-is.
- EXIF `DateTimeOriginal` keeps its UTC offset when the camera recorded one
  (`OffsetTimeOriginal`; iPhones do) → the sidecar `exif_time` is tz-aware and
  a photo taken while traveling matches its workout on the absolute instant.
  Without an offset it is naive and read as the workout's local time.
- Matching compares absolute instants; naive values are localized first.
