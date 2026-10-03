# Data sources — formats, quirks, failure modes

What each input actually looks like in the wild, learned from real ingests.
Every quirk here is handled in code with a test; this is the human-readable
index. Add to it whenever an ingest teaches something new (engine rule 6).

## Health Auto Export JSON (`data/raw/health/*.json`)

The main ongoing source: `{"data": {"workouts": [...], "metrics": [...]}}`,
written either by the app's iCloud/Dropbox export automations or by
`pull_health.py` (same shape).

- **Units follow the phone's locale.** `distance` arrives as
  `{"qty": 0.97, "units": "mi"}` for US users. The `units` field is
  authoritative (`parse_auto_export._distance_m`); a bare number is taken as km.
- **Workout types are display names** (`Indoor Cycling`, `Outdoor Walk`,
  `Stair Climbing`), not HealthKit identifiers. `matching.modality_map` must
  list both spellings; a lookup miss lowers pair confidence from 1.0 to 0.75,
  below the auto-merge bar, and the pair surfaces as ambiguous with a hint.
- **`duration` unit varies by app version** (minutes or seconds). The parser
  picks whichever reading is closer to the wall-clock span.
- **HR series come at the Watch's native ~5 s cadence** as
  `heartRateData: [{date, Min, Avg, Max}]`; asking the server for
  `metadataAggregation: seconds` does not make them denser.
- **Export windows overlap** and raw files are gitignored, so a machine can
  re-ingest an older export than the one a record came from.
  `records.upsert_record` never replaces a stored record with a less complete
  capture from a different file; same-file re-parses always apply.
- **Sub-2-minute records** (false starts, max-HR probes, accidental taps) are
  set aside by `propose_matches` (`classification.min_session_s`, default 120)
  and reported; they stay in `data/derived/workouts/` and are citable.
- Energy arrives in kcal (`activeEnergyBurned`); `location` is the string
  `Indoor`/`Outdoor`, not coordinates. Parsers never read route fields.

## Health Auto Export MCP server (`pull_health.py`)

Premium feature: the iPhone serves `http://<phone-ip>:9000/mcp` on the local
network while the app is in the **foreground** on its Server screen.

- Bearer token from the Server screen; lives in the workspace's gitignored
  `config/health_server.local.yaml`. Opening the endpoint in a browser (GET)
  returns `{"error":"method not allowed"}` — that is normal, the server is up.
- `No route to host` = the phone is not on the network at that address
  (screen locked → Wi-Fi asleep, or new DHCP address). `Connection refused`
  = phone reachable but the app is not serving (backgrounded). HTTP 401 = bad
  or regenerated token.
- Tools used: `get_workouts` (`includeRoutes` hardcoded false; location keys
  scrubbed again before writing) and `get_health_metrics` for resting HR,
  HRV and VO2max at daily resolution. A six-week pull is ~5 MB.
- The phone must also be **unlocked** for Health data access.

## AutoSync `.hae` files (iCloud Drive, not ingested)

The app's own cache under `iCloud~com~ifunography~HealthExport/AutoSync/`:
one LZFSE-compressed JSON per workout (`compression_tool -decode -a lzfse`).
Summaries only — start/end, energy, HR min/avg/max, **no HR series** — and
they carry the device name (owner's first name) and weather. Not used by
the parsers; the MCP pull supersedes them.

## Apple Health `export.xml` (backfill)

Full history, hundreds of MB, gitignored. Workout types are HealthKit
identifiers (`HKWorkoutActivityTypeCycling`). HR samples are matched to
workouts by time window. Parsed once; derived records are the durable form.

## Concept2 Logbook CSV (`data/raw/c2/`)

Two shapes: summary rows (one per workout) and per-stroke detail files.
Both go through `upsert_record`, so a summary never overwrites a richer
detail capture of the same piece.

## Monitor photos (`data/raw/photos/`, `find_monitor_photos.py`)

- EXIF time is the matching key, compared as an absolute instant using the
  photo's own offset (a naive value is read in the workout's offset; when the
  workout has none either, e.g. a C2 CSV, wall clocks are compared). The photo
  must fall in `[start, end + photo_window_after_end_s]` of a workout.
