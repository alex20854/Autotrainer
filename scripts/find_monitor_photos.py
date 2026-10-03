#!/usr/bin/env python3
"""Find exercise-monitor photos in Apple Photos and stage them for ingest (macOS).

Scans the Photos library for images taken in a date window (default: since
the last scan), reads their text with Apple's on-device Vision OCR, and scores
it for machine-console vocabulary (brand/console names, watts, splits, pace,
kcal...), plus a timing bonus when the photo was taken just after a recorded
workout ended (parse Health exports first so those records exist). Matches are exported — originals, with GPS/owner EXIF stripped — to
the workspace inbox, data/inbox/photos/ (gitignored). Photos in the override
album (default "Autotrainer") are always staged, whatever their text.

Nothing reaches data/raw/ until Claude has looked at it during /coach ingest:
  --promote UUID...  move staged photos into data/raw/photos/ (monitor photos)
  --reject UUID...   delete staged photos, never stage them again (false hits)

READ-ONLY toward Apple Photos, by construction:
  - The library is only read: osxphotos queries a temporary copy of its
    database, and this script uses nothing but the read-only calls pinned by
    tests/test_find_monitor_photos.py (no albums/keywords/edits/deletes).
  - Originals are exported as independent copies (never hard links), so
    stripping EXIF from a staged copy cannot touch the library original.
  - Every file this script writes, moves, or deletes passes _guard_write():
    it must live in this workspace's inbox, raw photos dir, or state file,
    never inside a *.photoslibrary, and never be hard-linked elsewhere.
  Side effect to know about: for a match whose original is only in iCloud,
  Photos is asked to export it, which makes Photos download that original
  (as viewing it would). --no-download avoids even that.

Deterministic: scoring is plain keyword arithmetic; the judgment call (is this
really a monitor?) is Claude's. State lives in data/derived/photo_finder.json.

Needs Full Disk Access for the app running it (System Settings -> Privacy &
Security -> Full Disk Access -> your terminal), and Photos automation access
to download originals that are only in iCloud.

Usage: python3 <engine>/scripts/find_monitor_photos.py [--since YYYY-MM-DD]
         [--until YYYY-MM-DD] [--dry-run] [--no-download]
       python3 <engine>/scripts/find_monitor_photos.py --promote UUID ... | --reject UUID ...
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import records, workspace

REPO_ROOT = workspace.root()
INBOX_DIR = REPO_ROOT / "data" / "inbox" / "photos"
PHOTOS_DIR = REPO_ROOT / "data" / "raw" / "photos"
STATE_PATH = REPO_ROOT / "data" / "derived" / "photo_finder.json"
CONFIG_PATH = REPO_ROOT / "config" / "athlete.yaml"

PHOTO_EXTS = {".jpeg", ".jpg", ".png", ".heic", ".heif"}

DEFAULTS = {
    "album": "Autotrainer",     # always-stage override album
    "library": None,            # path to a .photoslibrary; default: Photos' own (see resolve_library)
    "export_timeout_s": 180,    # per iCloud-only original fetched through Photos (see _call_with_deadline)
    "min_score": 4,
    "lookback_days": 30,        # first-run window when there's no state yet
    "ocr_confidence": 0.3,
    "near_end_before_s": 120,   # photo within [end - 2 min, end + 10 min] of a
    "near_end_after_s": 600,    # recorded workout -> timing bonus
    "near_end_bonus": 3,
    "extra_brands": [],         # workspace additions, same weight as BRANDS
    "extra_terms": [],          # workspace additions, same weight as STRONG
}

# Scoring vocabulary. Each distinct pattern counts once. OCR on LCD consoles is
# noisy ("watt" reads as wyatt / Walt / W30t), hence the loose variants.
BRANDS = {  # +3: a console or brand name is near-conclusive
    "concept2": r"concept\s*2|\bc2\b", "pm5": r"\bpm[345]\b", "assault": r"\bassault",
    "airdyne": r"air\s*dyne", "schwinn": r"\bschwinn", "echo": r"\becho\s*bike",
    "stairmaster": r"stair\s*master|step\s*mill", "versaclimber": r"versa\s*climber",
    "life_fitness": r"life\s*fitness", "precor": r"\bprecor", "technogym": r"techno\s*gym",
    "matrix": r"\bmatrix\b", "woodway": r"\bwoodway", "peloton": r"\bpeloton", "rogue": r"\brogue\b",
    "wattbike": r"watt\s*bike", "hydrow": r"\bhydrow", "ergatta": r"\bergatta",
}
STRONG = {  # +2: metric vocabulary that rarely appears off a console
    "watts": r"\bwatts?\b", "split": r"\bsplit\b", "per_500m": r"/\s*500\s*m?\b",
    "kcal": r"\bkcal\b", "cal_hr": r"cal\s*/\s*hr", "rpm": r"\brpm\b", "spm": r"\bs/?m\b|\bspm\b",
    "incline": r"\bincline\b", "mph": r"\bmph\b", "kmh": r"km\s*/\s*h", "mets": r"\bmets?\b",
    "floors": r"\bfloors?\b", "projected": r"\bprojected\b", "strokes": r"\bstrokes?\b",
    "elevation": r"\belev(ation)?\b", "interval": r"\bintervals?\b", "kj": r"\bkj\b",
    "mi_km": r"\bm[iu]\s*/\s*km\b",
}
WEAK = {  # +1: common console words that also appear elsewhere
    "watt_ocr": r"\bw[a-z0-9]{1,3}t[a-z]?\b", "cal": r"\bcal(ories)?\b", "pace": r"\bpace\b",
    "distance": r"\bdist(ance)?\b", "time": r"\b(elapsed|time)\b", "level": r"\blevel\b",
    "bpm": r"\bbpm\b|heart\s*rate", "avg": r"\bav(g|e|erage)\b", "console_keys": r"\b(units|display|menu)\b",
    "meters": r"\b\d{3,6}\s*m\b",
}
NEGATIVE = {  # -3: everyday text that shares console vocabulary
    "nutrition": r"total\s*fat|sodium|serving\s*size|carbohydrate|nutrition\s*facts",
    "receipt": r"\bsubtotal\b|\bsales\s*tax\b|\bvisa\b|\bmastercard\b|\bamex\b|\bchange\s*due\b"
               r"|total\s*due|\bauth\s*code\b|\bfare\b",
    # social-app chrome around ads/posts that mention equipment brands
    "social": r"send\s*message|\br/\w+|\bu/\w+|\bupvote|\bsponsored\b",
    # Apple Fitness/Health summaries: the Health export already carries these
    "health_app": r"active\s*calories|during\s*your\s*last|workout\s*details|heart\s*rate:\s*workout",
}
PRICE = re.compile(r"\$\s?\d[\d,]*\.\d{2}")
CLOCK = re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b")
NUMBER = re.compile(r"^\s*\d{2,6}(\.\d)?\s*$")


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        cfg.update((yaml.safe_load(CONFIG_PATH.read_text()) or {}).get("photo_finder") or {})
    return cfg


def score_text(lines: list[str], cfg: dict = DEFAULTS) -> tuple[int, list[str]]:
    """Keyword score for OCR'd lines -> (score, hits). Pure; unit-tested."""
    text = "\n".join(lines).lower()
    brands = {**BRANDS, **{f"extra:{b}": re.escape(b.lower()) for b in cfg.get("extra_brands", [])}}
    strong = {**STRONG, **{f"extra:{t}": re.escape(t.lower()) for t in cfg.get("extra_terms", [])}}
    score, hits = 0, []
    for weight, table in ((3, brands), (2, strong), (1, WEAK), (-3, NEGATIVE)):
        for name, pattern in table.items():
            if re.search(pattern, text):
                score += weight
                hits.append(name)
    if len(PRICE.findall(text)) >= 3:   # quotes, invoices, receipts
        score, hits = score - 3, hits + ["prices"]
    if CLOCK.search(text):
        score, hits = score + 1, hits + ["clock"]
    if sum(bool(NUMBER.match(line)) for line in lines) >= 4:
        score, hits = score + 1, hits + ["numbers"]
    return score, hits


