import html
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

import yaml

import build_dashboard as bd
import build_index
import ingest
from conftest import TEMPLATE_WORKSPACE, WORKSPACE, requires_workspace
from lib import facts as facts_lib
from lib import frontmatter

SECTIONS = ["Efficiency factor — BikeErg", "Avg watts per ride — BikeErg",
            "Weekly minutes in zone", "Baseline activity", "VO&#8322;max in context",
            "Benchmarks", "Recent sessions"]
# Phrases that once described one athlete inside engine code; none may return.
ATHLETE_LITERALS = ["field test 08-11", "conservative floor", "re-test pending",
                    "leg-limited", "known low", "your true value", "power floor",
                    "Apple Watch", "casual walkers", "quad-independent", "tends optimistic"]
# a unit with no value in front of it: "— W", "None bpm"
ORPHAN_UNIT = re.compile(r"(?:—|None|>)\s*<span style='font-size:14px'>")


def _blank(tmp_path):
    root = tmp_path / "blank"
    shutil.copytree(TEMPLATE_WORKSPACE, root)
    return root


def _copy(pipeline, tmp_path, name="ws"):
    root = tmp_path / name
    shutil.copytree(pipeline.ws, root)
    return root


def _card(page, title):
    start = page.index(f"<h2>{title}</h2>")
    end = page.find('<div class="card', start)
    return page[start:end if end != -1 else page.index('<p class="foot">', start)]


def _tips(fragment):
    """The data-tip texts in a page fragment, unescaped, in document order."""
    return [html.unescape(t) for t in re.findall(r'data-tip="([^"]*)"', fragment)]


def _set_config(root, **blocks):
    path = root / "config" / "athlete.yaml"
    config = yaml.safe_load(path.read_text())
    config.update(blocks)
    path.write_text(yaml.safe_dump(config, sort_keys=False))


def _set_athlete(root, **values):
    path = root / "config" / "athlete.yaml"
    config = yaml.safe_load(path.read_text())
    config["athlete"].update(values)
    path.write_text(yaml.safe_dump(config, sort_keys=False))


# ---------------------------------------------------------------- engine hygiene

def test_dashboard_in_ingest_pipeline():
    assert ingest.STEPS[-1] == "build_dashboard.py"


def test_no_athlete_literals_in_engine_code():
    source = Path(bd.__file__).read_text(encoding="utf-8")
    for phrase in ATHLETE_LITERALS:
        assert phrase.lower() not in source.lower(), phrase


def test_build_resolves_paths_at_call_time(pipeline, tmp_path):
    # no module-level workspace paths: the root passed in is the only one read
    assert not hasattr(bd, "REPO_ROOT") and not hasattr(bd, "OUT_PATH")
    assert "data through 2030-05-20" in bd.build(pipeline.ws)
    assert "no sessions yet" in bd.build(_blank(tmp_path))


# ---------------------------------------------------------------- blank workspace

def test_blank_workspace_renders_empty_states(tmp_path):
    page = bd.build(_blank(tmp_path))
    assert page.startswith("<!doctype html>") and page.rstrip().endswith("</script>")
    assert "None" not in page
    assert not ORPHAN_UNIT.search(page)
    assert "no sessions yet" in page and "no benchmarks yet" in page
    assert "no baseline activity yet" in page
    # no empty charts: only the VO2max card (literature points) draws one
    assert "no data yet" not in page and page.count("<svg") == 1
    for absent in ["Efficiency factor", "Weekly minutes in zone", "per session",
                   'class="tiles"', 'class="legend"', "data through", "anchors:"]:
        assert absent not in page, absent
    for section in ["Baseline activity", "VO&#8322;max in context", "Benchmarks",
                    "Recent sessions"]:
        assert f"<h2>{section}</h2>" in page
    for phrase in ATHLETE_LITERALS:
        assert phrase not in page


# ---------------------------------------------------------------- synthetic workspace

def test_synthetic_workspace_sections_and_provenance(pipeline):
    page = bd.build(pipeline.ws)
    for section in SECTIONS:
        assert f"<h2>{section}</h2>" in page, section
    assert "None" not in page and not ORPHAN_UNIT.search(page)
    for phrase in ATHLETE_LITERALS:
        assert phrase not in page, phrase
    # data through = facts as_of (newest date in the data), never the clock
    assert facts_lib.collect(facts_lib.load(pipeline.ws))["as_of"] == "2030-05-20"
    assert "data through 2030-05-20" in page
    assert "anchors: LTHR 160, FTP 200 W</p>" in page
    # both anchor tiles cite the newest LTHR/FTP benchmark heading
    assert page.count('<div class="n">benchmark 2030-05-01</div>') == 2
    assert "136–143" in page and "≤150 W on the BikeErg" in page
    assert "<td>LTHR/FTP field test (BikeErg)</td>" in page


