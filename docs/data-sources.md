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
- The finder needs **Full Disk Access** for the app running it; originals
  that exist only in iCloud additionally need Photos **automation**
  permission (System Settings → Privacy & Security → Automation), or they
  are recorded as pending and retried.
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
