# Readiness, Confounders and Detraining

How to read resting HR, HRV and heart-rate drift as **context** for coaching
decisions, and what the knowledge base claims about losing fitness. The
coaching rules that act on these signals live in `skills/coach/adapt.md`
(§1 layoffs, §3 illness signals); this file is the background they rest on.

**Tags.** Grades per the `evidence.md` legend. Almost nothing here has a
primary source in the repo: physiology stated at mechanism level is marked
`[grade C - mechanism, unverified]` (coherent physiology, no source named),
and practice rules `[grade D - practitioner heuristic, unverified]`. No
numbers are introduced; the only numbers below are the engine's own defaults
and the styles' existing fields, quoted with their tags.

## What resting HR and HRV trends can and cannot show

- **Can**: a sustained rise in resting HR, or a sustained fall in HRV,
  relative to the athlete's own recent baseline is a common accompaniment of
  illness, accumulated fatigue, poor sleep or heat stress
  `[grade C - mechanism, unverified]`.
- **Cannot**: say *why* the number moved, diagnose anything, or say that the
  athlete is "ready" for a hard session. A normal reading does not rule out
  illness or fatigue `[grade C - mechanism, unverified]`. Symptoms the athlete
  reports outrank any number (`skills/coach/adapt.md` §3).
- **Between athletes**: absolute values differ widely between people and
  devices, so only an athlete's own trend is interpretable
  `[grade C - mechanism, unverified]`. Never compare an athlete's value with
  another person's or with a population norm in coaching.

## Rolling baselines beat single readings

- One morning's value carries measurement noise (sleep timing, posture,
  a missed or short reading) as well as signal; a median over a window damps
  single outliers, and a window long enough to span normal weekly variation
  makes "unusual for this athlete" meaningful
  `[grade C - mechanism, unverified]`.
- That is why the status facts compare a latest value with 7- and 28-day
  medians and always report the count of readings behind each median
  (`n_7d`, `n_28d`). A median of a handful of points is weak evidence — say
  how many points it rests on (`skills/coach/adapt.md` §3).
- A sustained shift (several consecutive readings) means more than any single
  reading; a lasting step change after a block of training can also be
  adaptation, not a warning `[grade C - mechanism, unverified]`.

## Wearable HRV caveats

- Consumer wearables take HRV from short optical readings at times the device
  chooses; the measurement conditions vary from day to day, unlike a
  controlled morning measurement `[unverified]`.
- The HRV statistic a wearable reports is device-defined; values from
  different devices, or from different software versions, are not
  interchangeable `[unverified]`.
- Optical sensor accuracy validation skews toward lighter skin tones and male
  subjects, so error bands are likely wider for others (`evidence.md`
  Caveats; dossier statement for HR, assumed to apply to HRV
  `[unverified]`).
- Treat HRV as the weaker of the two recovery signals here: a low HRV delta
  alone is context to mention, not a trigger (`skills/coach/adapt.md` §3,
  `[grade D - practitioner heuristic, unverified]`).

## Confounders of heart-rate drift and of HR at a given output

Heart rate at a fixed power, and its upward drift over a steady session, rise
for reasons other than fitness or effort. Name the plausible confounder
before reading a high HR or a large drift as lost fitness or a too-hard
session. Drift is not decoupling: decoupling compares output to HR
(`skills/coach/SKILL.md` guardrails; `skills/coach/review.md`).

- **Heat**: more blood is sent to the skin for cooling, leaving less central
  blood volume; stroke volume falls and HR rises to hold cardiac output
  `[grade C - mechanism, unverified]`.
- **Dehydration**: lower plasma volume reduces stroke volume, so HR rises at
  the same output, and the effect grows through a session
  `[grade C - mechanism, unverified]`.
- **Sleep loss**: shifts autonomic balance toward sympathetic activity,
  raising HR at rest and in exercise for some people
  `[grade C - mechanism, unverified]`.
- **Illness**: fever and the immune response raise HR; training hard while
  unwell is a guardrail matter, not a data point
  (`skills/coach/adapt.md` §3) `[grade C - mechanism, unverified]`.
