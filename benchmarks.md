# Benchmarks

Dated field-test results, newest first. This is the human-readable log; the
*current* anchors derived from it live in `config/athlete.yaml` (which scripts
read). When a test is recorded here, update athlete.yaml in the same commit.

Recommended protocol cadence: re-test zones every 4–6 weeks (dossier,
Compliance Verification section). Formulas (220−age, 180−age) are bootstrap
only — a field LTHR/FTP test replaces them (spec §11).

Test menu:
- **LTHR/FTP field test** (primary erg): 20–30 min TT; LTHR = avg HR of final
  20 min; FTP ≈ 95% of 20-min avg watts.
- **MAF test**: fixed 5 km erg at MAF-cap HR; record time/avg watts.
- **2k row** (or modality benchmark): all-out; record time/avg watts/avg HR.
- **Resting HR**: weekly morning average from Health data.

## Results

### 2026-08-14 — VO2max triangulation (three methods)
- Result: power floor **30.7** (leg-limited 20-min test, ACSM); Apple Watch
  Cardio Fitness **33.4** (walk-derived, under-reads casual walkers);
  Uth–Sørensen HR-ratio **~51** (15.3 × 185 ÷ 55, tends optimistic).
- Conditions/notes: honest verdict — true value most likely mid-to-upper 30s.
  Resting HR 52-55 (athletic range); RHR spiked 52→63 for two days after the
  08-11 field test (recovery signal). Sources: data/derived/metrics.jsonl.
- athlete.yaml updated: yes — hr_resting 55.

### 2026-08-11 — LTHR/FTP field test (concept2-bikeerg)
- Result: 20:06 @ **150 W avg**, 9,095 m (PM5). HR built 147→161 over the final
  15 min, max 170; **LTHR = 157** (final-10-min avg from the HR series).
  **FTP = 142 W** (95% of 20-min avg).
- Conditions/notes: short untracked warm-up; even pacing, good execution.
  **Athlete report: the limiter was quad fatigue, not cardiovascular
  capacity — cardio-wise the effort was not very challenging.** Confirms
  the sub-maximal read from the HR trace (final HR well under >=176 max).
  Interpretation: the BikeErg power number is real but leg-endurance-bound
  (peripheral limiter); the HR-side threshold is likely underestimated.
  Both anchors stand as conservative floors. Re-test fresh after several
  easy days; consider a separate short HR-ceiling probe on the Airdyne
  (legs can't cap it). Record: health-2026-08-11T210335-indoor-cycling.
- athlete.yaml updated: yes — lthr 157; power.bikeerg.ftp 142.

### 2026-08-10 — observed max HR (bikeerg, informal)
- Result: HR max **176 bpm** observed during a 22-min easy ride finished with a
  hard surge over the last few minutes.
- Conditions/notes: athlete was fatigued; reports confident headroom into the
  180s, possibly 190s, when fresh. Treat 176 as a floor, not the max.
  (The 176 came in a 1.7-min all-out burst logged separately —
  record health-2026-08-10T212716-elliptical; kept out of the session
  ledger as a benchmark probe, not training.)
- athlete.yaml updated: yes — hr_max set to 185 (athlete-estimated midpoint,
  BOOTSTRAP ONLY until the LTHR/FTP field test).

### 2026-08-10 — subjective watt calibration (bikeerg)
- Athlete report: 100–115 W very comfortable; effort becomes noticeably
  harder around 125–135 W. Agrees independently with the decoupling
  evidence (<=128 W clean, 133 W+ decoupled) — LT1 sits near ~130 W.
- athlete.yaml updated: z2_watts_ceiling 130 confirmed (still bootstrap).

Entry template:

```
### YYYY-MM-DD — <test> (<machine>)
- Result: ...
- Conditions/notes: ...
- athlete.yaml updated: yes/no (fields)
```
