# Project Spec: Claude Cardio Coach ("Engine")

**Version:** 0.2 (alpha, single user)
**Changes from 0.1:** (1) Reframed architecture — Claude *is* the engine; no app, no database. (2) Flat-file data store (markdown + YAML frontmatter + generated index) replaces SQLite. (3) All data sources are opportunistic per-session ("best available evidence"), reflecting unreliable C2 sync. (4) Coaching knowledge base entries now carry dose-response fields: minimum effective dose, time-to-measurable-benefit, consistency requirement, and detraining decay.

---

## 1. Problem Statement

The user trains cardio regularly on gym equipment (Concept2 machines, Airdyne, stairclimber, Versaclimber, exercise bikes, treadmills) plus outdoor running and sleds. Two data streams already exist — Apple Watch/Health workout records and photos of equipment monitors taken after each session — but they live in silos, don't reconcile automatically, and no coaching intelligence sits on top of them.

The goal is a system where Claude acts as a **cardio coach and compliance monitor** in the style of elite aerobic-capacity coaches (Chris Hinshaw's pace-diversity/recovery methodology; Rob & Lizzy Carson's erg-centric "Engine" style programming): it prescribes structured training toward a chosen goal, verifies from objective data whether the prescription was actually executed, and adapts programming over time.

## 2. Architecture Principle: Claude Is the Engine

This is **not an app build**. There is no server, no daemon, no database, no application logic layer. The system is:

- **A repo of flat files** — the durable memory. Files are the interface between sessions; anything Claude should remember must be written to a file.
- **Claude (via Claude Code skills/commands)** — all intelligence: photo reading, ambiguous match adjudication, program generation, compliance judgment, coaching conversation, report writing.
- **A small toolbox of deterministic scripts** — used *only* where determinism, repeatability, or data volume demands it. Rule of thumb: if the task is "apply fixed math to lots of numbers" (parse a 500 MB `export.xml`, compute per-second time-in-zone, rebuild the index), it's a script Claude runs. If the task requires judgment (read a photo, resolve a fuzzy match, decide next week's plan), it's Claude directly. Scripts never make coaching decisions.
- **Display components (optional, later)** — an HTML/artifact dashboard is purely a *rendering of files*. It contains no logic and no state of its own.

**Consequence for the spec:** wherever v0.1 said "engine," read "a Claude skill operating on files, optionally calling a utility script."

## 3. Goals

1. **Unified workout ledger:** ≥95% of cardio sessions correctly reconciled across available sources, with ambiguous cases resolved conversationally during review.
2. **Objective compliance scoring:** Every Tier 1–2 prescription (§8) scored from data (HR summary, duration, watts/pace), not self-report.
3. **Evidence-based prescription:** Programming generated from the coaching-styles knowledge base (§10), including honest time-to-benefit expectations.
4. **Adaptive coaching loop:** Weekly review analyzing trends (watts@HR, decoupling, interval repeatability) and adjusting the next block.
5. **Low-friction operation:** photo habit + periodic export + short weekly check-in. Nothing else.

## 4. Non-Goals (v1)

- No geriatric/clinical populations; no medical advice (flag anomalies, refer out).
- No strength or nutrition programming.
- No multi-user, auth, or cloud backend.
- No real-time/in-workout coaching.
- No custom iOS app.
- **No database** — flat files until scale forces the issue (P2 note in §6).

## 5. Data Sources: Opportunistic, Best-Available-Evidence

Real-world reliability varies (C2 ErgData/Logbook sync is flaky in practice; photos get forgotten; exports arrive late). Therefore **no source is primary by design**. Each canonical session records *which* sources contributed and what confidence that supports. Per-session source hierarchy when multiple exist:

1. **Full machine trace** (ErgData/C2 Logbook CSV/TCX with splits) — richest; wins for interval detail when present.
2. **Monitor photo** (Claude vision extraction: machine type, elapsed time, distance, avg watts, cals, splits if shown; per-field confidence; EXIF timestamp is the matching key).
3. **Apple Health record** (timestamps, duration, workout type, kcal, avg/max HR, HR series) — nearly always present; anchors the session's existence and HR data even when machine data is missing.
4. **User statement** (RPE, notes, Tier 3 self-report) — subjective layer, never substituted for objective data in Tier 1–2 scoring.

