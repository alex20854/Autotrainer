import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

import find_monitor_photos as fmp

from conftest import WORKSPACE, requires_workspace

# Real Vision OCR output from Concept2 PM5 photos (note the LCD misreads).
PM5_FULL = ["• concept 2.", "25:09", "37", "128", "Watt", "10799", "78", "12176", "PM5",
            "0", "wyatt", "split", "projected", "30:00", "Units", "Display", "Menu"]
PM5_SPARSE = ["O concept 2,", "20:16", "32", "wyatt", "138", "Walt", "PM5", "0"]
# Fan-bike console (AirDyne): no watts/split vocabulary at all.
AIRDYNE = ["20/10", "INTERVAL", "30/90", "INTERVAL", "CUSTOM", "INTERVAL", "TIME", "TARGET",
           "CAL/kJ", "TARGET", "MU/KM", "TARGET", "HEART RATE"]
# Glare shot: brand unreadable, only fragments survive.
GLARE = ["20:16", "138", "W30t"]

NUTRITION = ["Nutrition Facts", "Serving size 1 cup", "Calories 250", "Total Fat 12g",
             "Sodium 470mg", "Total Carbohydrate 31g"]
RECEIPT = ["Subtotal 42.10", "Sales tax 2.53", "Total 44.63", "VISA", "10:42"]
CHAT = ["What time works?", "Wait for me", "want to grab lunch", "12:30"]


def test_console_photos_match():
    for lines in (PM5_FULL, PM5_SPARSE, AIRDYNE):
        score, hits = fmp.score_text(lines)
        assert score >= fmp.DEFAULTS["min_score"], (lines, hits)


@pytest.mark.parametrize("lines", [NUTRITION, RECEIPT, CHAT, []])
def test_everyday_text_does_not_match(lines):
    score, hits = fmp.score_text(lines)
    assert score < fmp.DEFAULTS["min_score"], hits


def test_workspace_extra_brand_counts():
    cfg = {**fmp.DEFAULTS, "extra_brands": ["Keiser"]}
    assert "extra:Keiser" in fmp.score_text(["KEISER M3i", "12:04"], cfg)[1]


END = datetime(2026, 8, 8, 20, 41, 0, tzinfo=timezone.utc)


def test_timing_bonus_rescues_glare_shot_after_workout():
    just_after = END.replace(minute=44)
    assert fmp.score_text(GLARE)[0] < fmp.DEFAULTS["min_score"]
    score, hits = fmp.score_photo(GLARE, just_after, [END])
    assert score >= fmp.DEFAULTS["min_score"] and "near_workout_end" in hits


def test_timing_alone_is_not_enough():
    # a post-workout selfie has no console text
    assert fmp.score_photo([], END.replace(minute=43), [END])[0] < fmp.DEFAULTS["min_score"]


def test_near_workout_end_window():
    ends = [END]
    assert fmp.near_workout_end(END.replace(minute=39), ends)       # 2 min before end
    assert fmp.near_workout_end(END.replace(minute=51), ends)       # 10 min after
    assert not fmp.near_workout_end(END.replace(minute=52), ends)   # too late
    assert not fmp.near_workout_end(END.replace(minute=30), ends)   # mid-workout


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(fmp, "INBOX_DIR", tmp_path / "inbox")
    monkeypatch.setattr(fmp, "PHOTOS_DIR", tmp_path / "raw")
    monkeypatch.setattr(fmp, "STATE_PATH", tmp_path / "state.json")
    (tmp_path / "inbox").mkdir()
    (tmp_path / "raw").mkdir()
    return tmp_path


def test_known_uuids_reads_photos_style_names(ws):
    (ws / "raw" / "020BACC7-FDBE-4A24-9845-F1C65B089BCE_1_102_a.jpeg").write_bytes(b"x")
    (ws / "inbox" / "aaaa-bbbb.heic").write_bytes(b"x")
    seen = fmp.known_uuids(fmp.load_state())
    assert {"020BACC7-FDBE-4A24-9845-F1C65B089BCE", "AAAA-BBBB"} <= seen


def test_promote_and_reject(ws):
    (ws / "inbox" / "AAAA.heic").write_bytes(b"monitor")
    (ws / "inbox" / "BBBB.jpeg").write_bytes(b"receipt")
    fmp.promote(["aaaa"])
    fmp.reject(["BBBB"])
    assert (ws / "raw" / "AAAA.heic").exists()
    assert not any((ws / "inbox").iterdir())
    state = fmp.load_state()
    assert state["promoted"] == ["AAAA"] and state["rejected"] == ["BBBB"]
    assert {"AAAA", "BBBB"} <= fmp.known_uuids(state)   # never staged again


def test_promote_unknown_uuid_exits(ws):
    with pytest.raises(SystemExit):
        fmp.promote(["NOPE"])


