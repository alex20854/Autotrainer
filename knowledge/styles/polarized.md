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
key_source_ids: [stoggl-sperlich-2014, seiler-kjerland-2006, seiler-tonnessen-2009]
evidence_grade_code: "A/B"
evidence_grade_split:
  mostly_easy_plus_some_hard: "A"
  strict_polarized_beats_threshold_or_pyramidal: "B"
studied_population: "48 well-trained endurance athletes, baseline VO2peak 62.6, 9 wk (Stoggl & Sperlich 2014); descriptive elite data (Seiler & Kjerland 2006; population detail in knowledge/sources.yaml)"
machine_suitability:
  excellent: [all]
  notes: "naturally maps to erg training: z2 rows/rides for the 80%, 4x4 or short intervals for the 20%"
verification_tier: 1
minimum_effective_dose: "4-5 sessions/wk total with the 80/20 split held [unverified]"
time_to_measurable_benefit: "distribution effects measured over ~9-wk blocks (Stoggl & Sperlich 2014)"
consistency_requirement: "weekly 80/20 audit; grey-zone creep is the failure mode"
detraining_decay: "N/A (meta-structure) — decay follows the constituent methods"
contraindications: ["not enough weekly sessions (<3) to make a distribution meaningful [unverified]"]
progression_rules:
  - "audit sessions-based split weekly from the index (Seiler counts sessions, not minutes)"
  - "enforce 'easy easy, hard hard' — the distribution only works if the 80% is genuinely easy"
  - "caveat: elite base phases are often pyramidal rather than strictly polarized; don't over-fit"
---

# Polarized 80/20

The organizing frame for every goal track's week: a large base of genuinely
easy work plus a small dose of genuinely hard work, with the middle minimized.
Grade A for "mostly easy plus some hard" is the dossier's headline grade,
kept; in the repo it rests on one RCT plus descriptive elite data rather than
multi-RCT corroboration, so treat that A as unconfirmed (evidence.md, Known
weak claims). The stronger claim that strict polarized beats threshold or
pyramidal distributions rests on one RCT in well-trained athletes: grade B
(`evidence_grade_split`; evidence.md Method 2 audit note).

**Coaching notes.** Audit from `data/index.jsonl` on a rolling 4 weeks: count
sessions by intensity classification (z2-dominant time-in-zone = easy; interval
structure or z4+ time = hard; substantial z3 = grey). Alert when grey-zone
minutes creep. The audit is structural and cheap to verify — session counting
plus each session's own tier-1 zone check.
