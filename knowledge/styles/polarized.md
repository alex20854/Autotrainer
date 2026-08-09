---
style: polarized
name: Polarized 80/20 intensity distribution
protocol:
  structure: meta-structure (weekly distribution, not a session type)
  intensity: "~80% of sessions below LT1, ~20% above LT2; deliberately minimize the moderate grey zone"
  frequency_per_wk: [4, 5]
primary_adaptations: [VO2max, time-to-exhaustion, peak power — superior vs threshold-heavy or volume-only in trained athletes]
evidence_grade: A
key_sources: ["Stoggl & Sperlich 2014 (Front Physiol 5:33): POL +11.7% VO2peak vs THR/HVT no further improvement", "Seiler & Kjerland 2006 (descriptive elite data)"]
machine_suitability:
  excellent: [all]
  notes: "naturally maps to erg training: z2 rows/rides for the 80%, 4x4 or short intervals for the 20%"
verification_tier: 1
minimum_effective_dose: "4-5 sessions/wk total with the 80/20 split held"
time_to_measurable_benefit: "distribution effects measured over ~9-wk blocks (Stoggl & Sperlich 2014)"
consistency_requirement: "weekly 80/20 audit; grey-zone creep is the failure mode"
detraining_decay: "N/A (meta-structure) — decay follows the constituent methods"
contraindications: ["not enough weekly sessions (<3) to make a distribution meaningful"]
progression_rules:
  - "audit sessions-based split weekly from the index (Seiler counts sessions, not minutes)"
  - "enforce 'easy easy, hard hard' — the distribution only works if the 80% is genuinely easy"
  - "caveat: elite base phases are often pyramidal rather than strictly polarized; don't over-fit"
---

# Polarized 80/20

The organizing frame for every goal track's week: a large base of genuinely
easy work plus a small dose of genuinely hard work, with the middle minimized.
Grade A: the best-evidenced *structure* in this KB.

**Coaching notes.** Audit from `data/index.jsonl` on a rolling 4 weeks: count
sessions by intensity classification (z2-dominant time-in-zone = easy; interval
structure or z4+ time = hard; substantial z3 = grey). Alert when grey-zone
minutes creep. The audit is structural and cheap to verify — session counting
plus each session's own tier-1 zone check.
