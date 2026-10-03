#!/usr/bin/env python3
"""Privacy guard for a PUBLIC repo: block location and identity leaks.

The athlete accepts training data (HR, watts, plans) being public; what must
never land in git is *where to find them* or *who exactly they are*:

  - GPS/location EXIF in photos (fail) + owner/serial EXIF (fail)
  - location-bearing files: GPX/KML/KMZ/GeoJSON (fail outright, compressed
    too), TCX with trackpoint positions (fail; also TCX saved as .xml), FIT,
    compressed activity files and archives (cannot be inspected: fail unless
    listed under `allow_files:` in config/privacy.local.yaml), and numeric
    latitude/longitude values in JSON/JSONL/JS/HTML text — scalars, arrays,
    latlng pairs, GeoJSON coordinates, FIT semicircles (fail)
  - street addresses, phone numbers, personal email addresses in text (fail;
    noreply committer emails are allowlisted)
  - personal strings from config/privacy.local.yaml (gitignored — your full
    name, street, employer, etc. live ONLY in that local file, never in the
    repo itself)
  - git identity: warns when git user.email is a personal/corporate address
    (use a noreply address; GitHub web uploads use your account email —
    enable GitHub's "Keep my email addresses private")

Modes:
  --staged      check only files staged for commit (pre-commit hook mode);
                content is read from the index, i.e. what the commit records
  --strip-gps   rewrite photos in data/raw/photos/ dropping GPS + serial/owner
                EXIF in place (the ONE sanctioned mutation of raw/ — privacy
                beats immutability)
  (default)     audit every tracked file + all photos

Exit 1 on findings so the pre-commit hook blocks; after human review a
deliberate `git commit --no-verify` overrides.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import workspace


def _git_toplevel() -> Path:
    """The repo being guarded: engine or workspace, whichever we're inside."""
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True).stdout.strip()
    return Path(out) if out else workspace.root()


REPO_ROOT = _git_toplevel()
PHOTOS_DIR = REPO_ROOT / "data" / "raw" / "photos"
LOCAL_CONFIG = REPO_ROOT / "config" / "privacy.local.yaml"

PHOTO_EXTS = {".jpeg", ".jpg", ".png", ".heic", ".heif"}
TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".jsonl", ".py", ".txt", ".csv", ".xml", ".sh",
             ".html", ".htm", ".svg", ".js", ".tsv", ".toml"}
