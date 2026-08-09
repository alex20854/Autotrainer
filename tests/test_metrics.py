import pytest

import compute_metrics as cm


def test_time_in_zone_known_answer():
    bands = {"z1": (0, 120), "z2": (120, 140), "z3": (140, 300)}
    # samples every 10s: 60s at 110, 60s at 130, 60s at 145, final sample 5s
    series = [[t, 110] for t in range(0, 60, 10)]
    series += [[t, 130] for t in range(60, 120, 10)]
    series += [[t, 145] for t in range(120, 180, 10)]
    tiz = cm.time_in_zone(series, bands)
    assert tiz == {"z1": 60, "z2": 60, "z3": 55}  # last sample counts 5s


def test_time_in_zone_caps_sparse_gaps():
    bands = {"z2": (120, 140)}
    series = [[0, 130], [600, 130]]  # 10-min gap must not credit 600s
    assert cm.time_in_zone(series, bands)["z2"] == 35  # 30 capped + 5 final


def test_efficiency_factor():
    assert cm.efficiency_factor(185, 132) == 1.4
    assert cm.efficiency_factor(None, 132) is None


def test_decoupling_hr_only():
    # constant-output session: HR 130 first half, 136.5 second -> 5.0% drift
    series = [[t, 130] for t in range(0, 1800, 60)]
    series += [[t, 136.5] for t in range(1800, 3600, 60)]
    assert cm.decoupling_pct(series, None, 3600) == 5.0


def test_decoupling_with_watts():
    hr = [[t, 130] for t in range(0, 1800, 60)] + [[t, 136.5] for t in range(1800, 3600, 60)]
    watts = [[t, 150] for t in range(0, 3600, 60)]
    # EF1 = 150/130, EF2 = 150/136.5 -> (EF1-EF2)/EF1 = 1 - 130/136.5 = 4.8%
    assert cm.decoupling_pct(hr, watts, 3600) == pytest.approx(4.8, abs=0.05)


def test_decoupling_needs_enough_samples():
    assert cm.decoupling_pct([[0, 130], [60, 131]], None, 120) is None


def test_detect_bouts_4x4():
    # 4 x 4min @ 250W with 3min @ 100W recoveries, 10s sampling
    series, t = [], 0
    for _ in range(4):
        series += [[t + i, 250] for i in range(0, 240, 10)]
        t += 240
        series += [[t + i, 100] for i in range(0, 180, 10)]
        t += 180
    bouts = cm.detect_bouts(series, threshold=200, min_bout_s=60)
    assert len(bouts) == 4
    assert all(b["avg"] == 250 for b in bouts)
    assert bouts[0]["start_s"] == 0 and bouts[1]["start_s"] == 420


def test_detect_bouts_ignores_short_spikes():
    series = [[t, 100] for t in range(0, 300, 10)]
    series[5] = [50, 300]  # single 10s spike
    assert cm.detect_bouts(series, threshold=200, min_bout_s=60) == []


def test_zone_bounds_sources():
    config = {"athlete": {"lthr": 160}, "zones": {"bands": {"z2": [0.85, 0.89]}}}
    bands, source = cm.zone_bounds(config)
    assert source == "lthr"
    assert bands["z2"] == (pytest.approx(136), pytest.approx(142.4))

    config = {"athlete": {"lthr": None, "hr_max": 180}, "zones": {"bands": {"z2": [0.85, 0.89]}}}
    _, source = cm.zone_bounds(config)
    assert source == "bootstrap"

    bands, source = cm.zone_bounds({"athlete": {}, "zones": {"bands": {}}})
    assert bands is None and source == "unconfigured"