def workout_ends(workouts: list[dict]) -> list[datetime]:
    return sorted(records.parse_dt(w["end"]) for w in workouts if w.get("end"))


def near_workout_end(taken: datetime, ends: list[datetime], cfg: dict = DEFAULTS) -> bool:
    """True if `taken` falls in [end - before, end + after] of any workout. Pure."""
    for end in ends:
        if end.tzinfo is None and taken.tzinfo is not None:
            end = end.replace(tzinfo=taken.tzinfo)
        if -cfg["near_end_before_s"] <= (taken - end).total_seconds() <= cfg["near_end_after_s"]:
            return True
    return False


def score_photo(lines: list[str], taken: datetime, ends: list[datetime],
                cfg: dict = DEFAULTS) -> tuple[int, list[str]]:
    score, hits = score_text(lines, cfg)
    if near_workout_end(taken, ends, cfg):
        score, hits = score + cfg["near_end_bonus"], hits + ["near_workout_end"]
    return score, hits


# ------------------------------------------------------------------- write guard

class UnsafeWrite(RuntimeError):
    pass


def _guard_write(path: Path) -> Path:
    """Refuse any write/move/delete outside the workspace's finder paths.

    Allowed: files inside INBOX_DIR or PHOTOS_DIR, and STATE_PATH itself.
    Refused: anything inside a Photos library bundle, anything elsewhere, and
    any existing file with other hard links (it could be a library original).
    """
    resolved = Path(path).resolve()
    if any(part.endswith(".photoslibrary") for part in resolved.parts):
        raise UnsafeWrite(f"refusing to modify the Photos library: {resolved}")
    allowed_dirs = (INBOX_DIR.resolve(), PHOTOS_DIR.resolve())
    if resolved != STATE_PATH.resolve() and not any(resolved.parent == d for d in allowed_dirs):
        raise UnsafeWrite(f"refusing to write outside the finder's workspace paths: {resolved}")
    if resolved.is_symlink() or Path(path).is_symlink():
        raise UnsafeWrite(f"refusing to modify a symlink: {path}")
    if resolved.exists() and resolved.stat().st_nlink > 1:
        raise UnsafeWrite(f"refusing to modify a hard-linked file: {resolved}")
    return resolved