**Apple Health ingestion paths** (both feed the same normalizer):
- *Ongoing:* Health Auto Export app → scheduled JSON to an iCloud Drive folder. Constraint: iOS only exports while the phone is unlocked → arrival is periodic; the review process is pull-based and idempotent.
- *Backfill/fallback:* native Health `export.zip` → streaming parse of `export.xml` (script; the file is huge).

**Known caveats to encode:** wrist optical HR lags 5–15 s on sharp transitions → never verify short intervals by HR peaks; treadmill Watch distance is estimated → photo is authority for speed/incline; grip work (sleds/carries) corrupts wrist HR.

## 6. Data Store: Flat Files

```
engine/
  data/
    raw/
      health/      # exported JSON, export.xml as received (immutable)
      photos/      # monitor photos (immutable)
      c2/          # ErgData/Logbook exports when sync worked (immutable)
    sessions/
      2026/2026-08-08-bikeerg-z2.md    # ONE canonical session per file
    index.jsonl                        # generated; one line per session
  plans/           # weekly plans / prescriptions (markdown + frontmatter)
  knowledge/
    styles/        # coaching KB entries (§10)
    evidence.md    # research dossier / citations
  reports/         # weekly reviews Claude writes
  benchmarks.md    # dated test results (2k row, LTHR test, MAF test, resting HR...)
  goals.md         # active + historical goal tracks
```

- **Session file = markdown with YAML frontmatter.** Frontmatter carries structured fields (date, start/end, modality, machine, duration, avg/max HR, avg watts, distance, kcal, sources[], match_confidence, prescription_id, compliance{score, tier, components}, computed{time_in_zone, decoupling}). Body carries human notes and Claude's observations. Human-readable, greppable, git-diffable.
- **HR series never inlined.** They stay in `raw/`; sessions store computed summaries only (a script computes time-in-zone/decoupling from the raw series so Claude never reads thousands of samples into context).
- **`index.jsonl` is derived, never hand-edited.** A tiny script regenerates it from session frontmatter so Claude can scan the whole history cheaply without opening hundreds of files.
- **The frontmatter schema is the contract.** If scale ever hurts (unlikely for one user), migrating index + frontmatter into SQLite is mechanical (P2). Design nothing that blocks that; build none of it now.

## 7. Reconciliation

Timestamps won't match exactly (photo taken after the workout; monitor 30:00 vs Watch 30:24). Process:

1. A **proposal script** does the deterministic part: candidate pairs by date/time window (photo EXIF within [session_start, session_end + 10 min]), duration cross-check (|monitor − Health| ≤ 90 s default), modality-consistency lookup (learned mapping, e.g., SkiErg console → Health "Rowing"/"Other"; never hard-fail).
2. High-confidence pairs auto-merge into a session file.
3. **Ambiguous cases go to Claude, not a queue UI:** during `/coach review`, Claude presents each unresolved case conversationally ("Photo at 6:42 AM shows an Airdyne at 25:00; Health has a 26:10 'Indoor Cycling' workout ending 6:41 — merge?") and writes the resolution. Unmatched single-source sessions are first-class (forgot the photo; outdoor run with no monitor).

Acceptance: ≥95% precision on auto-merges (no wrong pairings), ≥85% auto-merge recall on backfill; everything else resolvable in one review conversation.

## 8. Compliance Framework

Every prescription carries a **verification tier** chosen at programming time; the coach prefers lower tiers unless the goal demands otherwise (this matches the evidence — see §10/§11).

- **Tier 1 — Fully verifiable** (single machine, continuous: Zone 2, MAF, capped-watt rows). Verified by duration, % time-in-zone (HR or watts band), decoupling. Score fully computed.
- **Tier 2 — Structurally verifiable** (single machine, intervals: 4×4, 30/30s, threshold repeats). Verified by interval structure from machine watts/splits where available, HR trace *shape* (bout counts, plateaus, recovery dips) secondarily. Bouts < 2 min: machine metrics only; HR peaks ignored.
- **Tier 3 — Partially verifiable** (mixed modal: Hyrox sims, circuits, intervals with lifting). Session-level proxies (duration, HR profile plausibility, kcal) + per-station photos + structured self-report. Scores are explicitly confidence-qualified.

## 9. Dose-Response: Time-to-Benefit and Consistency (new in 0.2)

