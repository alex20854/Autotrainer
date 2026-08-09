# /coach ingest — Pull Data, Extract Photos, Reconcile

Outcome: all new raw data normalized, photos extracted, auto-merges applied,
index rebuilt, and the athlete told what needs review.

## 1. Deterministic pass

```
python3 scripts/ingest.py
```

Runs parsers → prep_photos → proposals → auto-merges → metrics → index.
Read the step outputs; note counts.

## 2. Vision extraction (your judgment work)

For every pending sidecar (`extracted: false` in `data/derived/photos/*.yaml`):

1. Read the photo (`converted` path if set, else `photo`).
2. Consult `knowledge/machines.md` for the console layout if known.
3. Fill the sidecar: `machine` + `machine_confidence`, `fields` with per-field
   `{value, confidence}` for whatever the console shows (elapsed_time_s,
   distance_m, watts_avg, kcal, pace, splits...), `extracted: true`, `notes`
   for anything odd. Units: convert to schema units (seconds, meters, kcal).
4. If the console layout is new or you got something wrong before, add/refine
   the `knowledge/machines.md` entry, including this photo as an example.
5. Not a monitor photo at all? `extracted: true`, `machine: null`, note why —
   it will surface as an orphan for review and can be ignored there.

Do NOT guess low-visibility values: a missing field with a note beats a
low-confidence hallucination. Per-field confidence must reflect actual
legibility.

## 3. Re-reconcile

```
python3 scripts/propose_matches.py && python3 scripts/apply_merges.py && \
python3 scripts/compute_metrics.py && python3 scripts/build_index.py
```

(The extractions may enable new pairings.)

## 4. Report

Tell the athlete: sessions added (by day/modality), anything the metrics pass
flagged (`zones_source: bootstrap` or `unconfigured` — prompt setup/field
test), and how many ambiguous cases await `/coach review`. Keep it short;
detail lives in the files.