# ------------------------------------------------------------------- state

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"scanned_through": None, "promoted": [], "rejected": [], "pending": []}


def save_state(state: dict) -> None:
    _guard_write(STATE_PATH)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    for key in ("promoted", "rejected", "pending"):
        state[key] = sorted(set(state.get(key, [])))
    done = set(state["promoted"]) | set(state["rejected"])
    state["pending"] = [u for u in state["pending"] if u not in done]
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def uuid_of(path: Path) -> str:
    """Photos names files <UUID>_1_105_c.jpeg etc.; staged files are <UUID>.<ext>."""
    return path.stem.split("_")[0].upper()


def known_uuids(state: dict) -> set[str]:
    seen = set(state["promoted"]) | set(state["rejected"])
    for d in (PHOTOS_DIR, INBOX_DIR):
        if d.is_dir():
            seen |= {uuid_of(p) for p in d.iterdir() if not p.name.startswith(".")}
    return seen


def staged(uuids: list[str]) -> list[Path]:
    wanted = {u.upper() for u in uuids}
    found = [p for p in INBOX_DIR.iterdir() if uuid_of(p) in wanted] if INBOX_DIR.is_dir() else []
    missing = wanted - {uuid_of(p) for p in found}
    if missing:
        sys.exit(f"not in {INBOX_DIR}: {', '.join(sorted(missing))}")
    return found


# ------------------------------------------------------------------- manual export fallback

def match_exports(files, pending_photos, tolerance_s: float = 2.0):
    """Pair files the user exported from Photos with pending photos.

    files: [(path, exif_iso_or_None)]; pending_photos: objects with uuid,
    original_filename and an aware date. Match by original filename first
    (case-insensitive), else by capture time within tolerance_s — Photos keeps
    EXIF on "Export Unmodified Original". -> ({uuid: path}, unmatched_paths)."""
    by_name = {}
    for p in pending_photos:
        if p.original_filename:
            by_name.setdefault(p.original_filename.lower(), p)
    matched, unmatched = {}, []
    for path, exif in files:
        photo = by_name.get(path.name.lower())
        if photo is None and exif:
            taken = datetime.fromisoformat(exif)
            for p in pending_photos:
                ref = p.date if taken.tzinfo else p.date.replace(tzinfo=None)
                if abs((taken - ref).total_seconds()) <= tolerance_s:
                    photo = p
                    break
        if photo is None or photo.uuid in matched:
            unmatched.append(path)
        else:
            matched[photo.uuid] = path
    return matched, unmatched


