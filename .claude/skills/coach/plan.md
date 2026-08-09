# /coach plan — Next Week's Prescriptions

Outcome: `plans/YYYY-Www.md` (schema in `docs/schema.md`) with prescriptions
the athlete can execute and the system can verify.

## Inputs (read in this order)

1. `goals.md` — active goal track and constraints.
2. `config/athlete.yaml` — anchors (are they bootstrap or field-tested?),
   equipment.
3. `data/index.jsonl` — recent weeks: adherence, compliance scores, trends
   (efficiency factor, decoupling, interval watts).
4. Last `reports/` review (if any) — its next-week adjustment is your starting
   point.
5. `knowledge/styles/*.md` for the track's methods.

## Composition rules

- Polarized skeleton by default (see `knowledge/styles/polarized.md`): the 80%
  easy / 20% hard split, sized to the athlete's realistic weekly slots.
- **Prefer lower verification tiers unless the goal demands otherwise**
  (spec §8): single-machine steady state and erg intervals before mixed-modal.
- Respect each style's frequency ceilings and contraindications (frontmatter).
- Schedule any due field test (zone re-test every 4-6 wks; MAF test monthly if
  MAF framing) as one of the week's slots.
- Adjust volume conservatively: no >10-20% weekly jumps; deload if the review
  flagged fatigue/illness.

## Writing the plan

Frontmatter: `week`, `goal_track`, `prescriptions[]` with `id: YYYY-Www-N`,
`style`, `tier`, `modality`, `scheduled_day`, `targets{}` (numeric, verifiable:
duration_s, hr_band, watts_band/ceiling, bouts, bout_s, recovery_s — targets
the metrics scripts can check).

Body, per prescription: what to do in plain gym language, **why it's in the
week** (adaptation sought), the verification tier stated, and the §9
time-to-benefit context ("this is week 3 of ~6-8 before 4x4 watts should
move"). Anchor targets to field-tested values; if anchors are bootstrap, say
so and keep intensity prescriptions conservative.

Close by summarizing the week to the athlete in 3-5 lines.