@requires_workspace
@pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision OCR is macOS-only")
def test_real_monitor_photos_score_as_matches():
    pytest.importorskip("osxphotos")
    from osxphotos.text_detection import detect_text
    photos = sorted((WORKSPACE / "data" / "raw" / "photos").iterdir())
    for photo in photos:
        lines = [t for t, c in detect_text(str(photo)) if c >= fmp.DEFAULTS["ocr_confidence"]]
        score, hits = fmp.score_text(lines)
        assert score >= fmp.DEFAULTS["min_score"], (photo.name, hits)


# ---------------------------------------------------------------- read-only guarantees

def test_guard_allows_only_finder_paths(ws):
    assert fmp._guard_write(ws / "inbox" / "A.heic")
    assert fmp._guard_write(ws / "raw" / "A.heic")
    assert fmp._guard_write(ws / "state.json")
    for bad in (ws / "elsewhere.jpeg", ws / "inbox" / "sub" / "A.heic", ws.parent / "A.heic"):
        with pytest.raises(fmp.UnsafeWrite):
            fmp._guard_write(bad)


def test_guard_refuses_photos_library(ws, monkeypatch):
    lib = ws / "Photos Library.photoslibrary" / "originals"
    lib.mkdir(parents=True)
    monkeypatch.setattr(fmp, "INBOX_DIR", lib)   # even if misconfigured to point there
    with pytest.raises(fmp.UnsafeWrite, match="Photos library"):
        fmp._guard_write(lib / "A.heic")


def test_guard_refuses_hard_links_and_symlinks(ws, tmp_path):
    original = tmp_path / "library-original.heic"
    original.write_bytes(b"original")
    import os
    os.link(original, ws / "inbox" / "LINKED.heic")
    with pytest.raises(fmp.UnsafeWrite, match="hard-linked"):
        fmp._guard_write(ws / "inbox" / "LINKED.heic")
    (ws / "inbox" / "SYM.heic").symlink_to(original)
    with pytest.raises(fmp.UnsafeWrite):
        fmp._guard_write(ws / "inbox" / "SYM.heic")
    # reject must not delete through a link either; the original survives
    with pytest.raises(fmp.UnsafeWrite):
        fmp.reject(["LINKED"])
    assert original.read_bytes() == b"original"


class FakePhoto:
    uuid, original_filename, path = "AAAA", "IMG_1.HEIC", "/lib/originals/A/AAAA.heic"

    def __init__(self, write_to=None):
        self.calls, self.write_to = [], write_to

    def export(self, dest, **kw):
        self.calls.append(kw)
        out = Path(self.write_to or Path(dest) / kw["filename"])
        out.write_bytes(b"copy")
        return [str(out)]


def test_export_is_an_independent_copy(ws):
    photo = FakePhoto()
    path = fmp.export_original(photo, fmp.INBOX_DIR, download=False)
    assert path.parent == (ws / "inbox").resolve()
    [kw] = photo.calls
    assert kw["export_as_hardlink"] is False and kw["edited"] is False
    assert path.stat().st_nlink == 1


def test_export_landing_outside_inbox_is_refused(ws):
    photo = FakePhoto(write_to=ws / "surprise.heic")
    with pytest.raises(fmp.UnsafeWrite):
        fmp.export_original(photo, fmp.INBOX_DIR, download=False)


def test_promote_never_overwrites_raw(ws):
    (ws / "raw" / "AAAA.heic").write_bytes(b"raw")
    (ws / "inbox" / "AAAA.heic").write_bytes(b"new")
    with pytest.raises(SystemExit):
        fmp.promote(["AAAA"])
    assert (ws / "raw" / "AAAA.heic").read_bytes() == b"raw"


# Pin the Apple Photos surface: only these read-only osxphotos members may be
# used. Adding anything here is a deliberate, reviewed change.
ALLOWED_PHOTO_ATTRS = {"uuid", "date", "path", "path_derivatives", "original_filename",
                       "intrash", "export"}
ALLOWED_DB_ATTRS = {"photos", "albums"}
ALLOWED_OSXPHOTOS = {"PhotosDB", "text_detection", "detect_text"}


def test_only_read_only_photos_api_is_used():
    import ast
    tree = ast.parse(Path(fmp.__file__).read_text())
    photo_attrs, db_attrs, osx_attrs, imports = set(), set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            owner = node.value.id
            if owner in {"photo", "p"} and node.attr not in {"name", "parent", "stem", "suffix"}:
                photo_attrs.add(node.attr)
            elif owner == "db":
                db_attrs.add(node.attr)
            elif owner == "osxphotos":
                osx_attrs.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            imports |= {mod} | {a.name for a in node.names}
    assert photo_attrs <= ALLOWED_PHOTO_ATTRS, photo_attrs - ALLOWED_PHOTO_ATTRS
    assert db_attrs <= ALLOWED_DB_ATTRS, db_attrs - ALLOWED_DB_ATTRS
    assert osx_attrs <= ALLOWED_OSXPHOTOS, osx_attrs - ALLOWED_OSXPHOTOS
    # photoscript / PhotoKit are osxphotos' write paths into the library
    assert not any("photoscript" in i or "photokit" in i.lower() for i in imports), imports