def adopt_files(matched: dict, state: dict) -> list:
    """Copy matched exports into the inbox under their photo UUID (the user's
    export folder is left untouched — it is outside the finder's write
    guard), strip identifying EXIF, and clear them from pending."""
    from privacy_check import strip_photo
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    staged = []
    for uuid, src in matched.items():
        dest = _guard_write(INBOX_DIR / f"{uuid}{src.suffix.lower()}")
        shutil.copy2(src, dest)
        strip_photo(_guard_write(dest))
        staged.append(dest)
        state["pending"] = [u for u in state.get("pending", []) if u.upper() != uuid.upper()]
    return staged


def _exif_iso(path: Path) -> str | None:
    from PIL import Image
    import pillow_heif
    from prep_photos import exif_datetime
    pillow_heif.register_heif_opener()
    try:
        with Image.open(path) as im:
            return exif_datetime(im)
    except Exception:  # noqa: BLE001 — not an image we can read; name matching may still work
        return None


def list_pending() -> int:
    osxphotos, _, _ = _photos_backend()
    state = load_state()
    if not state.get("pending"):
        print("nothing pending"); return 0
    db = osxphotos.PhotosDB(dbfile=str(resolve_library(load_config().get("library"))))
    print("pending photos — in Photos, search the filename (or go to the date), select them, then\n"
          "File > Export > Export Unmodified Original... into a folder, and run --adopt <folder>:")
    for p in sorted(db.photos(uuid=sorted(state["pending"])), key=lambda p: p.date):
        print(f"  {p.uuid}  {p.date:%Y-%m-%d %H:%M}  {p.original_filename}  {'local' if p.path else 'iCloud only'}")
    return 0


def adopt(folder: Path) -> int:
    osxphotos, _, _ = _photos_backend()
    state = load_state()
    files = [(f, _exif_iso(f)) for f in sorted(folder.iterdir())
             if f.is_file() and f.suffix.lower() in PHOTO_EXTS]
    if not files:
        sys.exit(f"no photos in {folder}")
    pending = db_photos = []
    if state.get("pending"):
        db = osxphotos.PhotosDB(dbfile=str(resolve_library(load_config().get("library"))))
        db_photos = db.photos(uuid=sorted(state["pending"]))
    matched, unmatched = match_exports(files, db_photos)
    for dest in adopt_files(matched, state):
        print(f"adopted {dest.name} -> data/inbox/photos/")
    for path in unmatched:
        print(f"  not a pending photo (left in place): {path.name}")
    save_state(state)
    print(f"adopt: {len(matched)} staged, {len(unmatched)} unmatched, {len(state['pending'])} still pending")
    return 0


def promote(uuids: list[str]) -> int:
    state = load_state()
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    for p in staged(uuids):
        dest = PHOTOS_DIR / p.name
        _guard_write(p), _guard_write(dest)
        if dest.exists():
            sys.exit(f"{dest} already exists; not overwriting raw data")
        shutil.move(str(p), dest)
        state["promoted"].append(uuid_of(p))
        print(f"promoted {p.name} -> data/raw/photos/")
    save_state(state)
    return 0


def reject(uuids: list[str]) -> int:
    state = load_state()
    for p in staged(uuids):
        _guard_write(p).unlink()
        state["rejected"].append(uuid_of(p))
        print(f"rejected {p.name} (deleted; will not be staged again)")
    save_state(state)
    return 0


# ------------------------------------------------------------------- scanning

DEFAULT_LIBRARY = Path.home() / "Pictures" / "Photos Library.photoslibrary"


def _default_bundle() -> Path:
    return DEFAULT_LIBRARY


