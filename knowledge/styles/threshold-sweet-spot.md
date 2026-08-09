---
style: threshold-sweet-spot
name: Threshold / tempo / sweet spot (LT2, FTP-style)
protocol:
  structure: sustained blocks
  intensity: "sweet spot ~88-94% FTP; threshold ~95-105% FTP; RPE ~7/10, short clipped sentences"
  sessions: "2-3 x 15-20 min sweet spot, or over-unders (e.g. 10 min alternating 90%/105% FTP)"
  frequency_per_wk: [2, 3]
primary_adaptations: [lactate threshold, mitochondrial density, capillarization, muscular endurance]
evidence_grade: B/C
key_sources: ["strong practitioner record (Overton/FasCat, Hunter Allen)", "Seiler's data favor polarized over threshold-heavy in trained athletes"]
machine_suitability:
  excellent: [bikeerg, rowerg, bike, treadmill-run]
  notes: "ideal for erg work — wattage targeting is precise; Symbio bikes with FTP fields work"
verification_tier: 1
minimum_effective_dose: "2x/wk during a block"
time_to_measurable_benefit: "~4-8 wks for FTP/threshold-watt gains"
consistency_requirement: ">=2x/wk during a block"
detraining_decay: "moderate; 1x/wk maintains"
contraindications: ["does NOT raise the VO2max ceiling — needs z5 work alongside to avoid plateau", "grey-zone fatigue: cap at 2-3 sessions/wk (ceiling, not floor)"]
progression_rules:
  - "verify avg watts fall in the 88-94% FTP band; drift above threshold turns the session into junk fatigue"
  - "progress FTP via field test every 4-6 wks, then recompute bands"
---

# Threshold / Sweet Spot

Time-efficient aerobic stimulus for the metabolic-health track and FTP
progression. Sits in the grey zone by design, so it's rationed — Seiler's
skepticism is on record (evidence.md), and the coach should say so when
prescribing it.

**Coaching notes.** Fully watt-verifiable on ergs (tier 1): avg watts vs the
FTP band, plus stable HR corroboration. Requires a real FTP anchor in
`config/athlete.yaml` — do not prescribe from formula-derived values.
