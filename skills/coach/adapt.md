# /coach adapt — Layoffs, Missed Sessions, Illness, Travel, New Machines

Outcome: the current or next plan changed to fit what actually happened, with
the reason written into the plan file. Read the status brief first (SKILL.md);
every fact below comes from `status.py --json`, never from hand arithmetic.

**Grade tags.** Every rule carries one: a pointer to the knowledge file that
supports it, or `[grade D - practitioner heuristic, unverified]`. Numeric
cut-points marked as defaults are engine choices, not findings — adjust them
for the athlete and say that you did. Never present a default as evidence.

## 1. Return after a layoff

Status must be run `--as-of` today (SKILL.md first step), or a layoff reads
as zero days. Pick the rung from **recency and recent volume**, taking the
more conservative of the two (day ranges and the volume test are grade D
defaults; the shape — interval fitness fades in weeks, base fades slowly —
follows `$ENGINE/knowledge/styles/norwegian-4x4.md` `detraining_decay` /
`consistency_requirement` and `zone2.md` `detraining_decay` — whose numbers
are themselves `[unverified]`; `$ENGINE/knowledge/readiness.md`, Detraining,
summarises them with their grades):

- **Recency**: `sessions.days_since_last_structured` against the table.
- **Volume**: when `consistency.current_streak_weeks` is 0 and the two weeks
  before the current one in `weeks` both have `structured_sessions` below
  `consistency.threshold_sessions`, the rung is at least **Re-entry** — one
  short session after weeks off does not reset the ladder
  `[grade D - practitioner heuristic, unverified]`. If the threshold does not
  match the athlete's realistic frequency, it is set in `config/athlete.yaml`
  `status.consistency_sessions`; say so rather than ignoring the test.

| Days | Rung |
|---|---|
| ≤ 7 | **Resume** the plan as written. No current plan (no goal, or first plan): hold the frequency of the last 2-4 `weeks` (`structured_sessions`) and session lengths from those weeks' index rows (`duration_s`), easy aerobic only. |
| 8-14 | **Repeat** the last completed week (or the last ledger week with structured work) at the low end of its durations and targets. |
| 15-28 | **Re-entry**: 1 week, rules below. |
| > 28, or null | **Long re-entry**: 2+ weeks, then retest anchors before prescribing by zone or power. Null (no structured session in the ledger) is a new athlete: HR-only, provisional, from bootstrap anchors (`setup.md` §2). |

`[grade D - practitioner heuristic, unverified]` for all four cut-points.

**Intensity gate**: no intervals and no field test until
`consistency.current_streak_weeks` ≥ 2. It always applies on the re-entry
rungs, and on Resume and Repeat whenever the streak is 0
`[grade D - practitioner heuristic, unverified]`.

Re-entry rules:
- Easy aerobic only — `zone2` style, HR ceiling at or below the top of the z2
  band from `config/athlete.yaml` zones × LTHR
  (`$ENGINE/knowledge/styles/zone2.md` progression_rules: enforce the ceiling).
- **Frequency before duration**: restore sessions per week first, at durations
  at or below the shortest of the athlete's recent structured sessions (read
  `duration_s` from their last few structured rows in `data/index.jsonl`);
  lengthen only once frequency holds (`zone2.md` progression_rules: duration
  first; ordering vs frequency `[grade D - practitioner heuristic, unverified]`).
- Long re-entry: power anchors are stale — use them as ceilings, not targets,
  until the retest lands in `benchmarks.md` and `config/athlete.yaml`
  (`$ENGINE/knowledge/styles/hinshaw-pace-diversity.md`
  consistency_requirement: stale benchmarks mean wrong paces).
- **Retest timing**: schedule the retest in the first week after the intensity
  gate is met — not first, and not merely after re-entry's calendar length
  `[grade D - practitioner heuristic, unverified]`.

## 2. Missed sessions

- **Never stack hard sessions**: no two hard sessions on one day or on
  consecutive days (`$ENGINE/knowledge/styles/polarized.md` "easy easy, hard hard";
  `norwegian-4x4.md` contraindications: recovery-limited, never daily; the
  consecutive-day rule `[grade D - practitioner heuristic, unverified]`).
- Move a missed hard session **at most once**, to a day not adjacent to
  another hard session; otherwise drop it
  `[grade D - practitioner heuristic, unverified]`.
- Drop a missed easy session rather than doubling another day's
  (`zone2.md` coaching notes: frequency spread out matters on the metabolic
  track; no-doubling `[grade D - practitioner heuristic, unverified]`).