- Photos usually arrive **after** the Health record has become a session;
  Health-only auto sessions are therefore upgradable in place (schema.md).
- **macOS 27** broke osxphotos' lookup of the last-opened library (it returns
  nothing), which surfaced as `FileNotFoundError` on an untouched library.
  The finder now resolves the library itself (`--library`,
  `photo_finder.library`, osxphotos' lookups, then the default bundle in
  `~/Pictures`) and needs osxphotos ≥ 0.77.2.
- The finder needs **Full Disk Access** for the app running it; originals
  that exist only in iCloud additionally need Photos **automation**
  permission (System Settings → Privacy & Security → Automation), or they
  are recorded as pending and retried. macOS's permission prompt blocks the
  export call indefinitely, so the finder waits `photo_finder.export_timeout_s`
  (default 180 s) per such original, then records it as pending and moves on,
  saying why. macOS shows that prompt only to a real app: a shell inside another
  app's panel (an IDE or chat terminal) never gets it and would block forever,
  so run the finder once from Terminal.app to grant Photos automation, or use
  `--no-download` and sweep the pending iCloud-only originals from Terminal.app
  later. After one timeout a run stops trying Photos for its remaining matches.
  Storage-friendly fallback that needs no automation and no bulk download:
  `--list-pending` prints each pending photo's filename and date; in Photos,
  select them and File > Export > Export Unmodified Original into a folder
  (iCloud fetches just those); `--adopt <folder>` matches the files to the
  pending IDs (filename, else capture time) and stages them.
- Vision OCR misreads LCD consoles predictably (`watt` → `wyatt`, `Walt`,
  `W30t`); the scorer's loose patterns and penalties for receipts, nutrition
  labels, social-app chrome and Fitness-app summaries are tuned on real hits.
- **Travel:** the Watch keeps recording in the home offset (Auto Export stamps
  the source time zone) while the photo's EXIF carries the local offset where
  it was taken (`OffsetTimeOriginal: -07:00`). `prep_photos` keeps that offset
  in `exif_time`; read as home time, the photo would sit hours from its
  workout and surface as an orphan. The offset reveals only a time zone — far
  coarser than the location data the privacy rules exclude — and
  `privacy_check --strip-gps` leaves it in place by design.
- Apple Fitness / Health **screenshots** of a workout are not monitor photos:
  the Health export already carries that data, and they can show a map.

## Computed metrics (`compute_metrics.py`)

Not an input, but its numbers come straight from the HR and watts series
above, and two of its readings changed (schema.md, session `computed:`).

- **Zones are contiguous.** The shipped band tables were integer percents
  (`z2 [0.85, 0.89]`, `z3 [0.90, 0.94]` ...) read literally with an exclusive
  upper bound, so HR between 89–90%, 94–95% and 99–100% of LTHR counted in no
  zone (at LTHR 160: 142.4–144, 150.4–152 and 158.4–160 bpm) — a sizeable
  share of a steady session that sits near a zone edge. Each zone now runs up
  to the next zone's start; lower bounds are unchanged. Overlaps or gaps wider
  than rounding warn once.
- **Decoupling is windowed and modality-gated.** It used to be computed for
  every session with HR (walks included) over the whole session, warm-up
  included, and for every session without a watts series (all Watch-only
  ones) the value was heart-rate drift labelled as decoupling. Now:
  allowlisted modalities only, the warm-up skipped, a minimum window (ending
  at the session's end when the HR trace reaches it), null with
  `not_steady` when a watts series shows work bouts, and `decoupling_method`
  says whether the number is `pw_hr` or `hr_drift`. C2 split watts are
  weighted by the time each split covers. Watch-only sessions read
  `hr_drift`, and can't be checked for steadiness — only Tier 1 steady
  sessions make a meaningful drift trend.
- **Historical values shift at the next ingest** (metrics are recomputed every
  run): zone totals rise toward the full HR duration, and short or non-steady
  sessions lose their decoupling value (null with `decoupling_note`).
