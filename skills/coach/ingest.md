# /coach ingest — Pull Data, Extract Photos, Reconcile

Outcome: all new raw data normalized, photos extracted, auto-merges applied,
index rebuilt, and the athlete told what needs review.

## 0. Find new monitor photos (macOS, Apple Photos)

Parse Health exports first so the finder can use workout end times, then scan:

```
"$PY" "$ENGINE/scripts/parse_auto_export.py"
"$PY" "$ENGINE/scripts/find_monitor_photos.py"          # add --dry-run to preview
```

It OCRs photos since the last scan and stages likely console photos in
`data/inbox/photos/` (GPS already stripped). Look at every staged photo:
a machine console → `--promote UUID ...` (moves it into `data/raw/photos/`);
anything else → `--reject UUID ...` (deleted, never staged again). Never
promote a photo showing people, faces, or identifiable places — ask the
athlete instead. Mention any near-misses it lists; the athlete can add real
ones to the override album (default "Autotrainer") and re-run.

If it fails to open the library, the app running it needs Full Disk Access
(System Settings → Privacy & Security) — the athlete grants that, not you.
Skip this step on non-Mac setups; photos can always be dropped into
`data/raw/photos/` by hand.

## 1. Deterministic pass

```
"$PY" "$ENGINE/scripts/ingest.py"
```

Runs parsers → prep_photos → proposals → auto-merges → metrics → index.
Read the step outputs; note counts.

## 2. Vision extraction (your judgment work)

For every pending sidecar (`extracted: false` in `data/derived/photos/*.yaml`):

1. Read the photo (`converted` path if set, else `photo`).
2. Consult `$ENGINE/knowledge/machines.md` for the console layout if known.
3. Fill the sidecar: `machine` + `machine_confidence`, `fields` with per-field
   `{value, confidence}` for whatever the console shows (elapsed_time_s,
   distance_m, watts_avg, kcal, pace, splits...), `extracted: true`, `notes`
   for anything odd. Units: convert to schema units (seconds, meters, kcal).
4. If the console layout is new or you got something wrong before, add/refine
   the `$ENGINE/knowledge/machines.md` entry (engine knowledge: describe the
   console generically, never the athlete or their gym), including this photo as an example.
5. Not a monitor photo at all? `extracted: true`, `machine: null`, note why —
   it will surface as an orphan for review and can be ignored there.

Do NOT guess low-visibility values: a missing field with a note beats a
low-confidence hallucination. Per-field confidence must reflect actual
legibility.

## 3. Re-reconcile

```
for s in propose_matches apply_merges compute_metrics build_index; do
  "$PY" "$ENGINE/scripts/$s.py" || break; done
```

(The extractions may enable new pairings.)

## 4. Refresh the hosted dashboard

Ingest already re-rendered `dashboard.html`. If this session has the Artifact
tool, also refresh the hosted copy (same URL every time):

```
"$PY" "$ENGINE/scripts/build_dashboard.py" --artifact <scratch>/cardio-coach.html
```

then publish that file to the hosted-dashboard URL recorded in the workspace
`CLAUDE.md`. No URL recorded yet → publish a new artifact and record its URL
there so every later ingest updates the same page. Sessions without the
Artifact tool skip this — the committed `dashboard.html` is always current
regardless.

## 5. Report

Tell the athlete: sessions added (by day/modality), anything the metrics pass
flagged (`zones_source: bootstrap` or `unconfigured` — prompt setup/field
test), and how many ambiguous cases await `/coach review`. Keep it short;
detail lives in the files.