def test_vo2max_estimates_carry_only_method_caveats(pipeline):
    card = _card(bd.build(pipeline.ws), "VO&#8322;max in context")
    caveats = yaml.safe_load(bd.REFERENCE_VALUES.read_text())["method_caveats"]
    for label, method in [("You — power estimate", "power_estimate"),
                          ("You — watch estimate", "watch_estimate"),
                          ("You — HR-ratio estimate", "hr_ratio_estimate")]:
        assert f">{label}</text>" in card
        assert html.escape(caveats[method]) in card, method
    assert "Average, female 40-49" in card


def test_decoupling_and_hr_drift_cards_from_pipeline(pipeline):
    page = bd.build(pipeline.ws)
    pw = _card(page, "Aerobic decoupling per session")
    drift = _card(page, "HR drift per session")
    # the C2-backed ride is the only pw_hr point; HR-drift values stay out of it
    assert len(_tips(pw)) == 1 and "% decoupling" in _tips(pw)[0]
    assert "2030-05-13" in pw and ">5%<" in pw
    assert "HR drift" not in pw.split("</div>", 1)[1]
    assert len(_tips(drift)) == 4 and all("% HR drift" in t for t in _tips(drift))
    assert "decoupling\n" not in drift
    assert ">5%<" not in drift


def test_anchors_note_verbatim_and_null_anchor_tiles_hidden(pipeline, tmp_path):
    root = _copy(pipeline, tmp_path)
    _set_athlete(root, anchors_note="floor - re-test <pending>", lthr=None)
    page = bd.build(root)
    assert "anchors: FTP 200 W (floor - re-test &lt;pending&gt;)</p>" in page
    assert '<div class="k">LTHR</div>' not in page
    assert '<div class="k">Zone 2</div>' not in page  # bootstrap zones: no LTHR band
    assert '<div class="k">FTP (BikeErg)</div>' in page
    assert "bootstrap zones from HRmax 192" in page


def test_anchor_benchmark_selection():
    text = """### 2030-01-02 — 2k row (RowErg)
### 2030-02-01 - lthr retest (BikeErg)
### 2030-01-15 — FTP test (BikeErg)
```
### 2031-01-01 — LTHR in a fenced example
```
"""
    assert bd.anchor_benchmark(text) == {"date": "2030-02-01", "title": "lthr retest (BikeErg)"}
    assert bd.anchor_benchmark("### 2030-01-02 — 2k row (RowErg)\n") is None
    assert bd.anchor_benchmark(None) is None


def test_no_anchor_benchmark_leaves_tile_note_empty(pipeline, tmp_path):
    root = _copy(pipeline, tmp_path)
    bench = root / "benchmarks.md"
    bench.write_text(bench.read_text().replace("LTHR/FTP field test", "Max HR probe"))
    page = bd.build(root)
    assert "benchmark 2030-05-01" not in page
    assert '<div class="k">LTHR</div><div class="v">160' in page


def test_benchmark_rows_use_the_facts_heading_rule():
    text = """## Results
### 2030-01-02 — 2k row (RowErg)
- Result: **7:40.0**, 190 W
### 2030-02-01 - LTHR retest (BikeErg)
- Conditions/notes: result line further down
- Result: LTHR 162 bpm
### 2030-02-30 – impossible date
### 2030-03-01 – FTP test (BikeErg)
- Conditions/notes: no result recorded
## Notes
- Result: not under a dated heading
```
### 2031-01-01 — fenced example
- Result: ...
```
"""
    rows = bd.benchmark_rows(text)
    assert [r["date"] for r in rows] == [b["date"] for b in facts_lib.parse_benchmarks(text)]
    assert rows == [
        {"date": "2030-01-02", "test": "2k row (RowErg)", "result": "7:40.0, 190 W"},
        {"date": "2030-02-01", "test": "LTHR retest (BikeErg)", "result": "LTHR 162 bpm"},
        {"date": "2030-03-01", "test": "FTP test (BikeErg)", "result": ""}]
    assert bd.benchmark_rows(None) == []


