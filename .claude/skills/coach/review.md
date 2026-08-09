# /coach review — Weekly Review

Outcome: ambiguities resolved, every prescribed session compliance-scored,
trends read, next week adjusted, and a report in `reports/YYYY-Www.md`.

## 1. Fresh data

Run `/coach ingest` first (or confirm it just ran).

## 2. Resolve ambiguities (conversation, not a queue UI)

For each case in `data/derived/proposals.json: ambiguous[]`, present it the
spec §7 way — evidence summary, then your read:

> "Photo at 6:42 shows a SkiErg at 25:00; Health has a 26:00 'Rowing' workout
> ending 6:36 and a 26:00 'Other' ending 7:06 — the second fits better
> (photo 6 min before its end vs 6 min after the first). Merge with that one?"

On decision: write/update the session file yourself (`match_method: claude`,
honest `match_confidence`, all sources listed), or record an orphan photo as a
photo-only session / discard non-workout shots. If a modality pairing was
unusual but real, append it to `config/athlete.yaml: matching.modality_map`.
Then rerun `compute_metrics.py` and `build_index.py`.

## 3. Compliance scoring (tiers per spec §8)

For each prescription in the week's plan, find its session(s) (match by
day/modality; set `prescription_id` on the session). Score into `compliance:`:

- **Tier 1** (continuous): components = duration vs target, % time-in-zone
  (HR or watts band), decoupling (<5% good). Fully computed — read
  `computed:`, never eyeball raw data.
- **Tier 2** (intervals): interval structure from machine watts/splits where
  present (`computed.bouts`, C2 splits), HR trace *shape* secondarily
  (bout count, plateaus, recovery dips). Bouts < 2 min: machine metrics only.
- **Tier 3** (mixed): session-level proxies + station photos + structured
  self-report; score explicitly confidence-qualified.
- Unprescribed sessions: record, no score; note if they broke the 80/20.
- Missed prescriptions: score 0 with the reason if known — honest, not harsh.

## 4. Trends & audits

From `data/index.jsonl` (rolling 4 wks): efficiency factor at z2 watts,
decoupling trend, interval repeatability (same-style watts across weeks),
adherence %, 80/20 session distribution. Compare against the §9 timeline for
the current block ("week 5 of 8 — on schedule; watts@HR up 4%").

## 5. Adjust & write

Decide next week's adjustment (progress, hold, or deload) with rationale tied
to the trends and the style's progression rules. Write
`reports/YYYY-Www.md`: scores table, distribution audit, trends, resolutions
made, adjustment + why. Voice per `SKILL.md`. Then generate next week via
`/coach plan` (or fold it in if the athlete wants it now).