def resolve_library(explicit: str | Path | None, workspace_root: Path | None = None) -> Path:
    """The .photoslibrary to read.

    An explicit --library / photo_finder.library value must exist (a relative
    value resolves against the workspace root): a typo must never silently scan
    some other library and then advance the scan watermark past the window.
    Only without one do we try osxphotos' last-opened and system-library
    lookups, then the default bundle in ~/Pictures — lazily, each guarded, so a
    broken Photos preferences file cannot block the run (macOS 27 broke the
    last-opened lookup; the bundle is where Photos keeps the library unless
    the user moved it)."""
    if explicit:
        lib_path = Path(str(explicit)).expanduser()
        if not lib_path.is_absolute():
            lib_path = (workspace_root or REPO_ROOT) / lib_path
        if not lib_path.exists():
            sys.exit(f"Photos library not found: {lib_path} (from --library / photo_finder.library)")
        return lib_path
    from osxphotos import utils
    for lookup in (utils.get_last_library_path, utils.get_system_library_path, _default_bundle):
        try:
            cand = lookup()
        except Exception as e:  # noqa: BLE001 — a lookup failing must not end the run
            print(f"  library lookup {lookup.__name__} failed: {e}", file=sys.stderr)
            continue
        if cand and Path(cand).expanduser().exists():
            return Path(cand).expanduser()
    sys.exit("no Photos library found — pass --library '/path/to/Photos Library.photoslibrary' "
             "or set photo_finder.library in config/athlete.yaml")


def ocr_lines(photo, min_conf: float) -> list[str]:
    from osxphotos.text_detection import detect_text
    path = photo.path or next(iter(photo.path_derivatives or []), None)
    if not path:
        return []
    try:
        return [text for text, conf in detect_text(path) if conf >= min_conf]
    except Exception as e:  # unreadable/corrupt file: report, don't abort the scan
        print(f"  {photo.uuid}: OCR failed ({e})", file=sys.stderr)
        return []


class ExportTimeout(RuntimeError):
    pass


def _call_with_deadline(fn, seconds: float):
    """Run fn() in a daemon thread and give up after `seconds`.

    A Photos-mediated export blocks for as long as macOS waits for the user to
    allow automation of Photos (or while Photos migrates its library after an
    OS upgrade), and that wait has no timeout of its own — the run would sit
    silently forever. An abandoned call is left to die with the process."""
    result: dict = {}

    def run():
        try:
            result["value"] = fn()
        except BaseException as e:  # noqa: BLE001 — re-raised on the caller's thread
            result["error"] = e

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise ExportTimeout(f"no answer from Photos after {int(seconds)}s")
    if "error" in result:
        raise result["error"]
    return result.get("value")


def export_original(photo, dest: Path, download: bool, timeout_s: float | None = None) -> Path | None:
    ext = Path(photo.original_filename).suffix.lower() or ".jpeg"
    name = f"{photo.uuid}{ext}"
    _guard_write(dest / name)
    dest.mkdir(parents=True, exist_ok=True)
    # Copy semantics only: export_as_hardlink=False keeps the staged file
    # independent of the library original; edited/live/raw variants are off.
    common = dict(filename=name, overwrite=True, export_as_hardlink=False,
                  edited=False, live_photo=False, raw_photo=False)
    if photo.path:
        out = photo.export(str(dest), **common)
    elif download:
        # original lives only in iCloud: Photos fetches it (AppleScript) — bounded wait
        out = _call_with_deadline(lambda: photo.export(str(dest), use_photos_export=True, **common),
                                  timeout_s or DEFAULTS["export_timeout_s"])
    else:
        return None
    if not out:
        return None
    return _guard_write(Path(out[0]))   # re-check what export actually wrote


def stage_match(photo, cfg: dict, download: bool, *, photos_ok: bool = True):
    """Export one match into the inbox -> (path | None, photos_ok, note).

    photos_ok turns False the first time Photos fails to answer in time:
    the cause is systemic (macOS never showed its automation prompt, or
    Photos is busy), so the remaining iCloud-only matches are recorded as
    pending at once instead of each waiting out the deadline."""
    if not photo.path and download and not photos_ok:
        return None, False, "skipped: Photos did not answer earlier in this run; recorded as pending"
    try:
        path = export_original(photo, INBOX_DIR, download, cfg.get("export_timeout_s"))
    except UnsafeWrite:
        raise   # a safety violation stops the run; never logged-and-continued
    except ExportTimeout as e:
        return None, False, (f"{e} — macOS never showed its 'control Photos' prompt for this process, or "
                             "Photos is busy. Run once from Terminal.app to get the prompt, grant it under "
                             "System Settings -> Privacy & Security -> Automation, or turn on Photos > "
                             "Settings > iCloud > 'Download Originals to this Mac'; recorded as pending")
    except Exception as e:  # noqa: BLE001 — one bad photo must not end the run
        return None, photos_ok, f"EXPORT FAILED: {e}"
    if path is None:
        return None, photos_ok, "original not local (run without --no-download to fetch it); recorded as pending"
    return path, photos_ok, ""