Core coaching knowledge — drives sequencing, expectation-setting, and maintenance dosing. Governing principle, well supported by the training literature: **high-intensity adaptations arrive fast and decay fast; volume-driven aerobic base arrives slowly and decays slowly.**

Every KB entry (§10) must carry four fields, and the coach must use them when setting expectations:

- `minimum_effective_dose` — least frequency × duration that produces adaptation.
- `time_to_measurable_benefit` — when the *system's own metrics* should show it (and which metric).
- `consistency_requirement` — adherence level below which progress stalls.
- `detraining_decay` — how fast the adaptation fades if stopped, and the maintenance dose.

Seed values (evidence-based estimates; ranges honest, citations in `knowledge/evidence.md`):

| Method | Min. effective dose | Time to measurable benefit | Consistency need | Decay / maintenance |
|---|---|---|---|---|
| Norwegian 4×4 | 1×/wk (2–3×/wk to build) | **~6–8 wks** at 3×/wk for ~5–7% VO2max (Helgerud 2007: 8 wks); interval watts improve within 3–4 wks | Miss >2 wks and gains stall | VO2max decay begins ~2–4 wks after stopping (blood-volume/stroke-volume losses first); ~1×/wk maintains |
| SIT / REHIT | 2–3×/wk, 10–25 min | **~2–6 wks** (oxidative markers in ~2 wks / 6 sessions; VO2max ~6 wks — Gibala) | High per-session effort required; tolerability is the limiter | Fast decay like other HII work; 1–2×/wk maintains |
| Threshold / sweet spot | 2×/wk | **~4–8 wks** for FTP/threshold-watt gains | ≥2×/wk during a block | Moderate decay; 1×/wk maintains |
| Zone 2 / LT1 | 3×/wk × 45–60 min (benefit scales with volume) | **~6–8 wks** for first objective signal (watts@HR ↑, decoupling <5%); mitochondrial/metabolic adaptations compound over **months** | The compounding is the point: ≥3×/wk, most weeks, indefinitely | Slowest decay of all; base built over months survives short breaks |
| Polarized distribution | 4–5 sessions/wk total | Distribution effects measured over ~9-wk blocks (Stöggl & Sperlich 2014) | Weekly 80/20 audit | N/A (meta-structure) |
| MAF base | 3–4×/wk under HR cap | MAF test (pace at capped HR) improves over **8–16 wk** base phases | Strict cap discipline | Slow decay (it *is* base) |
| Hyrox specific | 4–6 sessions/wk mixed | **12–13 wk** race block *on an existing base*; from scratch ≥6 months | High — specificity work perishable | Station skill/compromised-running fitness fades in weeks |

Two corrections to common intuition the coach should actively teach:
1. **4×4 is the fast one, not the slow one.** Measurable VO2max gains take ~6–8 weeks at 3×/week — and it should *never* be daily (recovery-limited; 3×/wk is the studied ceiling).
2. **Zone 2 is the slow-compounding one** — its metabolic payoff needs months of consistent volume, which is why it's the base layer, started first and never really stopped. Additionally, part of exercise's insulin-sensitizing effect is acute (lasting roughly 24–72 h post-session), which argues for *frequency* (≥3×/wk, spread out) on the metabolic-health track independent of total volume.

**Goal-track time-to-value (set at intake, shown in every plan):**
- *General CV health:* first VO2max/interval-watt signal ~6–8 wks; resting-HR drop often 4–8 wks. Minimum viable: 3× Zone 2 (45 min) + 1× 4×4 weekly.
- *Metabolic health:* acute glycemic benefits begin immediately with frequency; durable markers (body comp, lipids, watts@HR) 8–12 wks.
- *Hyrox:* 12–13 wk specific block on top of ≥8–12 wks of base; committing to a race date before the base exists is a programming error the coach should catch.

## 10. Coaching Styles Knowledge Base