- **Recent hard work**: residual fatigue from preceding days can raise or
  sometimes blunt the HR response at a given output; the direction is not
  reliable `[grade C - mechanism, unverified]`.
- **Stimulants**: caffeine and other sympathomimetics (including some
  medicines) raise HR; medicines that slow the heart lower it — ask before
  interpreting, and never advise on medication (`skills/coach/SKILL.md`
  guardrails) `[grade C - mechanism, unverified]`.
- **Measurement**: wrist-HR artefacts — cadence lock, grip, a loose strap —
  can look like drift (`modalities.md`, wrist-HR background).

## Reading the status facts' recovery numbers

`scripts/lib/facts.py` (`status.py --json`, `recovery` block) reports
measurements only; it never says "recovered" or "not recovered". Read it as
context, never as a verdict:

- `resting_hr.latest`, `median_7d`, `median_28d`, `delta_vs_28d`, `n_7d`,
  `n_28d` — the latest reading, the medians of the readings in the 7 and 28
  days ending at `as_of`, and the latest minus the 28-day median. Read the
  `n` first.
- `resting_hr.days_elevated` — consecutive most-recent readings in the
  28-day window at or above the 28-day median plus
  `elevated_threshold_bpm`. The threshold (default 5 bpm,
  `status.resting_hr_elevated_bpm`) is an engineering default labelled a
  practitioner heuristic in the code `[unverified]`; adjust it per athlete
  and say so.
- `hrv` — the same medians and delta, no elevation count (see the HRV
  caveats above for why it is the weaker signal).
- `vo2_max.latest` — the device maker's estimate (`protocols.md`, Watch
  estimate): a trend at best, never a test result.
- What the coach does with them — e.g. an easy day when `days_elevated` ≥ 2 —
  is a coaching rule in `skills/coach/adapt.md` §3, tagged there
  `[grade D - practitioner heuristic, unverified]`.

## Detraining and return from a layoff

What the style entries' own `detraining_decay` fields already claim, with the
grade of the style they sit in. The style grade covers the method's efficacy,
**not** its decay figures: every decay number below is `[unverified]` in its
style file (`evidence.md`, Known weak claims).

| Style (grade) | `detraining_decay` claims |
|---|---|
| `norwegian-4x4` (A) | VO2max decay begins ~2–4 wks after stopping, blood-volume/stroke-volume losses first; ~1×/wk maintains — both [unverified] |
| `sit-rehit-tabata` (A efficacy) | fast, like other high-intensity work; 1–2×/wk maintains [unverified] |
| `short-aerobic-hiit` (B) | fast, like other high-intensity work; 1×/wk maintains [unverified] |
| `threshold-sweet-spot` (B/C) | moderate; 1×/wk maintains [unverified] |
| `zone2` (B/C) | slowest of all methods; base built over months survives short breaks (qualitative) |
| `maf` (D formula / C principle) | slow — it is base (qualitative) |
| `hinshaw-pace-diversity` (C/D) | follows the underlying systems: interval fitness fades in weeks, base slowly (qualitative) |
| `carson-engine` (D) | erg-specific pacing skill fades faster than the aerobic base (qualitative) |
| `hyrox` (C/D), `sled-conditioning` (C) | station skill and specific capacity fade in weeks (qualitative) |
| `polarized` (A/B) | not applicable — decay follows the constituent methods |

The common shape — **high-intensity adaptations arrive fast and fade fast;
volume-built aerobic base arrives slowly and fades slowly** — is spec §9's
governing principle, described there as well supported but with no citation
in the repo `[unverified]`. Use it to explain *why* the return ladder in
`skills/coach/adapt.md` §1 reintroduces easy volume before intensity; its day
cut-points and the intensity gate are grade D defaults there, not findings
from these fields. A stale benchmark after a long layoff makes paces and
watts targets wrong (`hinshaw-pace-diversity.md` consistency_requirement), so
power anchors become ceilings until a retest (`adapt.md` §1).