# Formats whose whole purpose is a track or a place: never committed.
LOCATION_EXTS = {".gpx", ".kml", ".kmz", ".geojson"}
# Binary activity files that may carry GPS but cannot be inspected here; each
# one needs a deliberate allow_files entry in config/privacy.local.yaml.
OPAQUE_EXTS = {".fit"}
# Compressed files are classified by the suffix underneath (ride.gpx.gz is a
# GPX); whatever is inside cannot be inspected, so they are opaque otherwise.
COMPRESSED_EXTS = {".gz", ".bz2", ".xz", ".zst"}
# Archives (bulk Strava/Garmin/Health exports) are opaque too.
ARCHIVE_EXTS = {".zip", ".tar", ".tgz", ".7z", ".rar"}
# Text formats that can embed JSON objects (a dashboard inlines its data).
JSONISH_EXTS = {".json", ".jsonl", ".js", ".html", ".htm"}
SVG_EXTS = {".svg", ".html", ".htm"}

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
# TCX trackpoints carry <Position><LatitudeDegrees>..; any of them is a route.
TCX_POSITION_RE = re.compile(r"<\s*(?:\w+:)?(?:Position|LatitudeDegrees|LongitudeDegrees)\b")
# Generic .xml gets only the TCX-specific element names (<Position> alone is
# too common a word to fail an arbitrary XML file on).
XML_DEGREES_RE = re.compile(r"<\s*(?:\w+:)?(?:LatitudeDegrees|LongitudeDegrees)\b")
# A numeric value under a coordinate key (the key family pull_health.py
# scrubs). Keys may be "quoted", \"escaped\" (JSON inlined in a JS string) or
# bare (JS object literals). Values may sit inside arrays or a {"data": ...}
# wrapper. "long" alone is left out: too often a duration or a flag.
#   degrees:     "lat": 12.34  "start_longitude": "-56.7"  "startLat": 1
#                "lat": [0.1, 0.2]  {lat: 0.1}  {\"lng\":-0.4}
#   pairs:       "start_latlng": [0.1, -0.4]  "latlng": {"data": [[0.1, -0.4]]}
#   GeoJSON:     "coordinates": [[-0.4, 0.1]]  (needs an array of decimals)
#   semicircles: "position_lat": 14680064  (FIT records decoded to JSON)
_KEY_OPEN = r'(?<![\w$])(?P<q>\\?"|\'|)'
_KEY_CLOSE = r'(?P=q)\s*:\s*'
_WRAP = r'(?:[\[{]\s*(?:\\?"\w+\\?"\s*:\s*)?)'       # [  [[  {"data":
_NUM = r'-?\d{1,3}(?:\.\d+)?\b'
COORD_RE = re.compile(
    _KEY_OPEN + r'(?:'
    r'(?:(?:[A-Za-z]+_)?(?i:lat|latitude|lon|lng|longitude)'
    r'|[a-z]+(?:Lat|Latitude|Lon|Lng|Longitude))' + _KEY_CLOSE + _WRAP + r'*"?' + _NUM +
    r'|(?:(?:[A-Za-z]+_)?(?i:latlng)|[a-z]+LatLng)' + _KEY_CLOSE + _WRAP + r'+' + _NUM +
    r'|coordinates' + _KEY_CLOSE + _WRAP + r'+-?\d{1,3}\.\d+' +
    r'|(?:[A-Za-z]+_)?position_(?:lat|long)' + _KEY_CLOSE + r'"?-?\d+\b'
    r')'
)
# Numeric SVG geometry (polyline points, path data, coordinates, sizes) is
# chart drawing, not text: blank it before the phone/address/SSN regexes so a
# run of plotted numbers can never read as a phone number. Values containing
# anything but numbers and path-command letters are still scanned.
SVG_NUMERIC_ATTR_RE = re.compile(
    r'\b(?:points|d|viewBox|x[12]?|y[12]?|cx|cy|r|rx|ry|width|height)'
    r'="[-+0-9.,eE\sMmLlHhVvCcSsQqTtAaZz]*"'
)


def load_local_config() -> dict:
    if not LOCAL_CONFIG.exists():
        return {}
    return yaml.safe_load(LOCAL_CONFIG.read_text(encoding="utf-8")) or {}


def load_personal_patterns() -> list[re.Pattern]:
    return [re.compile(re.escape(term), re.IGNORECASE)
            for term in load_local_config().get("never_commit", []) if term]


def load_allow_files() -> set[str]:
    """Repo-relative paths of opaque files (e.g. .fit) reviewed and allowed."""
    return {Path(str(f)).as_posix() for f in load_local_config().get("allow_files", []) or [] if f}


def check_photo(path: Path, data: bytes | None = None) -> list[str]:
    """`data` is the file's content when it does not come from `path` (index)."""
    from PIL import Image, ExifTags
    import pillow_heif
    pillow_heif.register_heif_opener()
    findings = []
    with Image.open(io.BytesIO(data) if data is not None else path) as im:
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


def check_text(path: Path, personal: list[re.Pattern], data: bytes | None = None) -> list[str]:
    if data is not None:
        text = data.decode("utf-8", errors="ignore")
    else:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
    findings = []
    suffix = path.suffix.lower()
    if suffix in JSONISH_EXTS:
        for m in COORD_RE.finditer(text):
            findings.append(f"{_rel(path)}: coordinate value {m.group()!r} — location leak")
    if ((suffix == ".tcx" and TCX_POSITION_RE.search(text))
            or (suffix == ".xml" and XML_DEGREES_RE.search(text))):
        findings.append(f"{_rel(path)}: TCX with trackpoint positions — GPS route leak")
    if suffix in SVG_EXTS:
        text = SVG_NUMERIC_ATTR_RE.sub("", text)
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


