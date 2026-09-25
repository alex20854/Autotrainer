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
import sys
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

DEFAULTS = {
    "album": "Autotrainer",     # always-stage override album
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
    "concept2": r"concept\s*2|\bc2\b", "pm5": r"\bpm\s*[345]\b", "assault": r"\bassault",
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
NEGATIVE = {  # -3: receipts and nutrition labels also say "cal"
    "nutrition": r"total\s*fat|sodium|serving\s*size|carbohydrate|nutrition\s*facts",
    "receipt": r"\bsubtotal\b|\bsales\s*tax\b|\bvisa\b|\bmastercard\b|\bchange\s*due\b",
}
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
    return {"scanned_through": None, "promoted": [], "rejected": []}


def save_state(state: dict) -> None:
    _guard_write(STATE_PATH)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["promoted"], state["rejected"] = sorted(set(state["promoted"])), sorted(set(state["rejected"]))
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


def export_original(photo, dest: Path, download: bool) -> Path | None:
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
        out = photo.export(str(dest), use_photos_export=True, **common)
    else:
        return None
    if not out:
        return None
    return _guard_write(Path(out[0]))   # re-check what export actually wrote


def scan(since: datetime, until: datetime, cfg: dict, *, dry_run: bool, download: bool) -> int:
    import osxphotos
    from privacy_check import strip_photo

    try:
        db = osxphotos.PhotosDB()
    except OSError as e:
        sys.exit(f"cannot open the Photos library ({e.__class__.__name__}). Grant Full Disk "
                 "Access to the app running this script (System Settings -> Privacy & Security "
                 "-> Full Disk Access), restart it, and re-run.")
    state = load_state()
    seen = known_uuids(state)
    album = cfg["album"]
    in_album = {p.uuid for p in db.photos(albums=[album], movies=False)} if album in db.albums else set()
    window = db.photos(movies=False, from_date=since, to_date=until)
    pool = {p.uuid: p for p in window}
    pool.update({p.uuid: p for p in db.photos(uuid=list(in_album))} if in_album else {})

    ends = workout_ends(records.load_records())
    matches, near_misses, scanned, skipped = [], [], 0, 0
    for uuid, photo in sorted(pool.items(), key=lambda kv: kv[1].date):
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

    print(f"photo finder: {since:%Y-%m-%d} -> {until:%Y-%m-%d}: {scanned} scanned, "
          f"{skipped} already seen, {len(matches)} match(es); {len(ends)} workout end times")
    if not ends:
        print("  (no workout records yet — parse Health exports first for the timing bonus)")
    not_local = 0
    for photo, score, hits in matches:
        label = f"score {score}" if score is not None else f"album '{album}'"
        line = f"  {photo.uuid}  {photo.date:%Y-%m-%d %H:%M}  {label}  [{', '.join(hits)}]"
        if dry_run:
            print(line)
            continue
        try:
            path = export_original(photo, INBOX_DIR, download)
        except UnsafeWrite:
            raise   # a safety violation stops the run; never logged-and-continued
        except Exception as e:
            path = None
            print(f"{line}  EXPORT FAILED: {e}", file=sys.stderr)
        if path is None:
            not_local += 1
            continue
        strip_photo(_guard_write(path))
        print(f"{line}  -> data/inbox/photos/{path.name}")
    for photo, score, hits in near_misses:
        print(f"  near-miss {photo.uuid}  {photo.date:%Y-%m-%d %H:%M}  score {score}  "
              f"[{', '.join(hits)}] — not staged; add to album '{album}' if it's a monitor")
    if not_local:
        print(f"  {not_local} match(es) not staged (original not local or export failed); "
              "they stay unseen and will be retried next run")
    if not dry_run:
        state["scanned_through"] = until.isoformat(timespec="seconds")
        save_state(state)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="YYYY-MM-DD (default: last scan, else lookback_days)")
    ap.add_argument("--until", help="YYYY-MM-DD, inclusive (default: now)")
    ap.add_argument("--dry-run", action="store_true", help="list matches; export nothing, keep state")
    ap.add_argument("--no-download", action="store_true", help="skip matches whose original is only in iCloud")
    ap.add_argument("--promote", nargs="+", metavar="UUID")
    ap.add_argument("--reject", nargs="+", metavar="UUID")
    args = ap.parse_args()
    workspace.require(REPO_ROOT)
    if args.promote:
        return promote(args.promote)
    if args.reject:
        return reject(args.reject)

    cfg = load_config()
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