def test_benchmark_table_never_contradicts_anchor_provenance(pipeline, tmp_path):
    # a hyphen heading counts for the anchor tiles, so it counts for the table
    root = _copy(pipeline, tmp_path)
    bench = root / "benchmarks.md"
    bench.write_text(bench.read_text().replace(
        "### 2030-05-01 — LTHR/FTP field test", "### 2030-05-01 - LTHR/FTP field test"))
    page = bd.build(root)
    assert page.count('<div class="n">benchmark 2030-05-01</div>') == 2
    card = _card(page, "Benchmarks")
    assert "no benchmarks yet" not in card and "<td>2030-05-01</td>" in card
    # a dated heading without a Result line still gets a row, with a dash
    bench.write_text(bench.read_text().replace(
        "- Result: LTHR 160 bpm, FTP 200 W (20-min avg 211 W)\n", ""))
    card = _card(bd.build(root), "Benchmarks")
    assert "<td>2030-05-01</td>" in card and "<td>—</td>" in card


def test_output_is_deterministic(pipeline, tmp_path):
    a = bd.build(pipeline.ws)
    assert a == bd.build(pipeline.ws)
    # same inputs at another path, with fresh mtimes: same bytes
    assert a == bd.build(_copy(pipeline, tmp_path, "elsewhere"))
    assert a == (pipeline.ws / "dashboard.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------- render rules on synthetic rows

def _row(date, pct, method, modality="bikeerg"):
    return {"id": f"{date}-{modality}", "date": date, "modality": modality,
            "duration_s": 2400, "hr_avg": 135, "hr_max": 150, "watts_avg": 180,
            "efficiency_factor": 1.33, "compliance_score": None, "tier": 1,
            "decoupling_pct": pct, "decoupling_method": method,
            "decoupling_note": None if pct is not None else "window_too_short",
            "file": f"data/sessions/{date}.md"}


def _render(monkeypatch, tmp_path, index, metrics=(), baseline=()):
    config = {"athlete": {"lthr": 160}, "zones": {"bands": {
        "z1": [0.00, 0.85], "z2": [0.85, 0.89], "z3": [0.90, 0.94],
        "z4": [0.95, 0.99], "z5": [1.00, 9.99]}}}
    data = {"config": config, "index": index, "baseline": list(baseline),
            "metrics": list(metrics),
            "benchmarks_md": None, "goals_md": None, "plans": [], "reports": [],
            "workout_ends": [], "photo_finder": None, "proposals": None, "photos_inbox": 0}
    monkeypatch.setattr(bd.facts_lib, "load", lambda root: data)
    return bd.build(tmp_path)


def test_decoupling_and_hr_drift_never_share_a_chart(monkeypatch, tmp_path):
    page = _render(monkeypatch, tmp_path, [_row("2026-08-01", 3.0, "pw_hr"),
                                           _row("2026-08-02", 7.5, "hr_drift"),
                                           _row("2026-08-03", None, None)])
    pw = _card(page, "Aerobic decoupling per session")
    drift = _card(page, "HR drift per session")
    assert "3.0% decoupling" in pw and "7.5%" not in pw and ">5%<" in pw
    assert "7.5% HR drift" in drift and "3.0%" not in drift and ">5%<" not in drift
    # the table says which kind each number is
    assert "<td>3.0</td>" in page and "<td>7.5 (HR)</td>" in page


def test_hr_drift_only_and_zone2_tile(monkeypatch, tmp_path):
    page = _render(monkeypatch, tmp_path, [_row("2026-08-02", 7.5, "hr_drift")])
    assert "Aerobic decoupling per session" not in page
    assert ">5%<" not in _card(page, "HR drift per session")
    # Zone 2 tile uses the resolved, contiguous band: [136, 144) bpm at LTHR 160
    assert "136–143" in page
    assert "data through 2026-08-02" in page


def test_week_tiles_name_their_window(monkeypatch, tmp_path):
    # health metrics a week past the last workout move "data through", not
    # the training window: daily metrics usually run ahead of workout exports.
    # Baseline this week is the as-of week (the Baseline chart's last bar),
    # and says so.
    index = [_row("2026-08-01", 3.0, "pw_hr"), _row("2026-08-05", 3.0, "pw_hr")]
    metrics = [{"date": "2026-08-12", "name": "resting_heart_rate", "value": 50.0,
                "units": "count/min"}]
    baseline = [{"week": "2026-W32", "minutes": 10, "count": 1},
                {"week": "2026-W33", "minutes": 90, "count": 4}]
    page = _render(monkeypatch, tmp_path, index, metrics, baseline)
    assert "data through 2026-08-12" in page and "plan for 2026-W33: none" in page
    assert '<div class="k">Training, last 7 days</div><div class="v">80' in page
    assert "2 structured sessions, 7 days to 2026-08-05" in page
    assert '<div class="k">Baseline this week</div><div class="v">90' in page
    assert '<div class="n">4 activities, week 2026-W33</div>' in page
    assert _tips(_card(page, "Baseline activity"))[-1].startswith("2026-W33  90 min")
    page = _render(monkeypatch, tmp_path, index, metrics, baseline[:1])
    assert '<div class="k">Baseline this week</div><div class="v">0' in page
    assert '<div class="n">no baseline activity in week 2026-W33</div>' in page


# ---------------------------------------------------------------- real workspace (read-only)

@requires_workspace
def test_dashboard_renders_workspace_state():
    html_out = bd.build(WORKSPACE)  # renders to a string; writes nothing
    for section in ["Efficiency factor", "Weekly minutes in zone",
                    "Baseline activity", "Benchmarks",
                    "Recent sessions", "prefers-color-scheme", "data-tip"]:
        assert section in html_out
    # titled by method: HR drift unless some session has a power trace
    assert "Aerobic decoupling per session" in html_out or "HR drift per session" in html_out
    assert "None" not in html_out
    # self-contained: no external requests of any kind
    for banned in ["http://", "https://", "src=", "@import"]:
        assert banned not in html_out, banned


@requires_workspace
def test_workspace_sessions_satisfy_schema():
    problems = []
    for path in sorted((WORKSPACE / "data" / "sessions").rglob("*.md")):
        fm, _ = frontmatter.load(path)
        problems += build_index.validate(fm, path)
    assert problems == []


# ---------------------------------------------------------------- status band

# Advice and verdict words (tests/test_status.py's list): the band states facts.
BANNED = ["should", "must", "need", "recommend", "try", "good", "bad", "great", "poor",
          "too", "overdue", "behind", "lazy", "warning"]


def _band(page):
    section = page[page.index('<section class="status"'):page.index("</section>")]
    return [html.unescape(t) for t in re.findall(r"<li>(.*?)</li>", section)]


def _assert_no_verdicts(lines):
    for line in lines:
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", line, re.IGNORECASE), (word, line)


def test_status_band_restates_the_facts(pipeline):
    page = bd.build(pipeline.ws)
    facts = facts_lib.collect(facts_lib.load(pipeline.ws))
    band = _band(page)
    assert band == [
        "data through 2030-05-20",
        "last structured session: 2030-05-20, rowerg, 0 days before the as-of date",
        "weeks with at least 3 structured sessions: 1 of 3, current streak 0",
        "newest benchmark: 2030-05-01 (19 days; configured cadence 42 days)",
        "goal: general-cv-health",
        "plan for 2030-W21: none"]
    # every number and date in the band is the facts' own value
    c, b = facts["consistency"], facts["benchmarks"]
    assert band[0].endswith(facts["as_of"])
    assert facts["sessions"]["last_structured"] == {"date": "2030-05-20", "modality": "rowerg"}
    assert facts["sessions"]["days_since_last_structured"] == 0
    assert (c["threshold_sessions"], c["weeks_meeting"], c["weeks_total"],
            c["current_streak_weeks"]) == (3, 1, 3, 0)
    assert (b["latest"]["date"], b["age_days"], b["cadence_days"]) == ("2030-05-01", 19, 42)
    assert facts["goal"]["track"] == "general-cv-health"
    assert facts["plan"] == {"current_week": "2030-W21", "exists": False, "latest": None}
    # sits above the tiles
    assert page.index('<section class="status"') < page.index('class="tiles"')
    _assert_no_verdicts(band)


def test_status_band_follows_files_and_config(pipeline, tmp_path):
    root = _copy(pipeline, tmp_path)
    (root / "plans").mkdir(exist_ok=True)
    (root / "plans" / "2030-W21.md").write_text("---\nweek: 2030-W21\n---\n")
    _set_config(root, status={"consistency_sessions": 1, "benchmark_cadence_days": 28})
    goals = root / "goals.md"
    goals.write_text(goals.read_text().replace("- Track: general-cv-health\n", ""))
    band = _band(bd.build(root))
    assert "plan for 2030-W21: present" in band
    assert "weeks with at least 1 structured session: 3 of 3, current streak 3" in band
    assert "newest benchmark: 2030-05-01 (19 days; configured cadence 28 days)" in band
    assert "goal: none set" in band
    _assert_no_verdicts(band)


def test_status_band_blank_workspace(tmp_path):
    band = _band(bd.build(_blank(tmp_path)))
    assert band == ["no dated data yet", "last structured session: none",
                    "no benchmarks yet", "goal: none set", "plan: none"]
    _assert_no_verdicts(band)


# ---------------------------------------------------------------- training vs baseline

def test_walks_count_in_baseline_not_training(pipeline):
    page = bd.build(pipeline.ws)
    # last 7 days to 2030-05-20: rowerg 15 + rowerg 35 min; the 40-min walk
    # on 05-18 is unstructured and stays out
    assert '<div class="k">Training, last 7 days</div><div class="v">50' in page
    assert "2 structured sessions, 7 days to 2030-05-20" in page
    zones = _card(page, "Weekly minutes in zone")
    assert "structured sessions only; walk, treadmill-walk minutes are in Baseline" in zones
    # W20 zone minutes are the structured sessions' own time-in-zone only
    expected = {k: 0.0 for k in ["z1", "z2", "z3", "z4", "z5"]}
    for path in sorted((pipeline.ws / "data" / "sessions").rglob("*.md")):
        fm, _ = frontmatter.load(path)
        if fm["modality"] != "walk" and bd.iso_week(str(fm["date"])) == "2030-W20":
            for k, v in fm["computed"]["time_in_zone"].items():
                expected[k] += v / 60
    w20 = next(t for t in _tips(zones) if t.startswith("2030-W20"))
    assert w20 == "2030-W20  " + "  ".join(
        f"{k} {round(v)}m" for k, v in expected.items() if v >= 1)
    # the walk is in Baseline: W20 = no rollup minutes + the 40-min logged walk
    base = _card(page, "Baseline activity")
    assert "2030-W20  40 min\nrollup 0 min, logged 40 min" in _tips(base)
    assert "2030-W19  25 min\nrollup 25 min, logged 0 min" in _tips(base)
    # Baseline this week (W21): the 20-min rollup walk on 05-21
    assert '<div class="k">Baseline this week</div><div class="v">20' in page


def _session_file(root, row, tiz):
    path = root / row["file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.safe_dump({"id": row["id"], "computed": {"time_in_zone": tiz}})
                    + "---\n")


def _weeks(card):
    return re.findall(r'data-week="([^"]+)"', card)


def test_baseline_weeks_reach_back_before_the_first_session(monkeypatch, tmp_path):
    # a first import: months of walks in the health export, no or one session
    baseline = [{"week": f"2026-W{n}", "minutes": 60, "count": 3} for n in range(20, 40)]
    metrics = [{"date": "2026-09-29", "name": "resting_heart_rate", "value": 50.0}]
    expected = [f"2026-W{n}" for n in range(20, 41)]  # through the as-of week, W40
    for index in ([], [_row("2026-09-28", 3.0, "pw_hr")]):
        card = _card(_render(monkeypatch, tmp_path, index, metrics, baseline),
                     "Baseline activity")
        assert "no baseline activity" not in card
        assert _weeks(card) == expected
        tips = _tips(card)
        assert tips[0] == "2026-W20  60 min\nrollup 60 min, logged 0 min"
        assert tips[-1] == "2026-W40  0 min\nrollup 0 min, logged 0 min"
    # capped at the most recent MAX_WEEKS, still ending at the as-of week
    long = [{"week": "2025-W02", "minutes": 30, "count": 1}] + baseline
    card = _card(_render(monkeypatch, tmp_path, [], metrics, long), "Baseline activity")
    assert len(_weeks(card)) == bd.MAX_WEEKS and _weeks(card)[-1] == "2026-W40"
    # activity only before the weeks shown: said so, not "yet"
    card = _card(_render(monkeypatch, tmp_path, [], metrics, long[:1]), "Baseline activity")
    assert "no baseline activity in the 26 weeks to 2026-W40" in card


def test_zone_chart_says_when_all_zone_data_is_older(monkeypatch, tmp_path):
    index = [_row("2025-01-06", 3.0, "pw_hr")]
    _session_file(tmp_path, index[0], {"z2": 1800})
    metrics = [{"date": "2026-09-29", "name": "resting_heart_rate", "value": 50.0}]
    card = _card(_render(monkeypatch, tmp_path, index, metrics), "Weekly minutes in zone")
    assert "no zone minutes in the 26 weeks to 2026-W40" in card and "no data yet" not in card


def test_weekly_charts_include_zero_weeks(monkeypatch, tmp_path):
    index = [_row("2026-06-02", 3.0, "pw_hr"), _row("2026-07-21", 3.0, "pw_hr")]
    for row in index:
        _session_file(tmp_path, row, {"z1": 600, "z2": 1800})
    baseline = [{"week": "2026-W23", "minutes": 30, "count": 2},
                {"week": "2026-W30", "minutes": 15, "count": 1}]
    metrics = [{"date": "2026-08-04", "name": "resting_heart_rate", "value": 50.0}]
    page = _render(monkeypatch, tmp_path, index, metrics, baseline)
    weeks = [f"2026-W{n}" for n in range(23, 33)]  # W23..W32 (as_of 2026-08-04)
    for title in ["Weekly minutes in zone", "Baseline activity"]:
        card = _card(page, title)
        assert _weeks(card) == weeks, title
    zones = _tips(_card(page, "Weekly minutes in zone"))
    assert zones[1] == "2026-W24  no zone minutes" and zones[0] == "2026-W23  z1 10m  z2 30m"
    assert "2026-W26  0 min\nrollup 0 min, logged 0 min" in _tips(_card(page, "Baseline activity"))


# ---------------------------------------------------------------- date-true axes

def _xs(card, cls="hit"):
    return [float(x) for x in re.findall(rf'<circle class="{cls}" cx="([\d.]+)"', card)]


def test_per_session_charts_are_placed_by_date(monkeypatch, tmp_path):
    # three rides a day apart, a seven-week layoff, one ride, then health
    # data running to the as-of date
    dates = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-07-22"]
    index = [_row(d, 3.0, "pw_hr") for d in dates]
    metrics = [{"date": "2026-08-05", "name": "resting_heart_rate", "value": 50.0}]
    page = _render(monkeypatch, tmp_path, index, metrics)
    for title in ["Efficiency factor — BikeErg", "Avg watts per ride — BikeErg",
                  "Aerobic decoupling per session"]:
        card = _card(page, title)
        xs = _xs(card)
        assert xs == sorted(xs) and len(xs) == 4, title
        day = (xs[1] - xs[0])
        assert abs((xs[3] - xs[2]) / day - 49) < 0.5, title  # 49 days of empty space
        ticks = re.findall(r'<text class="xt" data-date="([^"]+)" x="([\d.]+)"', card)
        assert ticks[-1][0] == "2026-08-05"  # the axis runs to as_of ...
        assert abs(float(ticks[-1][1]) - (xs[0] + 65 * day)) < 1  # ... 65 days after the first ride
        tick_x = [float(x) for _, x in ticks]
        assert tick_x == sorted(tick_x) and min(b - a for a, b in zip(tick_x, tick_x[1:])) > 90
        # no line drawn through the layoff: the lone July ride is not joined
        lines = re.findall(r'<polyline points="([^"]+)"', card)
        assert len(lines) == 1 and len(lines[0].split()) == 3, title


def test_flat_and_negative_values_render(monkeypatch, tmp_path):
    # HR drift is negative whenever second-half HR is lower; one such point,
    # or several equal ones, must give a padded, non-inverted value axis
    for pcts in ([-1.5], [-1.5, -1.5], [0.0], [2.0, 2.0]):
        index = [_row(f"2026-08-0{i + 1}", p, "hr_drift") for i, p in enumerate(pcts)]
        card = _card(_render(monkeypatch, tmp_path, index), "HR drift per session")
        ys = [float(y) for y in re.findall(r'<circle class="hit" cx="[\d.]+" cy="([\d.]+)"', card)]
        assert len(ys) == len(pcts) and all(24 < y < 210 - 28 for y in ys), pcts
    ticks = bd._y_ticks(-1.35, -1.65)
    assert ticks == sorted(ticks) and all(-1.65 <= t <= -1.35 for t in ticks) and ticks
    assert bd._y_ticks(-1.65, -1.35) == ticks


def test_date_axis_ticks_never_collide():
    for span in [0, 1, 3, 6, 13, 30, 45, 90, 200, 400, 1000, 3000]:
        first = (date(2030, 1, 1) - timedelta(days=span)).isoformat()
        x, ticks = bd.date_axis(first, "2030-01-01", 48, 432)
        assert ticks[-1][0] == "2030-01-01" and ticks[-1][1] == 432
        assert 1 <= len(ticks) <= 4, span
        assert all(48 <= t[1] <= 432 for t in ticks)
        assert all(b[1] - a[1] > 90 for a, b in zip(ticks, ticks[1:])), span
        assert len({t[2] for t in ticks}) == len(ticks), span
        if span:
            assert x(first) == 48


# ---------------------------------------------------------------- recent sessions table

def test_sessions_table_drops_empty_columns_and_labels_sources(pipeline):
    card = _card(bd.build(pipeline.ws), "Recent sessions")
    headers = re.findall(r"<th>(.*?)</th>", card)
    # no compliance score anywhere in the fixture: that column is dropped
    assert headers == ["date", "modality", "dur", "HR", "watts", "EF", "dec %", "source"]
    assert "<td>Health + Photo + C2</td>" in card and "<td>Health + Photo</td>" in card
    assert "<td>Health</td>" in card
    # scrolls sideways inside its card with the date column pinned
    assert '<div class="scroll nowrap" role="region"' in card
    assert ".scroll th:first-child, .scroll td:first-child { position:sticky; left:0;" in bd.CSS


def test_sessions_table_without_power_or_decoupling(monkeypatch, tmp_path):
    rows = [{**_row("2026-08-0%d" % d, None, None, "rowerg"), "watts_avg": None,
             "efficiency_factor": None, "compliance_score": 0.9, "source_kinds": ["photo", "user"]}
            for d in (1, 2)]
    card = _card(_render(monkeypatch, tmp_path, rows), "Recent sessions")
    assert re.findall(r"<th>(.*?)</th>", card) == ["date", "modality", "dur", "HR",
                                                    "score", "source"]
    assert "<td>Photo + Manual</td>" in card and "dec % =" not in card
    assert bd.source_label(["health", "photo", "photo", "odd"]) == "Health + Photo + odd"
    assert bd.source_label([]) == "—"


# ---------------------------------------------------------------- recovery strip

def test_recovery_strip_is_opt_in(pipeline, tmp_path):
    assert "<h2>Recovery</h2>" not in bd.build(pipeline.ws)
    root = _copy(pipeline, tmp_path)
    for value in ["yes", 1, None]:
        _set_config(root, dashboard={"show_recovery": value})
        assert "<h2>Recovery</h2>" not in bd.build(root), value
    _set_config(root, dashboard={"show_recovery": True})
    page = bd.build(root)
    card = page[page.index("<h2>Recovery</h2>"):]
    card = card[:card.index("</table>")]
    rec = facts_lib.collect(facts_lib.load(root))["recovery"]
    rhr, hrv = rec["resting_hr"], rec["hrv"]
    assert rhr["latest"] and hrv["latest"]
    assert f"<td>{rhr['latest']['value']:g} ({rhr['latest']['date']})</td>" in card
    assert f"<td>{rhr['median_28d']:g} (n={rhr['n_28d']})</td>" in card
    assert f"<td>{hrv['median_7d']:g} (n={hrv['n_7d']})</td>" in card
    assert f"<td>{rhr['delta_vs_28d']:+.1f}</td>" in card
    assert f"<td>{rhr['days_elevated']}</td></tr>" in card
    _assert_no_verdicts(re.sub(r"<[^>]+>", " ", card).split("\n"))


def test_recovery_strip_without_data(tmp_path):
    root = _blank(tmp_path)
    _set_config(root, dashboard={"show_recovery": True})
    assert "no resting HR or HRV data yet" in bd.build(root)


# ---------------------------------------------------------------- phone and accessibility

def _tokens(block):
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def _luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted([_luminance(a), _luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_tokens_meet_wcag_aa_in_both_themes():
    css = bd.CSS
    light = _tokens(css[css.index(":root {"):css.index("}", css.index(":root {"))])
    media = css[css.index("@media (prefers-color-scheme: dark)"):]
    dark_media = _tokens(media[:media.index("} }")])
    explicit = css[css.index(':root[data-theme="dark"]'):]
    dark = _tokens(explicit[:explicit.index("}")])
    assert dark == dark_media  # the two dark blocks never drift apart
    for name, theme in [("light", light), ("dark", dark)]:
        for text in ["ink", "ink2", "muted"]:
            for bg in ["page", "surface"]:
                ratio = contrast(theme[text], theme[bg])
                assert ratio >= 4.5, (name, text, bg, round(ratio, 2))
        assert contrast(theme["page"], theme["ink"]) >= 4.5  # tooltip: page on ink


def test_tooltips_are_focusable_and_labelled(pipeline):
    page = bd.build(pipeline.ws)
    tags = re.findall(r"<[a-z]+ [^>]*data-tip=[^>]*>", page)
    assert len(tags) > 10
    for tag in tags:
        tip = re.search(r'data-tip="([^"]*)"', tag).group(1)
        assert 'tabindex="0"' in tag and f'aria-label="{tip}"' in tag, tag
    for event in ["'focus'", "'blur'", "'click'", "'mousemove'"]:
        assert event in bd.JS
    # focusing an off-screen point scrolls the page: that scroll must not hide
    # the focused point's tooltip, so scroll is not wired straight to hide
    assert "addEventListener('scroll',hide" not in bd.JS
    assert "cur===document.activeElement" in bd.JS


def test_document_and_charts_are_labelled(pipeline):
    page = bd.build(pipeline.ws)
    assert page.startswith('<!doctype html>\n<html lang="en">')
    assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in page
    assert "<title>Cardio Coach</title>" in page
    svgs = re.findall(r"<svg [^>]*>", page)
    assert len(svgs) == 7
    for tag in svgs:
        # group, not img: an img's children are presentational, which would hide
        # the focusable, labelled tooltip targets from assistive technology
        assert 'role="group"' in tag and re.search(r'aria-label="[^"]{20,}"', tag), tag
    assert 'role="img"' not in page
    assert 'aria-label="Efficiency factor per BikeErg ride: 2 sessions from 2030-05-08 to 2030-05-13, plotted by date through 2030-05-20"' in page


def test_phone_layout_rules():
    css = bd.CSS
    phone = css[css.index("@media (max-width:520px)"):]
    assert "body { padding:16px; }" in phone
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in phone
    size = int(re.search(r"svg text \{ font-size:(\d+)px", phone).group(1))
    # 375px viewport - 2 x 16px gutter - 2 x (12px padding + 1px border) = the
    # chart's width; text scales with the 470-unit viewBox
    assert size * (375 - 32 - 26) / 470 >= 11
    assert "grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in css  # no blow-out


def _svg_text_px(css, viewport):
    """Effective chart text size at a viewport width, from the CSS: the svg
    text size in force there times the chart's scale (its rendered width over
    the 470-unit viewBox). Layout figures are the CSS's own, asserted here."""
    for rule in ["padding:24px;", ".wrap { max-width:1060px;", "gap:16px; }",
                 "@media (max-width:820px){ .grid { grid-template-columns:minmax(0,1fr); } }",
                 "border-radius:10px; padding:16px;", "body { padding:16px; }",
                 ".card { padding:12px; }"]:
        assert rule in css, rule
    size = int(re.search(r"svg text \{ font:(\d+)px", css).group(1))
    for lo, hi, px in re.findall(
            r"@media (?:\(min-width:(\d+)px\) and )?\(max-width:(\d+)px\) \{[^@]*?"
            r"svg text \{ font-size:(\d+)px", css):
        if (not lo or viewport >= int(lo)) and viewport <= int(hi):
            size = int(px)
    phone = viewport <= 520
    gutter, card_pad = (16, 12) if phone else (24, 16)
    wrap = min(viewport - 2 * gutter, 1060)
    column = (wrap - 16) / 2 if viewport > 820 else wrap
    return size * (column - 2 * (card_pad + 1)) / 470


def test_chart_text_stays_legible_at_every_width():
    # phones portrait and landscape, tablets, small laptops
    for viewport in [375, 390, 430, 520, 521, 600, 768, 820, 821, 844, 932, 1024,
                     1079, 1080, 1280, 1440]:
        assert _svg_text_px(bd.CSS, viewport) >= 11, viewport


def test_fixture_page_is_self_contained_and_small(pipeline, tmp_path):
    root = _copy(pipeline, tmp_path)
    _set_config(root, dashboard={"show_recovery": True})
    for page in (bd.build(pipeline.ws), bd.build(root)):
        for banned in ["http://", "https://", "src=", "@import", "url("]:
            assert banned not in page, banned
        assert len(page.encode("utf-8")) < 150 * 1024
        assert "None" not in page
    assert bd.build(root) == bd.build(root)
