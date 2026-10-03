# Field-Test Protocols

The field tests the repo already names — the workspace test menu
(`templates/workspace/benchmarks.md`) and the VO2max estimate methods
(`reference-values.yaml`) — written out once, with what each one can and
cannot tell. **No new protocols are introduced here**; where a machine has no
recorded protocol, this file says so.

Results go in the workspace `benchmarks.md` (dated, with conditions and
limiter notes); anchors derived from them go in `config/athlete.yaml` in the
same commit. Tags: grades per the `evidence.md` legend; `[unverified]` = no
source in the repo; source ids point into `sources.yaml`.

**Two rules that apply to every test** (`skills/coach/SKILL.md` guardrails):
an anchor from a sub-maximal or limiter-affected test is a **floor** ("at
least"), and formula anchors (220−age, 180−age) are bootstrap only until a
field test replaces them. Test timing after a layoff follows the intensity
gate in `skills/coach/adapt.md` §1.

## LTHR / FTP field test (primary erg)
- **Purpose**: individual zone anchors — the practical default for this
  system (`evidence.md`, HR-zone anchoring approaches: "more individualized;
  good reliability"; dossier statement, unsourced, no letter grade
  [unverified]).
- **Steps** (as in `benchmarks.md`): a 20–30 min time trial on one machine;
  LTHR = average HR of the final 20 min; FTP ≈ 95% of the 20-min average
  watts. The 95% factor and the final-20-min rule are practitioner
  conventions with no source in the repo [unverified].
- **Machines**: LTHR on any machine with steady wrist or strap HR; FTP only
  on a machine that reports watts (bikeerg; rowerg/skierg in watts mode;
  a bike with a power readout). On machines without watts (airdyne,
  elliptical, stairclimber, versaclimber, treadmill-walk, sled) **no
  validated FTP-type protocol is recorded**; an LTHR from a time trial there
  has not been examined in this knowledge base [unverified].
- **Biases and limiters**: a power test can be limited by local muscle
  fatigue rather than cardiorespiratory capacity (`modalities.md` bikeerg),
  so its anchors are floors; poor pacing (too hard early) lowers the
  20-min average [unverified]; the result is modality-specific — the LTHR
  transfers only approximately and the FTP not at all (`modalities.md`,
  Across modalities; grade D practitioner heuristic [unverified]). Steady-state wrist HR is the favourable case for
  optical HR (dossier Method 1).
- **Anchors yielded**: `lthr`; `power.<modality>.ftp` and, from it, the z2
  watts ceiling the athlete config holds (`docs/schema.md`).
- **Cadence**: re-test every 4–6 weeks (dossier [unverified]); after a long
  layoff, once the intensity gate is met (`skills/coach/adapt.md` §1).
- **Verification tier**: 1 (single machine, continuous; spec §8).
- **Evidence grade**: no letter grade in the dossier, which ranks field
  tests above formulas and below lab testing ("more individualized; good
  reliability" — unsourced); the conversion factors are [unverified].

## MAF test
- **Purpose**: a progress benchmark at a fixed HR cap — not an anchor
  (`styles/maf.md`).
- **Steps** (as in `benchmarks.md` and `maf.md`): a fixed 5 km on an erg
  held at the MAF-cap HR; record time and average watts (or pace).
- **Machines**: needs a distance readout — the Concept2 ergs, treadmills,
  ellipticals with a distance field. On a machine without distance (the
  airdyne's photographed console) **no MAF protocol is recorded**.
- **Biases and limiters**: the cap itself comes from the 180−age formula,
  which can misestimate individuals by ±5+ bpm (`maf.md`, attributed to an
  unidentified 2023 analysis — `sources.yaml` jcm-2023); day-to-day HR
  confounders shift the result at a fixed cap (`readiness.md`, Confounders);
  compare only on the same machine.
- **Anchors yielded**: none; the trend is the output.
- **Cadence**: monthly (`maf.md` progression_rules).
- **Verification tier**: 1.
- **Evidence grade**: the test itself is a measurement and is not graded;
  the formula behind the cap is D, the easy-means-easy principle C (`maf.md`
  evidence_grade_split).

## 2k row (or modality benchmark)
- **Purpose**: an all-out performance benchmark; the anchor that block-style
  erg programming keys paces to (`styles/carson-engine.md`,
  `styles/hinshaw-pace-diversity.md`).
- **Steps** (as in `benchmarks.md`): all-out 2000 m; record time, average
  watts (or pace) and average HR.
- **Machines**: rowerg. "Or modality benchmark" names no protocol for other
  machines — **none is recorded**.
- **Biases and limiters**: pacing skill and technique strongly shape the
  result [unverified]; an all-out effort of this length relies on more than
  aerobic capacity [unverified]; average HR over a short all-out effort is
  dragged down by the optical lag at the start (dossier; lag figure
  [unverified]) — record it, do not anchor zones on it.
- **Anchors yielded**: the benchmark time/watts for pace-keyed programming;
  no HR anchor.
- **Cadence**: at block end (`carson-engine.md` progression_rules).
- **Verification tier**: 1 — the PM5 result is the record (photo or trace).
- **Evidence grade**: inherits `carson-engine.md`'s D — practitioner practice.

## Resting HR
- **Purpose**: recovery context and an input to the HR-ratio VO2max estimate.
- **Steps** (as in `benchmarks.md`): weekly morning average from Health data.
  The status facts already report 7- and 28-day medians
  (`scripts/lib/facts.py` recovery; `readiness.md`).
- **Machines**: none — a wearable measurement.
- **Biases and limiters**: see `readiness.md` — single readings are noisy,
  device and measurement conditions vary [unverified].
- **Anchors yielded**: `hr_resting` (athlete config).
- **Cadence**: continuous, read weekly.
- **Verification tier**: not applicable (passive data).
- **Evidence grade**: see `readiness.md`.

## Talk test (Zone 2 refinement)
- **Purpose**: refine the top of Zone 2 inside a field-tested band.
- **Steps** (dossier Method 1): at Zone 2 the athlete can speak in full but
  slightly strained sentences.
- **Machines**: any.
- **Biases and limiters**: subjective; a refinement, not an anchor.
- **Anchors yielded**: none (adjusts the z2 ceiling judgement).
- **Cadence**: any steady session.
- **Verification tier**: self-report only; never scores a tier 1–2
  prescription (spec §5).
- **Evidence grade**: not graded; a practitioner recommendation (San Millán
  prefers it over formulas — dossier Method 1; `sources.yaml` san-millan-nd).

## VO2max estimates (dashboard comparison only)

Estimates, not tests. The dashboard shows each beside its method caveat
(`reference-values.yaml` method_caveats). None yields a training anchor.

### Power estimate (BikeErg 20-min test)
- **Steps** (as in `reference-values.yaml`): 20-min power ≈ FTP / 0.95;
  power at VO2max ≈ P20 / 0.85; ACSM leg-cycling VO2 = 10.8 × W / kg + 7.
- **Machines**: BikeErg (a leg-cycling equation). For the rower, ski erg or
  any machine without watts **no validated estimate protocol is recorded**.
- **Biases**: an effort short of truly maximal reads low; local leg fatigue
  can cap the test below cardiorespiratory capacity (`modalities.md`); the
  two power ratios have no source in the repo [unverified]; the ACSM equation
  is named but not checked (`sources.yaml` acsm-nd).
- **Evidence grade**: C (as `reference-values.yaml` grades it).

### Heart-rate ratio estimate (Uth–Sørensen)
- **Steps**: 15.3 × HRmax ÷ resting HR.
- **Source**: the 15.3 factor matches the Uth 2004 abstract, derived in
  well-trained men (`sources.yaml` uth-2004, claim checked).
- **Biases**: needs an accurately measured HRmax — a formula HRmax makes it
  meaningless; resting HR is noisy (`readiness.md`); individual error can be
  large (`reference-values.yaml` [unverified]).
- **Evidence grade**: not graded in the dossier; the factor rests on one
  validation study in well-trained men, and applicability to other
  populations is [unverified].

### Watch estimate
- **Steps**: none — the device maker models it from HR and movement during
  recorded activities; the method is proprietary.
- **Biases**: unknown for an individual (`reference-values.yaml`
  [unverified]); read the trend, not the number.
- **Evidence grade**: not gradable from the repo.