def classify(pool_items, *, seen, in_album, pending_set, ends, cfg, progress=None):
    """Sort the scan pool -> (matches, near_misses, dropped, scanned, skipped).

    dropped = photos carried over from the pending list that no longer reach
    min_score under the current scoring: they leave the pending list, but they
    are reported, never discarded silently."""
    matches, near_misses, dropped, scanned, skipped = [], [], [], 0, 0
    total = len(pool_items)
    for i, (uuid, photo) in enumerate(sorted(pool_items, key=lambda kv: kv[1].date), 1):
        if progress and (i % 25 == 0 or i == total):
            progress(i, total)
        if uuid.upper() in seen or photo.intrash:
            skipped += 1
            continue
        scanned += 1
        if uuid in in_album:
            matches.append((photo, None, ["album"]))
            continue
        score, hits = score_photo(ocr_lines(photo, cfg["ocr_confidence"]), photo.date, ends, cfg)
        if score >= cfg["min_score"]:
            matches.append((photo, score, hits))
        elif "near_workout_end" in hits:
            near_misses.append((photo, score, hits))
        elif uuid.upper() in pending_set:
            dropped.append((photo, score, hits))
    return matches, near_misses, dropped, scanned, skipped


def _photos_backend():
    """The deferred imports scan() needs (osxphotos is macOS-only and slow to
    import). Kept in one tested function so a wrong import path can't hide
    inside a code path the tests never reach."""
    import osxphotos
    from osxphotos.photosdb.photosdb import PhotosDBReadError
    from privacy_check import strip_photo
    return osxphotos, PhotosDBReadError, strip_photo


