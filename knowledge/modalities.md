# Modalities

One short section per label in the modality vocabulary
(`scripts/build_index.py` `MODALITIES`, `docs/schema.md`). For each: what
usually limits effort, which output metric the machine gives, how far wrist
optical HR can be trusted there, how steep the technique curve is, and which
verification tier (spec §8) is realistic. Console details live in
`machines.md`; field tests in `protocols.md`.

**Tags.** Grades follow the `evidence.md` legend (A–D). `[unverified]` marks a
statement with no source in the repo — most of this file is general
physiology and coaching consensus, stated qualitatively on purpose. No
physiological numbers are introduced here.

**Wrist-HR background** (applies to every section; detail in `evidence.md`,
Compliance Verification): wrist optical HR is most trustworthy in steady
state and least trustworthy at sharp transitions, with a lag of several
seconds (the dossier's 5–15 s figure is [unverified]); grip compression
corrupts it (dossier, unsourced [unverified]); vigorous wrist and arm motion
degrades it (dossier: "accuracy degrades with motion/sweat" [unverified]).
**Cadence lock** — the optical sensor locking onto a rhythmic movement
cadence instead of the pulse, producing a plausible-looking but wrong HR — is
a known practitioner concern on rhythmic modalities; nothing in the repo
grades it [unverified]. A trace that sits flat at one value while effort
changes, or jumps to a new level without a change in effort, is the cue to
treat that session's HR as suspect.

## rowerg
- **Limits effort**: whole-body, leg-driven work with a large technique
  component; poor technique can make the arms and back fail before the
  cardiorespiratory system [unverified].
- **Output metric**: pace per 500 m by default, switchable to watts or
  Calories on the PM5 (`machines.md` concept2-rowerg; concept2-pm5-101).
- **Wrist HR**: the hands grip the handle and the wrists flex every stroke —
  grip and arm drive both apply; steady-state averages are usable for trends,
  short-bout HR is not [unverified]. A chest strap paired to the PM5 is the
  open question in `docs/backlog.md`.
- **Technique curve**: moderate to steep — stroke sequencing matters for
  output [unverified].
- **Realistic tier**: 1 for continuous work, 2 for intervals with PM5
  interval data or a Concept2 trace (spec §8; `skills/coach/SKILL.md`).

## skierg
- **Limits effort**: upper body and trunk carry more of the work than on the
  rower, so local arm and trunk fatigue can arrive before cardiorespiratory
  limits [unverified].
- **Output metric**: PM5 pace / watts / Calories, as the RowErg
  (`machines.md` concept2-skierg — SkiErg screen still unconfirmed).
- **Wrist HR**: strong arm drive and grip on the handles — the least
  favourable erg for wrist optical HR [unverified]; prefer machine output
  for any verification.
- **Technique curve**: moderate [unverified].
- **Realistic tier**: 1 continuous, 2 intervals with machine data (spec §8).

## bikeerg
- **Limits effort**: legs only; local leg fatigue can end a maximal test
  before the cardiorespiratory system does [unverified], so a power test can
  understate cardiorespiratory capacity (`reference-values.yaml`
  method_caveats: an effort short of truly maximal reads low).
- **Output metric**: watts (`machines.md` concept2-bikeerg); pace per 1000 m
  is the PM5's pace basis here (concept2-pm5-101).
- **Wrist HR**: hands rest on the bars with little wrist motion — the most
  favourable erg for wrist HR in steady state (dossier Method 1:
  steady state is where optical HR is most accurate; npj Digital Medicine
  2025, claim not checked — `sources.yaml` lambe-2025).
- **Technique curve**: shallow [unverified].
- **Realistic tier**: 1 continuous, 2 intervals — with the RowErg, the
  dossier's preferred machine for precise interval wattage (`evidence.md`
  Method 3).

## airdyne
- **Limits effort**: arms and legs together against fan resistance that
  rises steeply with speed; all-out efforts become very hard very fast
  [unverified].
- **Output metric**: calories and an RPM dial; no watts or distance on the
  end screen photographed so far (`machines.md` airdyne).
- **Wrist HR**: push-pull handles — grip and arm drive apply [unverified];
  the console HR reads 0 without a paired strap (`machines.md`).
- **Technique curve**: shallow [unverified].
- **Realistic tier**: 1 for continuous work by HR; intervals rest on HR trace
  shape only (no per-interval machine output recorded yet), so bouts under
  2 min cannot be tier 2 here (`skills/coach/SKILL.md` interval rule).

## stairclimber
- **Limits effort**: legs carrying body weight; local leg fatigue and
  balance limit hard efforts [unverified].
- **Output metric**: unknown — no console entry in `machines.md` yet; the
  Watch's stair-climbing type gives HR and kcal only.
- **Wrist HR**: depends on handrail use — gripping the rails adds compression
  [unverified].
- **Technique curve**: shallow [unverified].
- **Realistic tier**: 1 for continuous work by HR (`zone2.md` lists it as
  excellent); intervals by HR shape only.

## versaclimber
- **Limits effort**: simultaneous arm and leg climbing; local fatigue in
  both [unverified].
- **Output metric**: unknown — `machines.md` versaclimber is an
  UNCONFIRMED stub until a console photo exists.
- **Wrist HR**: full grip with strong arm drive — grip and arm motion both
  apply [unverified].
- **Technique curve**: steep for many newcomers — coordination of the
  climbing pattern [unverified].
