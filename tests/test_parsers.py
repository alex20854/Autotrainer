from conftest import FIXTURES

import parse_auto_export
import parse_c2
import parse_health_export


def test_health_export_parses_workouts(tmp_path):
    recs = parse_health_export.parse_export(FIXTURES / "export.xml", tmp_path)
    assert len(recs) == 5  # 4 cardio + 1 strength (filtering happens at proposal time)
    by_type = {r["workout_type"]: r for r in recs}
    w1 = by_type["HKWorkoutActivityTypeCycling"]
    assert w1["duration_s"] == 1830
    assert w1["kcal"] == 310
    assert w1["distance_m"] == 14200
    # HR clipped to the workout window: 7 in-window samples, not the 12:00 one
    assert len(w1["hr"]["series"]) == 7
    assert w1["hr"]["max"] == 136
    assert w1["hr"]["series"][0] == [60, 105]  # 06:01 is 60s after start
    # workouts without HR records still parse
    assert by_type["HKWorkoutActivityTypeRowing"]["hr"] is None


def test_health_export_idempotent(tmp_path):
    parse_health_export.parse_export(FIXTURES / "export.xml", tmp_path)
    first = sorted(p.name for p in tmp_path.glob("*.json"))
    parse_health_export.parse_export(FIXTURES / "export.xml", tmp_path)
    second = sorted(p.name for p in tmp_path.glob("*.json"))
    assert first == second and len(first) == 5


def test_auto_export_parses_workout(tmp_path):
    recs = parse_auto_export.parse_file(FIXTURES / "auto_export.json", tmp_path)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["workout_type"] == "Indoor Cycling"
    assert rec["duration_s"] == 2801  # 46.68 min
    assert rec["kcal"] == 410
    assert rec["distance_m"] == 21400
    assert rec["hr"]["series"][0] == [7, 98]  # 06:15:10 is 7s after start
    assert rec["hr"]["max"] == 138


def test_auto_export_duration_units_heuristic():
    # app versions disagree on the duration unit; the wall-clock span decides
    # (real bug: seconds read as minutes made 21-min walks look like 21 hours)
    start, end = "2026-07-13T10:38:20-04:00", "2026-07-13T10:59:10-04:00"  # 1250s
    assert parse_auto_export._duration_s(1248.4, start, end) == 1248.4   # seconds
    assert parse_auto_export._duration_s(20.8, start, end) == 20.8 * 60  # minutes
    assert parse_auto_export._duration_s(None, start, end) is None


def test_c2_summary_csv(tmp_path):
    recs = parse_c2.parse_file(FIXTURES / "c2_logbook.csv", tmp_path)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["workout_type"] == "c2-rowerg"
    assert rec["duration_s"] == 1800
    assert rec["distance_m"] == 6820
    assert rec["kcal"] == 390
    assert rec["hr"]["avg"] == 128
    assert rec["watts"] == [[0, 142.0]]
