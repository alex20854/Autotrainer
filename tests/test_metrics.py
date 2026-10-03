import json
import math

import pytest

import compute_metrics as cm
from lib import frontmatter


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
    assert cm.decoupling_pct(series, None, (0, 3600)) == (5.0, "hr_drift")


def test_decoupling_with_watts():
    hr = [[t, 130] for t in range(0, 1800, 60)] + [[t, 136.5] for t in range(1800, 3600, 60)]
    watts = [[t, 150] for t in range(0, 3600, 60)]
    # EF1 = 150/130, EF2 = 150/136.5 -> (EF1-EF2)/EF1 = 1 - 130/136.5 = 4.8%
    pct, method = cm.decoupling_pct(hr, watts, (0, 3600))
    assert pct == pytest.approx(4.8, abs=0.05) and method == "pw_hr"


def test_decoupling_needs_enough_samples():
    assert cm.decoupling_pct([[0, 130], [60, 131]], None, (0, 120)) is None


SETTINGS = cm.metrics_settings({})


def _rising_then_flat(total_s, warmup_s=600, step=5):
    """HR climbs 100 -> 140 over the warm-up, then holds 140."""
    return [[t, 100 + 40 * t / warmup_s if t < warmup_s else 140]
            for t in range(0, total_s + 1, step)]


def test_decoupling_skips_warmup():
    series = _rising_then_flat(3600)
    # whole-session halves would read the warm-up climb as drift
    whole, _ = cm.decoupling_pct(series, None, (0, 3600))
    assert whole > 3
    out = cm.decoupling_fields(series, None, "bikeerg", SETTINGS)
    assert out["decoupling_pct"] == pytest.approx(0, abs=0.1)
    assert out["decoupling_method"] == "hr_drift"
    assert out["decoupling_window_s"] == 3000
    assert "decoupling_note" not in out


def test_decoupling_short_session_is_null_not_failure():
    out = cm.decoupling_fields(_rising_then_flat(1200), None, "bikeerg", SETTINGS)
    assert out == {"decoupling_pct": None, "decoupling_note": "window_too_short",
                   "decoupling_window_s": 600}


def test_decoupling_excluded_modality():
    out = cm.decoupling_fields(_rising_then_flat(3600), None, "walk", SETTINGS)
    assert out == {"decoupling_pct": None, "decoupling_note": "modality_excluded"}
    assert "mixed" not in SETTINGS["decoupling_modalities"]
    assert "rowerg" in SETTINGS["decoupling_modalities"]


def test_decoupling_settings_from_config():
    settings = cm.metrics_settings({"metrics": {"decoupling_min_window_s": 300,
                                                "decoupling_modalities": ["walk"]}})
    assert settings["decoupling_warmup_s"] == 600            # default kept
    out = cm.decoupling_fields(_rising_then_flat(1200), None, "walk", settings)
    assert out["decoupling_pct"] == pytest.approx(0, abs=0.1)


def test_decoupling_window_reaches_session_end():
    # 30:07 ride, Watch HR every 5 s, last sample at 29:59: a 30-minute ride
    hr = [[t, 140] for t in range(4, 1800, 5)]
    out = cm.decoupling_fields(hr, None, "bikeerg", SETTINGS, duration_s=1807)
    assert out["decoupling_window_s"] == 1207 and out["decoupling_pct"] == 0.0
    out = cm.decoupling_fields([[t, 140] for t in range(0, 1800, 5)], None, "bikeerg",
                               SETTINGS, duration_s=1800)
    assert out["decoupling_window_s"] == 1200 and out["decoupling_pct"] == 0.0
    # no duration known: the last HR sample is the end
    assert cm.decoupling_fields(hr, None, "bikeerg", SETTINGS)["decoupling_note"] == \
        "window_too_short"
    # HR stops well before the session ends: the trace doesn't cover it
    out = cm.decoupling_fields(hr, None, "bikeerg", SETTINGS, duration_s=1900)
    assert out["decoupling_window_s"] == 1199 and out["decoupling_note"] == "window_too_short"


