# /coach plan — Next Week's Prescriptions

Outcome: `plans/YYYY-Www.md` (schema in `$ENGINE/docs/schema.md`) with prescriptions
the athlete can execute and the system can verify.

## Inputs (read in this order)

1. `"$PY" "$ENGINE/scripts/status.py" --json --as-of <today>` — goal, current week, weekly
   volume and consistency, days since the last structured session, anchors,
   benchmark age, recovery context.
2. `goals.md` — active goal track and constraints.
3. `config/athlete.yaml` — anchors (are they bootstrap or field-tested?),
   equipment. `benchmarks.md` notes for how each anchor was obtained.
4. `data/index.jsonl` — recent weeks: compliance scores, trends
   (efficiency factor, decoupling, interval watts).
5. Last `reports/` review (if any) — its next-week adjustment is your starting
   point.
6. `$ENGINE/knowledge/styles/*.md` for the track's methods; `adapt.md` for
   layoffs, missed sessions, illness signals, deloads and progression.
7. `$ENGINE/knowledge/modalities.md` for each modality you prescribe on (its
   output metric, how far wrist HR can be trusted, the realistic tier) and
   `$ENGINE/knowledge/protocols.md` for any field test you schedule (steps,
   which machines it suits, its biases, the anchors it yields).

## No active goal

When `goal.active` is false, do not stall: write a 1-2 week **re-entry
block** from `adapt.md` §1 (rung chosen by recency and recent volume; with no
plan to resume, ≤ 7 days means hold recent frequency and session lengths, and
a null `days_since_last_structured` means a new athlete on HR-only
provisional targets) — easy aerobic work only, no intervals. Frontmatter
`status: draft`, `goal_track: pending`. Draft plans are never
compliance-scored; the plan body says so in its first line, and recommends
`/coach setup` before the block ends.

## Composition rules

- Polarized skeleton by default (see `$ENGINE/knowledge/styles/polarized.md`): the 80%
  easy / 20% hard split, sized to the athlete's realistic weekly slots.
- **Prefer lower verification tiers unless the goal demands otherwise**
  (spec §8): single-machine steady state and erg intervals before mixed-modal.
- **Interval tier honesty** (SKILL.md guardrail): bouts < 2 min need machine
  metrics (PM5 interval-summary photo or Concept2 trace) — no HR sensor
  verifies them; where no machine data will exist, swap short-bout styles for
  steady work or bouts ≥ 2 min rather than downgrading the tier. Bouts ≥ 2 min:
  machine metrics first, HR trace shape secondary. State which evidence the
  tier rests on.
- Respect each style's frequency ceilings and contraindications (frontmatter).
- Schedule any due field test (zone re-test every 4-6 wks; MAF test monthly if
  MAF framing) as one of the week's slots — only once `adapt.md` §1's
  intensity gate is met (`consistency.current_streak_weeks` ≥ 2 on a re-entry
  rung or after a zero streak), not when re-entry's calendar length ends.
  Write the protocol from `$ENGINE/knowledge/protocols.md`; on a machine it
  records no protocol for, say so rather than improvising one.
- Progression, holds and deloads: decide per `adapt.md` §6 and the styles'
  `progression_rules`. Weekly volume jumps stay within 10-20%
  `[grade D - practitioner heuristic, unverified]`.

## Targets

- Read targets from `config/athlete.yaml`: HR bands from `zones.bands` × LTHR;
  watts from `power.<modality>.ftp` and `z2_watts_ceiling`.
- A modality with no `power.<modality>` anchors gets HR **ceilings** only
  (`hr_ceiling` at or below the top of the z2 band, no `hr_band` floor),
  marked provisional — the LTHR came from another modality and transfers only
  approximately (`adapt.md` §4-§5; `$ENGINE/knowledge/modalities.md`, Across
  modalities). Hard HR bands on that modality wait for a
  calibration benchmark there (unless the LTHR test itself was on it).
- When the benchmark notes say the test was sub-maximal or limiter-affected,
  the anchor is a floor: describe targets built on it as "at least", and
  watts ceilings derived from it as conservative.
- If anchors are bootstrap (formula), say so and keep intensity
  prescriptions conservative.

## Writing the plan

Frontmatter: `week`, `status` (`active`, or `draft` for a no-goal block),
`goal_track`, `prescriptions[]` with `id: YYYY-Www-N`, `style`, `tier`,
`modality`, `scheduled_day`, `targets{}` (numeric, verifiable: duration_s,
hr_band, hr_ceiling, watts_band/ceiling, bouts, bout_s, recovery_s — targets
the metrics scripts can check).

Body, per prescription: what to do in plain gym language, **why it's in the
week** (adaptation sought), the verification tier stated, and the §9
time-to-benefit context ("this is week 3 of ~6-8 before 4x4 watts should
move"). Leave an `## Adaptations` heading for mid-week changes (`adapt.md` §7).

Close by summarizing the week to the athlete in 3-5 lines.
