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

## elliptical
- Console: Life Fitness touchscreen cardio console (Discover-style; their
  treadmills and bikes share the layout)
- Layout: a metrics strip across the top — Calories | Distance | Time Elapsed |
  Pace | HR — each with a ▾ to switch units; the lower part is the TV/apps
  area. Level sits bottom-left, Speed (mph) bottom-right. When the athlete
  stops, a **Pause** dialog overlays the TV area with a countdown and an "End
  Workout" button; photos are usually taken on this screen, and the strip
  still shows the finished values.
- Units/quirks: Distance in **miles** by default (convert to m). Calories are
  computed from the entered body weight — the strip shows "Enter Weight here
  for Accurate Calories" when none was set; then leave kcal out of the
  extraction (note it) so the Watch value stands. HR reads "---" without a
  chest strap or grip contact. No watts: effort is Level (resistance step) —
  record it in notes. Time Elapsed stops while paused and is the
  authoritative duration; the countdown is the seconds left before the
  console ends the workout by itself, so the photo was taken roughly
  (timeout − countdown) seconds after the athlete stopped — EXIF time runs
  slightly later than the true end (matters for photo-only sessions).
- Known extraction traps: Speed (mph) and Pace are live values and read
  0.0 / blank on the pause screen — never record them as averages (derive
  speed from distance ÷ elapsed if needed); the pause countdown is not a
  metric; the channel list on the right ("24.3 - AMC") is not data.
- Example photos: data/raw/photos/EEE27E9A-*.heic (pause screen)
- Precor variant (touchscreen elliptical/AMT): metrics strip reads Total
  Distance (mi) | Calories | **Time Remaining** (when a timed program runs —
  elapsed = program length − remaining; the Watch duration is the better
  authority) | Strides/Min (live) | Heart Rate (blank without contact). Two
  small numeric displays on the lower panel are resistance/incline-type
  levels, not metrics. A mid-workout photo has no end summary — extract what
  is shown and mark elapsed medium confidence.
  Example photos: data/raw/photos/7E859104-*.heic
