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


def _ride(source_file, n_samples, kcal=250):
    return records.make_record(
        source_kind="health", source_file=source_file, workout_type="Indoor Cycling",
        start="2026-08-06T20:38:34-04:00", end="2026-08-06T21:08:39-04:00", kcal=kcal,
        hr={"avg": 130, "max": 150, "series": [[i * 5, 130] for i in range(n_samples)]},
    )


def _stored(tmp_path):
    [rec] = records.load_records(tmp_path)
    return rec


def test_upsert_older_export_never_downgrades(tmp_path):
    assert records.upsert_record(_ride("newer.json", 360), tmp_path)
    # an older/partial export of the same workout: fewer HR samples -> kept
    assert not records.upsert_record(_ride("older.json", 120), tmp_path)
    assert _stored(tmp_path)["source_file"] == "newer.json"


def test_upsert_tie_keeps_stored_capture(tmp_path):
    records.upsert_record(_ride("a.json", 360), tmp_path)
    assert not records.upsert_record(_ride("b.json", 360), tmp_path)
    assert _stored(tmp_path)["source_file"] == "a.json"


def test_upsert_strictly_richer_capture_replaces(tmp_path):
    records.upsert_record(_ride("partial.json", 120), tmp_path)
    assert records.upsert_record(_ride("full.json", 360), tmp_path)
    assert len(_stored(tmp_path)["hr"]["series"]) == 360


def test_upsert_same_file_reparse_always_applies(tmp_path):
    # a parser fix re-deriving from the same raw file must land even if "poorer"
    records.upsert_record(_ride("same.json", 360, kcal=250), tmp_path)
    assert records.upsert_record(_ride("same.json", 300, kcal=260), tmp_path)
    assert _stored(tmp_path)["kcal"] == 260
