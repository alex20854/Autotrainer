import build_baseline as bb
import ingest

CLASSIFICATION = {"baseline_types": ["Outdoor Walk", "Walking"],
                  "promote_min_duration_s": 1800}


def walk(rid, start, end, duration_s, kcal=100, distance_m=2000, hr_avg=95):
    return {"record_id": rid, "source_kind": rid.split("-")[0],
            "workout_type": "Outdoor Walk", "start": start, "end": end,
            "duration_s": duration_s, "kcal": kcal, "distance_m": distance_m,
            "hr": {"avg": hr_avg, "max": None, "series": []}}


def test_weekly_rollup_known_answer():
    # Mon + Wed walks in 2026-W32; the Mon walk is double-captured (dup collapses)
    mon_a = walk("health-m1", "2026-08-03T12:00:00-04:00",
                 "2026-08-03T12:20:00-04:00", 1200, kcal=90, distance_m=1800, hr_avg=90)
    mon_b = walk("health-m2", "2026-08-03T12:00:10-04:00",
                 "2026-08-03T12:20:30-04:00", 1220, kcal=92, distance_m=1810, hr_avg=91)
    wed = walk("health-w1", "2026-08-05T18:00:00-04:00",
               "2026-08-05T18:30:00-04:00", 1800, kcal=140, distance_m=2900, hr_avg=100)
    lines = bb.rollup([mon_a, mon_b, wed], set(), CLASSIFICATION)
    assert len(lines) == 1
    week = lines[0]
    assert week["week"] == "2026-W32"
    assert week["count"] == 2                      # duplicate collapsed
    assert week["minutes"] == 50                   # 20 + 30 (primary durations)
    assert week["by_type"] == {"Outdoor Walk": 2}
    # duration-weighted HR: (90*1200 + 100*1800) / 3000 = 96
    assert week["hr_avg"] == 96


def test_claimed_records_excluded_from_rollup():
    hike = walk("health-h1", "2026-08-05T12:00:00-04:00",
                "2026-08-05T12:50:00-04:00", 3000)
    claimed = {"data/derived/workouts/health-h1.json"}
    assert bb.rollup([hike], claimed, CLASSIFICATION) == []


def test_non_baseline_types_ignored():
    ride = dict(walk("health-r1", "2026-08-05T06:00:00-04:00",
                     "2026-08-05T06:30:00-04:00", 1800),
                workout_type="Indoor Cycling")
    assert bb.rollup([ride], set(), CLASSIFICATION) == []


def test_weeks_sorted_across_year_boundary():
    a = walk("health-y1", "2026-01-02T12:00:00-04:00",
             "2026-01-02T12:20:00-04:00", 1200)   # 2026-01-02 is ISO 2026-W01
    b = walk("health-y2", "2025-12-30T12:00:00-04:00",
             "2025-12-30T12:20:00-04:00", 1200)   # ISO 2026-W01 as well
    lines = bb.rollup([a, b], set(), CLASSIFICATION)
    assert [l["week"] for l in lines] == ["2026-W01"]
    assert lines[0]["count"] == 2


def test_ingest_pipeline_includes_baseline_step():
    assert "build_baseline.py" in ingest.STEPS
    assert ingest.STEPS.index("apply_merges.py") < ingest.STEPS.index("build_baseline.py")