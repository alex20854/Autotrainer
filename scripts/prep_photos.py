#!/usr/bin/env python3
"""Photo prep: HEIC->JPEG conversion + EXIF timestamp extraction.

For every photo in data/raw/photos/ without a sidecar in data/derived/photos/,
this writes a sidecar seeded with the deterministic fields (paths, EXIF time)
and extracted: false. Claude fills in the vision fields during /coach ingest.
HEIC originals get a JPEG copy in data/derived/photos_converted/ (Claude's
vision reads JPEG/PNG, not HEIC); raw files are never modified.

EXIF DateTimeOriginal is naive local time — the matching layer interprets it
in config/athlete.yaml's timezone (docs/schema.md, Timezone rules).

Requires Pillow + pillow-heif (requirements.txt). On a Mac without them,
`sips -s format jpeg in.heic --out out.jpg` is the manual fallback.

Usage: python3 scripts/prep_photos.py [--photos DIR] [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from PIL import Image, ExifTags
import pillow_heif

pillow_heif.register_heif_opener()

REPO_ROOT = Path(__file__).resolve().parents[1]
PHOTOS_DIR = REPO_ROOT / "data" / "raw" / "photos"
SIDECAR_DIR = REPO_ROOT / "data" / "derived" / "photos"
CONVERTED_DIR = REPO_ROOT / "data" / "derived" / "photos_converted"

PHOTO_EXTS = {".jpeg", ".jpg", ".png", ".heic", ".heif"}
DATETIME_ORIGINAL = 0x9003
EXIF_IFD = 0x8769


def exif_datetime(im: Image.Image) -> str | None:
    exif = im.getexif()
    if not exif:
        return None
    value = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) or exif.get(ExifTags.Base.DateTime)
    if not value:
        return None
    # EXIF format "YYYY:MM:DD HH:MM:SS" -> ISO naive
    date, _, time = str(value).partition(" ")
    return f"{date.replace(':', '-')}T{time}"


def prep_photo(photo: Path, force: bool = False) -> dict | None:
    sidecar_path = SIDECAR_DIR / f"{photo.stem}.yaml"
    if sidecar_path.exists() and not force:
        return None

    with Image.open(photo) as im:
        taken = exif_datetime(im)
        converted = None
        if photo.suffix.lower() in {".heic", ".heif"}:
            CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
            converted = CONVERTED_DIR / f"{photo.stem}.jpg"
            im.convert("RGB").save(converted, "JPEG", quality=90)

    sidecar = {
        "photo": str(photo.relative_to(REPO_ROOT)),
        "converted": str(converted.relative_to(REPO_ROOT)) if converted else None,
        "exif_time": taken,
        "extracted": False,
        "machine": None,
        "machine_confidence": None,
        "fields": {},
        "splits": [],
        "notes": "",
    }
    SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")
    return sidecar


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--photos", type=Path, default=PHOTOS_DIR)
    ap.add_argument("--force", action="store_true", help="rewrite existing sidecars")
    args = ap.parse_args()

    photos = sorted(p for p in args.photos.iterdir() if p.suffix.lower() in PHOTO_EXTS) \
        if args.photos.is_dir() else []
    new = no_exif = 0
    for photo in photos:
        sidecar = prep_photo(photo, force=args.force)
        if sidecar:
            new += 1
            if not sidecar["exif_time"]:
                no_exif += 1
                print(f"WARNING: no EXIF timestamp in {photo.name} — "
                      f"matching will need manual timing", file=sys.stderr)
    pending = sum(1 for s in SIDECAR_DIR.glob("*.yaml")
                  if not yaml.safe_load(s.read_text()).get("extracted"))
    print(f"photos: {len(photos)} total, {new} new sidecars ({no_exif} missing EXIF), "
          f"{pending} pending vision extraction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
