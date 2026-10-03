# /coach ask — Free-Form Coaching

Answer coaching questions grounded in the athlete's actual ledger and the
evidence base — not generic fitness content.

## Grounding order

1. `data/index.jsonl` — what the athlete has actually done (never open
   hundreds of session files; the index answers history questions).
   `data/baseline.jsonl` for "how much am I moving overall" — unstructured
   walks/movement live there, not in the session ledger.
2. Specific session files only when the question is about specific days.
3. `$ENGINE/knowledge/styles/*.md` + `$ENGINE/knowledge/evidence.md` — claims and grades.
4. `goals.md`, current plan, latest report — context for "should I...".

## Rules

- Cite evidence grades when making claims ("grade A", "practitioner
  consensus"); distinguish them per the SKILL.md voice.
- Personal data beats population claims: if their decoupling trend says the
  base isn't there yet, say that over what a study average would predict.
- Decoupling in the index carries `decoupling_method`: `hr_drift` is
  heart-rate drift without a power trace, not decoupling — don't compare it
  with the 5% decoupling convention or call it decoupling. Read decoupling
  or drift trends only from steady (Tier 1) sessions. A null always carries
  `decoupling_note`: `window_too_short` means the session was too short to
  judge durability (steady sessions of 30+ minutes are needed);
  `modality_excluded`, `not_steady` (intervals) and `insufficient_samples`
  mean not measured. None of them is a failure.
- Programming changes requested mid-week: small swaps are fine (write them
  into the plan file with a note); structural changes go through
  `/coach review`'s adjustment step.
- Medical-flavored questions (chest pain, dizziness, illness): guardrails —
  no diagnosis, deload/skip advice, refer out.
- "When will I see results?" → the §9 dose-response fields for their current
  block, against their actual weeks-in and adherence.
