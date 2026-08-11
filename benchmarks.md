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

### 2026-08-10 — observed max HR (bikeerg, informal)
- Result: HR max **176 bpm** observed during a 22-min easy ride finished with a
  hard surge over the last few minutes.
- Conditions/notes: athlete was fatigued; reports confident headroom into the
  180s, possibly 190s, when fresh. Treat 176 as a floor, not the max.
- athlete.yaml updated: yes — hr_max set to 185 (athlete-estimated midpoint,
  BOOTSTRAP ONLY until the LTHR/FTP field test).

Entry template:

```
### YYYY-MM-DD — <test> (<machine>)
- Result: ...
- Conditions/notes: ...
- athlete.yaml updated: yes/no (fields)
```
