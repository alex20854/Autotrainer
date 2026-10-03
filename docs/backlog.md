# Backlog

Work that was scoped and deliberately deferred, with the reason it waits.
Ordered roughly by value. Add to it rather than keeping ideas in chat.

## Next packages

- **Close the evidence gaps** — the knowledge-base package (RowErg/SkiErg
  console entries, Versaclimber stub, `modalities.md`, `protocols.md`,
  `readiness.md`, the evidence audit and `knowledge/sources.yaml`) is done.
  Left: find sources for the numbers tagged `[unverified]` (`evidence.md`,
  Known weak claims — the wrist-HR lag figure and the spec §9 decay and
  time-to-benefit figures matter most), check the `claim_checked: false`
  entries that exist, and confirm the RowErg/SkiErg console details marked
  "confirm on the first photo" from real photos. Never import a claim without
  a ledger entry.
- **Concept2 + Watch consolidation** — field-authority table (Watch: HR, kcal,
  timing; machine: duration, distance, watts), a recording routine, a
  check-on-device list, and a replay tool that measures auto-merge precision
  against already-adjudicated sessions (spec targets: ≥95% precision, ≥85%
  recall). Merge-code changes wait for a real dual-recorded export.
- **Docs and release** — development guide, add-a-machine and add-a-source
  checklists, CHANGELOG (pre-1.0), rewrite of setup's wire-up check for the
  current flow (phone pull, photo finder, C2 CSV drop).

## Later, and why

- **Plan-vs-actual evidence script and plan linter** — highest-value next step
  once a first real plan exists; the checkable target vocabulary should be
  designed alongside it. Output must be measurements, never verdicts.
- **`/coach today` session card** — after the first plan, so the card matches
  the plan format; with no plan it can only say "no plan".
- **Per-modality anchors (schema change + migration)** — when a second machine
  becomes primary.
- **parse_c2 robustness, work-window alignment of HR and watts, pace↔watts
  helpers** — build against one real Logbook export per erg; fail loudly on
  unknown headers.
- **Output metric for machines without watts** — needs confirmed console fields.
- **Per-erg dashboard panels, plan-vs-actual grid, 80/20 view** — wait for real
  second-erg sessions and real plans; any 80/20 view must state whether it
  counts sessions or time in zone.
- **HR recovery (HRR60), session drill-down traces** — weak or low-priority
  signals; grade in evidence first.
- **Schema version marker + migrate.py** — before the first non-additive change.
- **doctor.py install check, unattended weekly ingest, plugin Python-env
  bootstrap, Concept2 Logbook API client** — need permissions, accounts or
  capabilities that only the athlete can grant or verify.

## Open questions to verify before relying on them

- Does Concept2 ErgData write completed workouts to Apple Health, and can
  ErgData or the PM5 take Apple Watch heart rate?
- A Bluetooth chest strap paired to the PM5 would put HR and watts on one clock
  (no alignment code needed) and avoid wrist-HR problems on arm-driven
  machines — confirm strap compatibility.
- Can a Watch cycling workout read BikeErg power over Bluetooth?
- Logbook CSV shape per erg (headers, Type values, timestamp semantics, rest
  rows, BikeErg pace basis); PM5 clock drift as a matching risk.
- Is PM5 calorie output a fixed formula independent of body weight?
- Concept2 pace-to-watts formula and the BikeErg basis.
- Versaclimber console readouts, any export, and which Watch workout type to use.
- Friel LTHR zone percentages for cycling vs running.
- Tier-2 interval verification needs machine evidence (a PM5 interval summary
  photo, a C2 trace, or strap HR); wrist HR alone cannot verify short bouts.

## Waiting on the athlete (per workspace)

Goal intake via `/coach setup`; how Concept2 sessions are recorded; onboarding
of any new machine (one console photo, one Watch workout type); retest timing.