def check_name(path: Path, allow_files: set[str]) -> list[str] | None:
    """Findings decided by the file name alone (no content needed), or None.

    Location formats fail outright (compressed too); opaque files (FIT,
    compressed, archives) fail unless allow-listed."""
    suffixes = [s.lower() for s in path.suffixes]
    suffix = suffixes[-1] if suffixes else ""
    inner = suffixes[-2] if suffix in COMPRESSED_EXTS and len(suffixes) > 1 else ""
    if suffix in LOCATION_EXTS or inner in LOCATION_EXTS:
        return [f"{_rel(path)}: {inner or suffix} is a location format — never commit tracks or places"]
    if suffix in OPAQUE_EXTS | COMPRESSED_EXTS | ARCHIVE_EXTS:
        if _rel(path) in allow_files:
            return []
        kind = ("binary" if suffix in OPAQUE_EXTS
                else "an archive" if suffix in ARCHIVE_EXTS else "compressed")
        return [f"{_rel(path)}: {''.join(suffixes[-2:]) if inner else suffix} is {kind} and may "
                "carry GPS — strip it or list it under allow_files in "
                "config/privacy.local.yaml after review"]
    return None


def check_file(path: Path, personal: list[re.Pattern], allow_files: set[str],
               data: bytes | None = None) -> list[str]:
    """Findings for one file, dispatched on its extension. Content comes from
    `data` when given (the staged blob), else from the working-tree file."""
    by_name = check_name(path, allow_files)
    if by_name is not None:
        return by_name
    suffix = path.suffix.lower()
    if suffix in PHOTO_EXTS:
        return check_photo(path, data)
    if suffix in TEXT_EXTS or suffix == ".tcx" or path.name in (".gitignore",):
        return check_text(path, personal, data)
    return []


def audit(files: list[Path], personal: list[re.Pattern], allow_files: set[str],
          staged: bool = False) -> list[str]:
    """Check `files`. staged=True reads content from the index (what the commit
    will record), so a staged file later edited or deleted on disk is still
    judged as staged; otherwise the working tree is read. Name-based findings
    never need the file to exist."""
    findings = []
    for path in files:
        if _rel(path) in EXCLUDE:
            continue
        by_name = check_name(path, allow_files)
        if by_name is not None:
            findings.extend(by_name)
        elif staged:
            data = _index_blob(path)
            if data is not None:
                findings.extend(check_file(path, personal, allow_files, data))
        elif path.exists():
            findings.extend(check_file(path, personal, allow_files))
    return findings


def _index_blob(path: Path) -> bytes | None:
    """The staged content of `path`, or None if it is not in the index."""
    res = subprocess.run(["git", "cat-file", "blob", f":{_rel(path)}"],
                         capture_output=True, cwd=REPO_ROOT)
    return res.stdout if res.returncode == 0 else None


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


# -z: NUL-separated, unquoted paths. Without it git C-quotes non-ASCII names
# ("Run \342\200\223 Lake.gpx"), which then match no file and are skipped.
def staged_files() -> list[Path]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"],
                         capture_output=True, text=True, cwd=REPO_ROOT).stdout
    return [REPO_ROOT / name for name in out.split("\0") if name]


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True,
                         cwd=REPO_ROOT).stdout
    return [REPO_ROOT / name for name in out.split("\0") if name]


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
        photos = sorted(PHOTOS_DIR.iterdir()) if PHOTOS_DIR.is_dir() else []
        stripped = [p for p in photos
                    if p.suffix.lower() in PHOTO_EXTS and strip_photo(p)]
        print(f"stripped EXIF from {len(stripped)} photo(s)")
        for p in stripped:
            print(f"  {_rel(p)}")
        return 0

    files = staged_files() if args.staged else tracked_files()
    findings = audit(files, load_personal_patterns(), load_allow_files(), staged=args.staged)
    findings.extend(check_git_identity())

    if findings:
        print("PRIVACY CHECK FAILED:", file=sys.stderr)
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
