import html
import re
import shutil
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
    return page[start:page.index('<div class="card', start)]


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
    assert pw.count("% decoupling") == 1 and "05-13" in pw and ">5%<" in pw
    assert "HR drift" not in pw.split("</div>", 1)[1]
    assert drift.count("% HR drift") == 4 and "decoupling\n" not in drift
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


def test_week_tiles_count_back_from_newest_session(monkeypatch, tmp_path):
    # health metrics a week past the last workout move "data through", not
    # the training window: daily metrics usually run ahead of workout exports
    index = [_row("2026-08-01", 3.0, "pw_hr"), _row("2026-08-05", 3.0, "pw_hr")]
    metrics = [{"date": "2026-08-12", "name": "resting_heart_rate", "value": 50.0,
                "units": "count/min"}]
    baseline = [{"week": "2026-W32", "minutes": 25, "count": 2}]
    page = _render(monkeypatch, tmp_path, index, metrics, baseline)
    assert "data through 2026-08-12" in page
    assert '<div class="k">Training, last 7 days</div><div class="v">80' in page
    assert "2 sessions" in page and "2 walks" in page


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
