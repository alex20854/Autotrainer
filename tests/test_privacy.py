"""Privacy guard tests — including a live audit of the actual repo content,
so `pytest` itself fails if a location/identity leak ever lands in tracked
files or photos."""

import re

from conftest import REPO_ROOT

import privacy_check as pc


# Positive-case PII samples are assembled at runtime (never literal in this
# file) so the repo-wide audit below stays clean without excluding this file.
PHONE = "703" + "-555-" + "0142"
PHONE_PARENS = "(703)" + " 555-" + "0142"
ADDRESS = "4501 Back" + "lick Rd"
ADDRESS2 = "12 Oak " + "Street"
EMAIL = "j.doe@" + "corp.com"
CORP_EMAIL = "someone@" + "cisco.com"


def test_phone_matches_real_numbers_not_dois():
    assert pc.PHONE_RE.search(f"call {PHONE} tonight")
    assert pc.PHONE_RE.search(PHONE_PARENS)
    # DOI / article-number fragments must not match (real case: evidence.md)
    assert not pc.PHONE_RE.search("s41746-025-02238-1")
    assert not pc.PHONE_RE.search("Med Sci Sports Exerc 39(4):665-671")


def test_address_matches_street_not_prose():
    assert pc.ADDRESS_RE.search(f"meet at {ADDRESS} for the run")
    assert not pc.ADDRESS_RE.search("progress by 10 watts per week")
    assert not pc.ADDRESS_RE.search("180 - age formula")


def test_email_allowlist():
    assert pc.EMAIL_ALLOWLIST.search("12345+user@" + "users.noreply.github.com")
    assert pc.EMAIL_ALLOWLIST.search("noreply@" + "anthropic.com")
    assert not pc.EMAIL_ALLOWLIST.search(CORP_EMAIL)


def test_text_check_flags_and_passes(tmp_path):
    dirty = tmp_path / "dirty.md"
    dirty.write_text(f"Contact John at {EMAIL} or {PHONE}, he lives at {ADDRESS2}.")
    findings = pc.check_text(dirty, personal=[re.compile("John Doe", re.I)])
    kinds = " ".join(findings)
    assert "email" in kinds and "phone" in kinds and "street address" in kinds

    clean = tmp_path / "clean.md"
    clean.write_text("Zone 2 ride, 45 min at 138 W, decoupling 3.1%")
    assert pc.check_text(clean, personal=[]) == []


def test_repo_photos_have_no_gps_or_owner_exif():
    photos = [p for p in pc.PHOTOS_DIR.iterdir()
              if p.suffix.lower() in pc.PHOTO_EXTS]
    assert photos, "expected photos in data/raw/photos"
    for photo in photos:
        assert pc.check_photo(photo) == [], f"identifying EXIF in {photo.name}"


def test_tracked_text_files_are_clean():
    personal = pc.load_personal_patterns()
    findings = []
    for path in pc.tracked_files():
        if (path.suffix.lower() in pc.TEXT_EXTS and path.exists()
                and str(path.relative_to(REPO_ROOT)) not in pc.EXCLUDE):
            findings.extend(pc.check_text(path, personal))
    assert findings == [], f"privacy findings in tracked files: {findings}"