def _splits(*pieces):
    """End-stamped split watts, as parse_c2 writes them: [(seconds, watts)...]."""
    series, t = [], 0
    for secs, watts in pieces:
        t += secs
        series.append([t, watts])
    return series


def test_pw_hr_weights_end_stamped_splits():
    hr = [[t, 140] for t in range(0, 3596, 5)]
    # 10-min warm-up split at 100 W stamped at 600 s, then a constant 200 W
    watts = _splits((600, 100), *[(600, 200)] * 5)
    out = cm.decoupling_fields(hr, watts, "bikeerg", SETTINGS, duration_s=3600)
    assert out["decoupling_method"] == "pw_hr"
    assert out["decoupling_pct"] == pytest.approx(0, abs=0.1)
    # a split straddling the halfway point is shared by time, not by stamp
    pct, method = cm.decoupling_pct([[t, 140] for t in range(0, 1200, 5)],
                                    _splits((300, 100), (600, 200), (300, 200)), (0, 1200))
    # first half 300 s @100 + 300 s @200 = 150 W; second half 200 W
    assert method == "pw_hr" and pct == pytest.approx((1 - 200 / 150) * 100, abs=0.1)


def test_pw_hr_needs_watts_covering_both_halves():
    hr = [[t, 140] for t in range(0, 2400, 5)]
    # watts stop a third of the way into the second half
    watts = [[t, 200] for t in range(0, 1800, 5)]
    pct, method = cm.decoupling_pct(hr, watts, (600, 2400))
    assert method == "hr_drift" and pct == 0.0


def _four_by_four(step):
    """10-min warm-up @110 W, 4 x (4 min @280 W, 3 min @110 W), easy to 40 min."""
    pieces = [(600, 110)] + [(240, 280), (180, 110)] * 4 + [(120, 110)]
    if step is None:                                  # one C2 split per piece
        return _splits(*pieces)
    series, t = [], 0
    for secs, watts in pieces:
        series += [[t + i, watts] for i in range(0, secs, step)]
        t += secs
    return series


@pytest.mark.parametrize("step", [5, None])
def test_intervals_are_not_steady(step):
    hr = [[t, 140] for t in range(0, 2400, 5)]
    out = cm.decoupling_fields(hr, _four_by_four(step), "bikeerg", SETTINGS, duration_s=2400)
    assert out == {"decoupling_pct": None, "decoupling_note": "not_steady",
                   "decoupling_window_s": 1800}


def test_steady_after_easy_warmup_is_steady():
    # the warm-up's lower power must not make the steady main set look like a bout
    hr = [[t, 140] for t in range(0, 1800, 5)]
    watts = _splits((600, 100), (600, 200), (600, 200))
    out = cm.decoupling_fields(hr, watts, "bikeerg", SETTINGS, duration_s=1800)
    assert out["decoupling_method"] == "pw_hr" and out["decoupling_pct"] == 0.0
    dense = [[t, 200 + (7 if t % 20 else -7)] for t in range(0, 1800, 2)]   # stroke noise
    assert not cm.has_work_bouts(dense, 600)


def test_compute_for_session_reports_method(tmp_path):
    hr = _rising_then_flat(3600)
    watts = [[t, 150] for t in range(0, 3601, 5)]
    rec_dir = tmp_path / "workouts"
    rec_dir.mkdir()
    (rec_dir / "c2-a.json").write_text(json.dumps({"hr": {"series": hr}, "watts": watts}))
    (rec_dir / "health-b.json").write_text(json.dumps({"hr": {"series": hr}, "watts": None}))
    config = {"athlete": {"lthr": 160}, "zones": {"bands": CONTIGUOUS}}
    paths = {}
    for name, ref, modality in [("pw", "c2-a", "bikeerg"), ("hr", "health-b", "bikeerg"),
                                ("walk", "health-b", "walk")]:
        paths[name] = tmp_path / f"{name}.md"
        frontmatter.save(paths[name], {
            "id": name, "modality": modality, "duration_s": 3600, "watts_avg": None,
            "hr_avg": 140, "sources": [{"kind": "health",
                                        "ref": f"data/derived/workouts/{ref}.json"}]})
    pw = cm.compute_for_session(paths["pw"], config, rec_dir)
    assert pw["decoupling_method"] == "pw_hr" and pw["decoupling_pct"] == pytest.approx(0, abs=0.1)
    assert cm.compute_for_session(paths["hr"], config, rec_dir)["decoupling_method"] == "hr_drift"
    walk = cm.compute_for_session(paths["walk"], config, rec_dir)
    assert walk["decoupling_pct"] is None and walk["decoupling_note"] == "modality_excluded"
    assert "decoupling_method" not in walk
    # time-in-zone accounts for the whole HR trace
    assert sum(walk["time_in_zone"].values()) == 3605


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


