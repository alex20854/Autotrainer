#!/usr/bin/env python3
"""Privacy guard for a PUBLIC repo: block location and identity leaks.

The athlete accepts training data (HR, watts, plans) being public; what must
never land in git is *where to find them* or *who exactly they are*:

  - GPS/location EXIF in photos (fail) + owner/serial EXIF (fail)
  - street addresses, phone numbers, personal email addresses in text (fail;
    noreply committer emails are allowlisted)
  - personal strings from config/privacy.local.yaml (gitignored — your full
    name, street, employer, etc. live ONLY in that local file, never in the
    repo itself)
  - git identity: warns when git user.email is a personal/corporate address
    (use a noreply address; GitHub web uploads use your account email —
    enable GitHub's "Keep my email addresses private")

Modes:
  --staged      check only files staged for commit (pre-commit hook mode)
  --strip-gps   rewrite photos in data/raw/photos/ dropping GPS + serial/owner
                EXIF in place (the ONE sanctioned mutation of raw/ — privacy
                beats immutability)
  (default)     audit every tracked file + all photos

Exit 1 on findings so the pre-commit hook blocks; after human review a
deliberate `git commit --no-verify` overrides.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PHOTOS_DIR = REPO_ROOT / "data" / "raw" / "photos"
LOCAL_CONFIG = REPO_ROOT / "config" / "privacy.local.yaml"

PHOTO_EXTS = {".jpeg", ".jpg", ".png", ".heic", ".heif"}
TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".jsonl", ".py", ".txt", ".csv", ".xml", ".sh"}

# The template intentionally shows placeholder PII patterns; everything else is fair game.
EXCLUDE = {"config/privacy.local.yaml.example"}

GPS_IFD = 0x8825
RISKY_EXIF = ("BodySerialNumber", "CameraOwnerName", "Artist", "Copyright")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_ALLOWLIST = re.compile(r"(@users\.noreply\.github\.com|noreply@anthropic\.com|@example\.com)$")
# digit-boundary guards keep DOIs/citation ranges (e.g. s41746-025-02238-1) out
PHONE_RE = re.compile(r"(?<![\d-])(?:\+?1[-. ])?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?![\d-])")
ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Z][A-Za-z]+\s+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Ct|Court|Blvd|Boulevard|Way|Terrace|Pl|Place)\b\.?",
)
SSN_RE = re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])")


def load_personal_patterns() -> list[re.Pattern]:
    if not LOCAL_CONFIG.exists():
        return []
    cfg = yaml.safe_load(LOCAL_CONFIG.read_text(encoding="utf-8")) or {}
    return [re.compile(re.escape(term), re.IGNORECASE)
            for term in cfg.get("never_commit", []) if term]


def check_photo(path: Path) -> list[str]:
    from PIL import Image, ExifTags
    import pillow_heif
    pillow_heif.register_heif_opener()
    findings = []
    with Image.open(path) as im:
        ex = im.getexif()
        if ex and ex.get_ifd(GPS_IFD):
            findings.append(f"{_rel(path)}: GPS EXIF present — location leak")
        tags = {ExifTags.TAGS.get(k, k): v for k, v in (ex.items() if ex else [])}
        for tag in RISKY_EXIF:
            if tags.get(tag):
                findings.append(f"{_rel(path)}: identifying EXIF {tag}={tags[tag]!r}")
    return findings


def strip_photo(path: Path) -> bool:
    """Drop GPS + identifying EXIF in place. Returns True if rewritten."""
    from PIL import Image, ExifTags
    import pillow_heif
    pillow_heif.register_heif_opener()
    with Image.open(path) as im:
        ex = im.getexif()
        dirty = bool(ex and ex.get_ifd(GPS_IFD))
        name_to_id = {v: k for k, v in ExifTags.TAGS.items()}
        for tag in RISKY_EXIF:
            if ex and ex.get(name_to_id[tag]):
                dirty = True
        if not dirty:
            return False
        if GPS_IFD in ex:
            del ex[GPS_IFD]
        for tag in RISKY_EXIF:
            ex.pop(name_to_id[tag], None)
        fmt = "JPEG" if path.suffix.lower() in {".jpg", ".jpeg"} else im.format
        im.save(path, fmt, exif=ex.tobytes(), quality=95)
    return True


def check_text(path: Path, personal: list[re.Pattern]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings = []
    for m in EMAIL_RE.finditer(text):
        if not EMAIL_ALLOWLIST.search(m.group()):
            findings.append(f"{_rel(path)}: email address {m.group()!r}")
    for regex, label in ((PHONE_RE, "phone number"), (ADDRESS_RE, "street address"),
                         (SSN_RE, "SSN-like number")):
        for m in regex.finditer(text):
            findings.append(f"{_rel(path)}: possible {label} {m.group()!r}")
    for pat in personal:
        if pat.search(text):
            findings.append(f"{_rel(path)}: personal term {pat.pattern!r} (privacy.local.yaml)")
    return findings


def check_git_identity() -> list[str]:
    try:
        email = subprocess.run(["git", "config", "user.email"], capture_output=True,
                               text=True, cwd=REPO_ROOT).stdout.strip()
    except OSError:
        return []
    if email and not EMAIL_ALLOWLIST.search(email):
        return [f"git user.email is {email!r} — commits will publish it; "
                "use a noreply address (GitHub: Settings → Emails → Keep private)"]
    return []


def staged_files() -> list[Path]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         capture_output=True, text=True, cwd=REPO_ROOT).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line]


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         cwd=REPO_ROOT).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true", help="check staged files only")
    ap.add_argument("--strip-gps", action="store_true",
                    help="rewrite photos dropping GPS/identifying EXIF")
    args = ap.parse_args()

    if args.strip_gps:
        stripped = [p for p in sorted(PHOTOS_DIR.iterdir())
                    if p.suffix.lower() in PHOTO_EXTS and strip_photo(p)]
        print(f"stripped EXIF from {len(stripped)} photo(s)")
        for p in stripped:
            print(f"  {_rel(p)}")
        return 0

    files = staged_files() if args.staged else tracked_files()
    personal = load_personal_patterns()
    findings = []
    for path in files:
        if not path.exists() or _rel(path) in EXCLUDE:
            continue
        suffix = path.suffix.lower()
        if suffix in PHOTO_EXTS:
            findings.extend(check_photo(path))
        elif suffix in TEXT_EXTS or path.name in (".gitignore",):
            findings.extend(check_text(path, personal))
    findings.extend(check_git_identity())

    if findings:
        print("PRIVACY CHECK FAILED — this repo is public:", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print("\nFix the finding (photos: scripts/privacy_check.py --strip-gps), or\n"
              "after human review override deliberately with git commit --no-verify.",
              file=sys.stderr)
        return 1
    scope = "staged files" if args.staged else f"{len(files)} tracked files"
    print(f"privacy check clean ({scope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
