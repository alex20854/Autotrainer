# Machine Console Reference

The growing per-machine example file (spec §15): every time vision extraction
meets a console, record what its display shows and where, so future
extractions get faster and more accurate. Add an entry (or refine one) whenever
a new console layout appears or an extraction error gets corrected.

Entry format:

```
## <machine id>            (matches config/athlete.yaml equipment / sidecar `machine`)
- Console: <model, e.g. Concept2 PM5>
- Layout: which fields appear where on the end-of-workout screen
- Units/quirks: pace basis (per 500m?), cal vs kcal, rest handling, rollover
- Known extraction traps: <what vision got wrong before, and the correction>
- Example photos: data/raw/photos/<...>
```

## concept2-bikeerg
- Console: Concept2 PM5 (cadence unit "rpm" identifies BikeErg vs RowErg/SkiErg "s/m")
- Layout, standard screen (top→bottom): elapsed time | current rpm; current
  watts; **ave watt** (the session average — the value to extract as
  watts_avg); total meters; last-split watts ("split watt" — NOT the average);
  "projected m" with the projection window (30:00 or 1:00:00 — a projection
  basis, not evidence the piece was that long).
- Alternate screens seen: large-format (time/current watts/ave watt/rpm only —
  no distance); bar-chart (time/current/ave watt + per-split bars); calorie
  screen (Cal/hr and total Cal, no watts/distance).
- Units/quirks: photos are usually taken at the end with rpm 0 and current
  watts decaying — ignore current watts, read "ave watt". Multiple photos of
  different screens for the same workout are common (same elapsed time on
  each) — merge them into one session, never two.
- Known extraction traps: "split watt" next to distance is easily mistaken for
  average watts; the projected-meters line is easily mistaken for distance.
- Example photos: data/raw/photos/020BACC7-*.jpeg (standard),
  data/raw/photos/B688AEDA-*.heic (large-format),
  data/raw/photos/DBD2F37E-*.jpeg (bar-chart),
  data/raw/photos/16392DF7-*.heic (calorie screen)

## airdyne
- Console: Schwinn Airdyne (AD series) — RPM dial up top, digital panel below
- Layout: digital panel shows TIME (mm:ss), CALORIE (total), HEART RATE (0
  unless a strap is paired). Side buttons select interval modes (20/10, 30/90)
  and targets.
- Units/quirks: no distance or watts on the end screen photographed; calories
  are the primary output metric. HR 0 means no strap, not zero HR.
- Known extraction traps: none yet.
- Example photos: data/raw/photos/8AE94715-*.jpeg
