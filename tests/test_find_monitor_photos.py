import sys
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
