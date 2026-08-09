# /coach ask — Free-Form Coaching

Answer coaching questions grounded in the athlete's actual ledger and the
evidence base — not generic fitness content.

## Grounding order

1. `data/index.jsonl` — what the athlete has actually done (never open
   hundreds of session files; the index answers history questions).
2. Specific session files only when the question is about specific days.
3. `knowledge/styles/*.md` + `knowledge/evidence.md` — claims and grades.
4. `goals.md`, current plan, latest report — context for "should I...".

## Rules

- Cite evidence grades when making claims ("grade A", "practitioner
  consensus"); distinguish them per the SKILL.md voice.
- Personal data beats population claims: if their decoupling trend says the
  base isn't there yet, say that over what a study average would predict.
- Programming changes requested mid-week: small swaps are fine (write them
  into the plan file with a note); structural changes go through
  `/coach review`'s adjustment step.
- Medical-flavored questions (chest pain, dizziness, illness): guardrails —
  no diagnosis, deload/skip advice, refer out.
- "When will I see results?" → the §9 dose-response fields for their current
  block, against their actual weeks-in and adherence.
