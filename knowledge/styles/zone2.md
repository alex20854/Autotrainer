---
style: zone2
name: Zone 2 / LT1 steady state
protocol:
  structure: continuous
  intensity: "at/just below LT1 (lactate ~1.5-2.0 mmol/L); ~60-70% HRmax; RPE 3-4/10; talk test (full but slightly strained sentences)"
  session_min: [45, 60]
  frequency_per_wk: [3, 4]
  weekly_volume_min: "150-240+ (San Millan argues 300-400 for metabolic optimization)"
primary_adaptations: [mitochondrial biogenesis, fat oxidation, lactate clearance, capillary density, stroke volume, insulin sensitivity]
evidence_grade: B/C
key_sources: ["San Millan (practitioner, ~28 yrs lab observation)", "Attia framing", "polarized literature corroborates high-volume LIT (grade A)"]
machine_suitability:
  excellent: [bikeerg, rowerg, skierg, airdyne, stairclimber, versaclimber, bike, treadmill-walk, run]
  notes: "BikeErg/RowErg preferred: non-impact, clean wattage; incline treadmill walking good for volume"
verification_tier: 1
minimum_effective_dose: "3x/wk x 45-60 min; benefit scales with volume"
time_to_measurable_benefit: "~6-8 wks for first objective signal (watts@HR up, decoupling <5%); mitochondrial/metabolic adaptations compound over months"
consistency_requirement: ">=3x/wk, most weeks, indefinitely — the compounding is the point"
detraining_decay: "slowest of all methods; base built over months survives short breaks"
contraindications: ["none specific; the risk is doing it too hard, not doing it"]
progression_rules:
  - "increase duration first, then power/pace at the same HR (the 'same HR, more watts' signal)"
  - "most common error is drifting too hard — enforce the z2 ceiling and watts cap"
---

# Zone 2 / LT1 Steady State

The base layer. Started first, never really stopped (spec §9). Continuous work
at the highest output sustainable with lactate under ~2 mmol/L, anchored in
practice by the HR z2 band and a per-machine watts ceiling
(`config/athlete.yaml`), refined by the talk test.

**Coaching notes.** This is the slow-compounding method — teach that explicitly
(spec §9 correction #2): the metabolic payoff needs months of consistent
volume. Part of the insulin-sensitizing effect is acute (~24-72 h
post-session), which argues for frequency (>=3x/wk, spread out) on the
metabolic-health track independent of total volume. Verification is the
best-case scenario: steady state is where wrist HR is most accurate, and
machine avg watts + duration give an objective load record. The single best
progress signal is efficiency factor (watts / HR) rising over weeks; single
sessions with decoupling >5% mean the "easy" day wasn't easy or the athlete is
fatigued. Flag too-hard easy days — it's the most common compliance failure.