def scan(since: datetime, until: datetime, cfg: dict, *, dry_run: bool, download: bool) -> int:
    osxphotos, PhotosDBReadError, strip_photo = _photos_backend()

    library = resolve_library(cfg.get("library"))
    try:
        db = osxphotos.PhotosDB(dbfile=str(library))
    except FileNotFoundError as e:
        sys.exit(f"{library} has no readable Photos database ({e}); is it the right bundle? "
                 "Pass --library to point at the library Photos opens.")
    except (PhotosDBReadError, sqlite3.DatabaseError) as e:
        sys.exit(f"{library} is not a readable Photos library ({e.__class__.__name__}: {str(e)[:120]}) "
                 "— an iPhoto library or not a Photos bundle? Pass --library to the one Photos opens.")
    except OSError as e:
        sys.exit(f"cannot open {library} ({e.__class__.__name__}: {str(e)[:120]}). Grant Full "
                 "Disk Access to the app running this script (System Settings -> Privacy & "
                 "Security -> Full Disk Access), restart it, and re-run.")
    print(f"photo finder: library {library}", flush=True)
    state = load_state()
    seen = known_uuids(state)
    album = cfg["album"]
    in_album = {p.uuid for p in db.photos(albums=[album], movies=False)} if album in db.albums else set()
    window = db.photos(movies=False, from_date=since, to_date=until)
    pool = {p.uuid: p for p in window}
    # matches from earlier runs that couldn't be staged: retried until staged
    retry = set(state.get("pending", [])) | in_album
    pool.update({p.uuid: p for p in db.photos(uuid=sorted(retry))} if retry else {})

    ends = workout_ends(records.load_records())
    pending_set = {u.upper() for u in state.get("pending", [])}
    print(f"photo finder: reading text from up to {len(pool)} photo(s) "
          f"({since:%Y-%m-%d} -> {until:%Y-%m-%d})...", flush=True)
    matches, near_misses, dropped, scanned, skipped = classify(
        list(pool.items()), seen=seen, in_album=in_album, pending_set=pending_set, ends=ends, cfg=cfg,
        progress=lambda i, n: print(f"  {i}/{n}", flush=True))

    print(f"photo finder: {since:%Y-%m-%d} -> {until:%Y-%m-%d}: {scanned} scanned, "
          f"{skipped} already seen, {len(matches)} match(es); {len(ends)} workout end times")
    if not ends:
        print("  (no workout records yet — parse Health exports first for the timing bonus)")
    not_local, still_pending = 0, []
    via_photos = [p for p, _, _ in matches if not p.path]
    if via_photos and download and not dry_run:
        print(f"  {len(via_photos)} original(s) live only in iCloud and will be fetched through "
              f"Photos (up to {cfg['export_timeout_s']}s each) — if macOS asks to allow control "
              "of Photos, click OK", flush=True)
    photos_ok = True
    for photo, score, hits in matches:
        label = f"score {score}" if score is not None else f"album '{album}'"
        line = f"  {photo.uuid}  {photo.date:%Y-%m-%d %H:%M}  {label}  [{', '.join(hits)}]"
        if dry_run:
            print(line)
            continue
        path, photos_ok, note = stage_match(photo, cfg, download, photos_ok=photos_ok)
        if path is None:
            print(f"{line}  {note}", file=sys.stderr, flush=True)
            not_local += 1
            still_pending.append(photo.uuid.upper())
            continue
        strip_photo(_guard_write(path))
        print(f"{line}  -> data/inbox/photos/{path.name}")
    for photo, score, hits in near_misses:
        print(f"  near-miss {photo.uuid}  {photo.date:%Y-%m-%d %H:%M}  score {score}  "
              f"[{', '.join(hits)}] — not staged; add to album '{album}' if it's a monitor")
    for photo, score, hits in dropped:
        print(f"  dropped {photo.uuid}  {photo.date:%Y-%m-%d %H:%M}  score {score} < {cfg['min_score']} under "
              f"current scoring  [{', '.join(hits)}] — no longer pending; add it to album '{album}' if it is a monitor")
    if not_local:
        print(f"  {not_local} match(es) not staged (original not local or export failed); "
              "recorded as pending and retried on every run until staged")
    if not dry_run:
        state["scanned_through"] = until.isoformat(timespec="seconds")
        state["pending"] = still_pending
        save_state(state)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="YYYY-MM-DD (default: last scan, else lookback_days)")
    ap.add_argument("--until", help="YYYY-MM-DD, inclusive (default: now)")
    ap.add_argument("--dry-run", action="store_true", help="list matches; export nothing, keep state")
    ap.add_argument("--no-download", action="store_true", help="skip matches whose original is only in iCloud")
    ap.add_argument("--library", help="Photos library bundle to read (default: the one Photos opens)")
    ap.add_argument("--promote", nargs="+", metavar="UUID")
    ap.add_argument("--reject", nargs="+", metavar="UUID")
    ap.add_argument("--list-pending", action="store_true",
                    help="show pending photos with filenames/dates so they can be exported from Photos by hand")
    ap.add_argument("--adopt", metavar="DIR", type=Path,
                    help="stage photos exported from Photos by hand (matched to pending by filename or capture time)")
    args = ap.parse_args()
    workspace.require(REPO_ROOT)
    if args.list_pending:
        return list_pending()
    if args.adopt:
        return adopt(args.adopt)
    if args.promote:
        return promote(args.promote)
    if args.reject:
        return reject(args.reject)

    cfg = load_config()
    if args.library:
        cfg["library"] = args.library
    now = datetime.now().astimezone()
    until = (datetime.fromisoformat(args.until).astimezone() + timedelta(days=1)) if args.until else now
    if args.since:
        since = datetime.fromisoformat(args.since).astimezone()
    elif load_state()["scanned_through"]:
        since = datetime.fromisoformat(load_state()["scanned_through"])
    else:
        since = now - timedelta(days=cfg["lookback_days"])
    return scan(since, until, cfg, dry_run=args.dry_run, download=not args.no_download)


if __name__ == "__main__":
    raise SystemExit(main())
