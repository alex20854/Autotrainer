---
style: norwegian-4x4
name: Norwegian 4x4 intervals
protocol:
  structure: intervals
  work: "4 x 4 min at ~90-95% HRmax (some sources 85-95%)"
  recovery: "3 min active at ~60-70% HRmax"
  total_min: 35-40 (incl. ~10 min warm-up + cool-down)
  frequency_per_wk: [1, 3]
primary_adaptations: [VO2max (stroke volume / cardiac output driven), lactate threshold velocity, endothelial function]
evidence_grade: A
key_sources: ["Helgerud 2007 (MSSE 39:665-71): 8 wks 3x/wk, VO2max +7.2%, SV +10%", "Wisloff 2007 (Circulation 115:3086-94)", "popularized by Rhonda Patrick"]
machine_suitability:
  excellent: [bikeerg, rowerg, skierg, airdyne, stairclimber, versaclimber, treadmill-run, run]
  notes: "BikeErg/RowErg preferred for precise interval wattage and safety at high intensity; incline treadmill running is the classic modality"
verification_tier: 2
minimum_effective_dose: "1x/wk maintains; 2-3x/wk to build"
time_to_measurable_benefit: "~6-8 wks at 3x/wk for ~5-7% VO2max (Helgerud 2007: 8 wks); interval watts improve within 3-4 wks"
consistency_requirement: "miss >2 wks and gains stall"
detraining_decay: "VO2max decay begins ~2-4 wks after stopping (blood-volume/stroke-volume losses first); ~1x/wk maintains"
contraindications: ["never daily — recovery-limited, 3x/wk is the studied ceiling", "uncontrolled cardiovascular symptoms -> refer out"]
progression_rules:
  - "increase pace/power, not duration"
  - "classic error: going too hard on interval 1 and fading — coach even pacing across the four reps"
---

# Norwegian 4x4

The best-studied VO2max builder. Teach the spec §9 correction #1 actively:
**4x4 is the fast method, not the slow one** — measurable VO2max gains in ~6-8
weeks at 3x/week, and it should never be daily.

**Coaching notes.** Primary verification is per-interval avg watts: four
near-equal hard bouts with four recovery dips (bout detection in
`compute_metrics.py` gives the structure; Claude judges whether it matches the
prescription). Wrist HR lags 5-15 s at interval starts, so use the HR trace to
confirm intervals 2-4 plateau near target and never penalize interval-1 HR.
Target watts come from the athlete's demonstrated interval power, progressed
per block.