`knowledge/styles/*.md`, one entry per method, YAML frontmatter + prose. Fields: protocol (parameterized), primary adaptation, evidence grade (A–D) + key sources, machine suitability, verification tier, the four §9 dose-response fields, contraindications, progression rules. Seed entries: Zone 2/LT1 (San Millán, Attia framing), polarized 80/20 (Seiler; Stöggl & Sperlich), Norwegian 4×4 (Helgerud/Hoff/Wisløff; popularized by Rhonda Patrick), threshold/sweet spot, short aerobic HIIT (Billat 30/30, 40/20, 15/15), SIT/Wingate/REHIT/Tabata (with the ~170% VO2max original-Tabata caveat), MAF, Hinshaw pace-diversity, Carson erg engine building, Hyrox-specific, sled conditioning. The completed research dossier (already produced) is the source material for `knowledge/evidence.md`; entries must preserve its evidence grades and its caveats about practitioner-consensus methods.

**Goal tracks** map to style mixes as in v0.1 (general CV health; metabolic health & performance; Hyrox/competition; extensible), now each annotated with §9 time-to-value.

## 11. Coaching Behaviors (Claude Code skills)

- `/coach setup` — goal intake, zone anchoring (field LTHR/FTP test scheduled; formulas as bootstrap only), expectation-setting from §9.
- `/coach ingest` — pull new raw files, run parsers + proposal script, merge sessions, regenerate index, surface ambiguities.
- `/coach plan` — write next week's plan to `plans/` (human-readable prescriptions with tier, targets, and the "why," including time-to-benefit context).
- `/coach review` — weekly: compliance scores, 80/20 distribution audit, trends (watts@HR, decoupling, interval repeatability), ambiguity resolution, next-week adjustment with rationale → written to `reports/`.
- `/coach ask` — free-form coaching grounded in the ledger.

**Voice:** direct, evidence-citing, compliance-honest, encouraging, never rubber-stamping; states verification tier with every prescription; distinguishes RCT-grade claims from practitioner consensus.

## 12. Milestones

- **Phase 0 — Scaffold:** repo layout, frontmatter schema, fixture data, index script.
- **Phase 1 — Data foundation:** export.xml backfill parser; Health Auto Export watcher-folder convention; photo vision workflow; proposal script; first full backfill meeting §7 acceptance. *Exit: entire history reconciled into `sessions/`.*
- **Phase 2 — Coaching MVP:** KB seeded from dossier; `/coach setup|plan|review`; Tier 1–2 scoring; one full prescribe→train→verify→adapt cycle on real weeks. *Exit: two consecutive honest weekly reviews.*
- **Phase 3 — Depth:** benchmark protocol + zone recalibration cadence; trend analytics; C2 trace ingestion (opportunistic); polarization meta-audit; optional read-only HTML dashboard.
- **Phase 4 — Mixed modal:** Hyrox track, Tier 3 definitions, multi-photo station evidence, race-countdown periodization.

## 13. Success Metrics

- Auto-merge precision ≥95% / recall ≥85%; photo extraction ≥98% on time/watts/cal (audited sample); weekly review is one command + one conversation; adherence ≥80% over a 4-wk block.
- 3-month lagging: measurable trend in ≥1 goal-relevant marker (watts@Z2-HR, 4×4 avg watts, benchmark times, resting HR) — with §9 timelines making "when should I expect this?" explicit up front.

## 14. Open Questions

1. **Zone anchoring (blocking):** field LTHR/FTP tests per primary modality in Phase 2; which modality first?
2. **Chest strap (non-blocking):** add for interval HR fidelity, or rely on machine watts? Affects Tier 2 config only.
3. **Health Auto Export settings (blocking, cheap):** verify Premium automation + iCloud Drive JSON with HR samples on real data; else scheduled manual exports.
4. **Photo routing (non-blocking):** manual folder copy v1; `osxphotos` album export later?
5. **C2 trace formats (non-blocking):** which export (CSV/TCX/FIT) is most reliable when sync *does* work; handle all three?

## 15. Risks

- **Late/flaky data arrival** (iOS export limits, C2 sync): mitigated by pull-based idempotent ingest and per-session best-available-source design — the system degrades gracefully to photo+Health or Health-only.
- **Vision extraction errors on unfamiliar consoles:** confidence fields + conversational resolution + a growing per-machine example file.
- **Context economy:** raw HR series and export.xml never enter Claude's context; scripts summarize. The index keeps whole-history questions cheap.
- **Coaching without medical oversight:** guardrails in the coach skill (no diagnosis, conservative progression, deload on illness signals).
- **Scope creep toward an app:** §2 is the guardrail — any proposed component must be a file, a skill, or a deterministic script, or it doesn't belong.