- The week is scored as it happened: a moved session is scored against its
  original prescription; a dropped one scores 0 with the reason (`review.md`).
- Repeated misses of the same slot are a planning problem — raise it at review
  and re-size the week, rather than carrying the debt forward.

## 3. Illness signals and recovery context

Background — what these numbers can and cannot show, rolling baselines,
wearable HRV caveats and the confounders of HR drift:
`$ENGINE/knowledge/readiness.md`.

- Context, not diagnosis: `recovery.resting_hr.days_elevated` (as `status.py`
  defines it against `elevated_threshold_bpm`, an engineering default) and the
  HRV `delta_vs_28d`. State the n behind each median; thin data is weak evidence.
- `days_elevated` ≥ 2, or symptoms the athlete reports → that day is easy or
  off; no intervals until both clear (spec §15 guardrail "deload on illness
  signals"; the 2-day trigger `[grade D - practitioner heuristic, unverified]`).
- A low HRV delta alone is context to mention, not a trigger
  `[grade D - practitioner heuristic, unverified]`.
- Chest pain, dizziness, fainting, palpitations, or symptoms that persist:
  stop training and refer out. Never diagnose (SKILL.md guardrails).
- Days lost to illness count toward the layoff ladder (§1): count from the
  illness start the athlete reports — an easy session during the illness does
  not reset the count `[grade D - practitioner heuristic, unverified]`.

## 4. Travel and unfamiliar equipment

- On any machine without `power.<modality>` anchors, prescribe by HR only —
  conservative ceilings at or below the top of the z2 band, tier 1 for
  continuous work `[grade D - practitioner heuristic, unverified]`.
- Unfamiliar watts or pace never compare with home machines: each console
  reports output on its own basis (`$ENGINE/knowledge/modalities.md`, Across
  modalities) `[grade D - practitioner heuristic, unverified]`.
- Ask for a console photo after every session (it identifies the machine and
  feeds `$ENGINE/knowledge/machines.md` if the console is new).
- Intervals on hotel or unknown machines: tier per the SKILL.md interval rule;
  without machine evidence, prefer steady work that week.
- A baseline collapse in a travel week is context, not a miss (`review.md`).

## 5. A new machine

- **Onboarding** (once): one console photo, and one Watch workout type the
  athlete will always use for it — add the machine to `equipment` and the type
  to `matching.modality_map` in `config/athlete.yaml`. If the modality is not
  in the schema vocabulary, stop: that is an engine change
  (`$ENGINE/docs/schema.md`, Modality vocabulary).
- **First sessions**: easy, HR-capped, stated as conservative ceilings — not
  zone targets — because the LTHR came from another modality and transfers only
  approximately (`$ENGINE/knowledge/modalities.md`, Across modalities)
  `[grade D - practitioner heuristic, unverified]`.
- **Calibration benchmark** only after 2-3 familiarisation sessions
  `[grade D - practitioner heuristic, unverified]`, using the `benchmarks.md`
  protocol (`$ENGINE/knowledge/protocols.md`); then set `power.<modality>` if
  the console reports watts, else the machine stays HR-only — no validated
  protocol is recorded for machines without watts.
- Add a `$ENGINE/knowledge/machines.md` entry from the first console
  photo — console layout and quirks only, never athlete data (`workspace.md`,
  Where new knowledge goes).

## 6. Deloads

- **When**: on signals, not a calendar — efficiency factor falling or
  decoupling rising at the same watts across weeks, illness signals (§3),
  accumulating misses, athlete-reported fatigue, or a block end where the
  style's own structure calls for it (`$ENGINE/knowledge/styles/carson-engine.md`
  progression_rules: re-test at block end). The KB holds no graded deload
  frequency; do not invent one.
- **How**: keep frequency, cut volume, and hold each hard style at the
  maintenance dose its `detraining_decay` field names (e.g. `norwegian-4x4.md`:
  ~1x/wk maintains). The size of the cut is your judgment — state it in the
  plan `[grade D - practitioner heuristic, unverified]`.
- A due retest fits a deload week `[grade D - practitioner heuristic, unverified]`.

## 7. Write it down

- Every adaptation goes in the plan file body under `## Adaptations`: date,
  what changed, the status facts that drove it, and its grade tag.
- Edit the prescription's frontmatter (`scheduled_day`, `targets`) when a
  session moves or changes, keeping its `id`; a dropped prescription stays in
  the frontmatter and is noted as dropped in the body.
- Hand edits to session files set `match_method: claude` with the reason in
  the body (`workspace.md` rule 7).
- Structural changes (new block, new goal) go through `/coach review` or
  `/coach setup`, not here.