LEGACY = {"z1": [0.00, 0.85], "z2": [0.85, 0.89], "z3": [0.90, 0.94],
          "z4": [0.95, 0.99], "z5": [1.00, 9.99]}       # integer-percent table
CONTIGUOUS = {"z1": [0.00, 0.85], "z2": [0.85, 0.90], "z3": [0.90, 0.95],
              "z4": [0.95, 1.00], "z5": [1.00, 9.99]}


def test_zone_bounds_sources():
    config = {"athlete": {"lthr": 160}, "zones": {"bands": CONTIGUOUS}}
    bands, source = cm.zone_bounds(config)
    assert source == "lthr"
    assert bands["z2"] == (pytest.approx(136), pytest.approx(144))
    assert bands["z5"] == (pytest.approx(160), math.inf)        # top zone open-ended

    config = {"athlete": {"lthr": None, "hr_max": 180}, "zones": {"bands": LEGACY}}
    bands, source = cm.zone_bounds(config)
    assert source == "bootstrap"                                # anchor = 0.9 * 180 = 162
    assert bands["z2"] == (pytest.approx(137.7), pytest.approx(145.8))   # contiguous too

    bands, source = cm.zone_bounds({"athlete": {}, "zones": {"bands": {}}})
    assert bands is None and source == "unconfigured"


def test_integer_percent_gaps_are_closed(capsys):
    cm._warned.clear()
    bands, _ = cm.zone_bounds({"athlete": {"lthr": 160}, "zones": {"bands": LEGACY}})
    assert capsys.readouterr().err == ""                        # rounding gaps: silent
    for bpm in (143, 151, 159):     # fell in the 0.89-0.90 / 0.94-0.95 / 0.99-1.00 holes
        assert sum(lo <= bpm < hi for lo, hi in bands.values()) == 1, bpm
    # every sample is counted somewhere: zone totals = HR trace duration
    series = [[t, 100 + (t // 5) % 80] for t in range(0, 3600, 5)]
    series += [[3610, 150], [3700, 150]]                        # 10 s gap, then capped 90 s
    tiz = cm.time_in_zone(series, bands)
    expected = 3600 + 10 + 30 + 5
    assert abs(sum(tiz.values()) - expected) <= 1


def test_contiguous_bands_unchanged():
    resolved, problems = cm.resolve_bands(CONTIGUOUS)
    assert problems == []
    assert {z: lo_hi for z, lo_hi in resolved.items() if z != "z5"} == \
        {z: tuple(v) for z, v in CONTIGUOUS.items() if z != "z5"}
    assert cm.resolve_bands(LEGACY)[0] == resolved              # same zones either way


def test_overlap_and_wide_gap_warn_once(capsys):
    cm._warned.clear()
    bad = dict(CONTIGUOUS, z3=[0.88, 0.95], z5=[1.05, 9.99])    # z2/z3 overlap, z4-z5 gap
    config = {"athlete": {"lthr": 160}, "zones": {"bands": bad}}
    cm.zone_bounds(config)
    cm.zone_bounds(config)                                      # second session, same run
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1
    assert "z2 [0.85, 0.9] overlaps z3" in err[0] and "gap 1-1.05" in err[0]