- **Realistic tier**: 1 for continuous work by HR once onboarded
  (`skills/coach/adapt.md` §5); nothing better until the console is known.

## bike
- **Limits effort**: legs only, as the BikeErg [unverified].
- **Output metric**: varies by bike — some gym bikes show watts and accept an
  FTP (dossier Method 4 mentions FTP fields); outdoor bikes give pace or
  speed from the Watch unless a power meter exists. Treat each bike's watts
  as its own scale (cross-modality section).
- **Wrist HR**: favourable in steady state, as the BikeErg [unverified].
- **Technique curve**: shallow [unverified].
- **Realistic tier**: 1 continuous; 2 for intervals only where the bike
  records per-interval output.

## treadmill-run
- **Limits effort**: running economy and impact tolerance as well as
  cardiorespiratory capacity [unverified].
- **Output metric**: speed and incline from the console; the photo is the
  authority — Watch distance on a treadmill is estimated (spec §5).
- **Wrist HR**: arms swing freely without grip — generally workable in steady
  state; running cadence is the classic cadence-lock risk [unverified].
- **Technique curve**: shallow for runners [unverified].
- **Realistic tier**: 1 continuous; 2 for intervals with console evidence of
  each speed change (spec §8).

## treadmill-walk
- **Limits effort**: incline and duration rather than speed; low impact
  (dossier Method 1: incline walking for volume at low joint stress).
- **Output metric**: speed and incline from the console (spec §5).
- **Wrist HR**: favourable if the rails are not held [unverified].
- **Technique curve**: none to speak of [unverified].
- **Realistic tier**: 1. Decoupling is not measured on walking by default
  (`docs/schema.md`, `metrics.decoupling_modalities`).

## run
- **Limits effort**: as treadmill running, plus terrain and weather.
- **Output metric**: pace and distance from the Watch. Route and location
  fields are ignored by design (CLAUDE.md privacy rules).
- **Wrist HR**: as treadmill running [unverified].
- **Technique curve**: shallow for experienced runners [unverified].
- **Realistic tier**: 1 continuous; 2 for intervals with Watch splits (pace
  verifies the structure; wrist HR does not for short bouts).

## walk
- **Limits effort**: rarely cardiorespiratory at walking speeds on the flat
  [unverified].
- **Output metric**: pace and distance from the Watch.
- **Wrist HR**: favourable [unverified].
- **Technique curve**: none.
- **Realistic tier**: 1 for duration; usually unstructured — excluded from
  structured counts by `status.unstructured_modalities` (`docs/schema.md`).

## sled
- **Limits effort**: local muscular fatigue and load; framed as
  anaerobic/metabolic conditioning, not a primary VO2max driver
  (`sled-conditioning.md`, grade C).
- **Output metric**: none — load × distance × rounds is self-reported
  (`sled-conditioning.md` progression_rules).
- **Wrist HR**: grip corrupts it — never HR-verify (spec §5;
  `sled-conditioning.md` contraindications).
- **Technique curve**: shallow [unverified].
- **Realistic tier**: 3, confidence-qualified (spec §8; `sled-conditioning.md`).

## elliptical
- **Limits effort**: legs, with optional arm handles; low impact
  [unverified].
- **Output metric**: resistance Level, distance, strides/min — no watts
  (`machines.md` elliptical). Level is not comparable across consoles.
- **Wrist HR**: moving handles add grip and arm motion; the fixed-handle
  stance is gentler [unverified]. Console HR needs grip contact or a strap.
- **Technique curve**: shallow [unverified].
- **Realistic tier**: 1 for continuous work by HR; intervals by HR shape
  only.

## mixed
- **Limits effort**: varies by station — circuits, Hyrox sims, intervals with
  lifting.
- **Output metric**: none as a whole; individual erg or run segments may
  carry their own.
- **Wrist HR**: grip stations corrupt it; transitions are the lag worst case
  (spec §5).
- **Technique curve**: as the stations involved.
- **Realistic tier**: 3 — session-level proxies, per-station photos and
  structured self-report, confidence-qualified (spec §8; `hyrox.md`).

## Across modalities

- **HR anchors transfer only approximately.** The same heart rate on two
  machines need not mean the same intensity: muscle mass involved, posture,
  arm work and local fatigue differ, so an LTHR measured on one modality is
  an approximation on another (`skills/coach/adapt.md` §5, grade D
  practitioner heuristic [unverified]).
- **Power anchors do not transfer.** Displayed units differ by machine: the
  PM5 uses a different pace basis on the BikeErg than on the RowErg
  (concept2-pm5-101), and levels have no unit at all. Beyond units, that an
  FTP from one erg says nothing usable about another erg's numbers is a
  practitioner heuristic — it rests on muscle mass, local fatigue and
  unexamined calibration differences, none sourced here (grade D
  practitioner heuristic [unverified]). Each modality gets its own
  `power.<modality>` anchors (`docs/schema.md`).
- **So a new machine starts on conservative HR ceilings** — at or below the
  top of the z2 band, no zone floors, no watts targets — until 2–3
  familiarisation sessions and a calibration benchmark on that machine exist
  (`skills/coach/adapt.md` §4–§5, those numbers are grade D defaults
  [unverified]; `skills/coach/plan.md` Targets).
- **Efficiency factor and decoupling compare within one modality.** A watts
  ÷ HR trend mixes scales if two machines are pooled (`evidence.md`,
  Compliance Verification; Friel benchmark, practitioner source).
