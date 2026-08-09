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

_(No entries yet — the first `/coach ingest` extraction pass over
`data/raw/photos/` seeds this file.)_
