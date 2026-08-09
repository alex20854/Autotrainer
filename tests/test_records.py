from lib import records


def test_record_id_is_deterministic():
    a = records.record_id("health", "2026-08-08T06:15:03-04:00", "HKWorkoutActivityTypeCycling")
    b = records.record_id("health", "2026-08-08T06:15:03-04:00", "HKWorkoutActivityTypeCycling")
    assert a == b == "health-2026-08-08T061503-cycling"


def test_parse_dt_formats():
    apple = records.parse_dt("2026-08-08 06:15:03 -0400")
    iso = records.parse_dt("2026-08-08T06:15:03-04:00")
    assert apple == iso
    naive = records.parse_dt("2026-08-06T06:42:00")
    assert naive.tzinfo is None


def test_make_record_derives_duration():
    rec = records.make_record(
        source_kind="health", source_file="x", workout_type="HKWorkoutActivityTypeRowing",
        start="2026-08-08T06:00:00-04:00", end="2026-08-08T06:30:00-04:00",
    )
    assert rec["duration_s"] == 1800


def test_save_and_load_round_trip(tmp_path):
    rec = records.make_record(
        source_kind="c2", source_file="x", workout_type="c2-rowerg",
        start="2026-08-08T06:00:00-04:00", end="2026-08-08T06:30:00-04:00",
        hr={"avg": 130, "max": 145, "series": [[0, 100], [60, 130]]},
    )
    records.save_record(rec, tmp_path)
    loaded = records.load_records(tmp_path)
    assert loaded == [rec]
