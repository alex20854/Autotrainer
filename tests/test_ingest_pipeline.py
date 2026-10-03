"""End-to-end: the synthetic workspace through scripts/ingest.py.

tests/fixtures/workspace_min holds only inputs (config, goals, benchmarks,
derived workout records, two extracted photo sidecars, daily metrics); every
generated file — sessions, index, baseline, proposals, dashboard — comes from
running the real pipeline over a temp copy (conftest `pipeline`). Runs without
any real workspace (AUTOTRAINER_WORKSPACE unset or pointing nowhere).
"""

import json

import build_index
from conftest import FIXTURE_WORKSPACE, snapshot
from lib import frontmatter


def _sessions(ws):
    out = {}
    for path in sorted((ws / "data" / "sessions").rglob("*.md")):
        fm, _ = frontmatter.load(path)
        out[path] = fm
    return out


def _index(ws):
    return [json.loads(l) for l in (ws / "data" / "index.jsonl").read_text().splitlines()]


def test_every_run_exits_zero(pipeline):
    for run in pipeline.runs:
        assert run.returncode == 0, run.stderr


def test_sessions_written_with_expected_modalities(pipeline):
    sessions = _sessions(pipeline.ws)
    modalities = sorted(fm["modality"] for fm in sessions.values())
    assert modalities == ["bike", "bikeerg", "bikeerg", "rowerg", "rowerg", "rowerg", "walk"]
    # the two console photos paired (one with a Health + Concept2 capture pair)
    paired = {fm["id"]: [s["kind"] for s in fm["sources"]] for fm in sessions.values()
              if any(s["kind"] == "photo" for s in fm["sources"])}
    assert paired == {"2030-05-08-bikeerg": ["health", "photo"],
                      "2030-05-13-bikeerg": ["c2", "health", "photo"]}
    # short walks stay baseline, never sessions
    baseline = [json.loads(l) for l in (pipeline.ws / "data" / "baseline.jsonl").read_text().splitlines()]
    assert [(b["week"], b["count"]) for b in baseline] == [("2030-W19", 1), ("2030-W21", 1)]


def test_sessions_satisfy_schema(pipeline):
    problems = []
    for path, fm in _sessions(pipeline.ws).items():
        problems += build_index.validate(fm, path)
    assert problems == []


def test_index_carries_decoupling_fields(pipeline):
    rows = {r["id"]: r for r in _index(pipeline.ws)}
    assert len(rows) == 7
    for r in rows.values():
        assert {"decoupling_pct", "decoupling_method", "decoupling_note"} <= r.keys()
        # a value has a method and no note; a null has a note and no method
        assert (r["decoupling_pct"] is None) == (r["decoupling_method"] is None)
        assert (r["decoupling_pct"] is None) == (r["decoupling_note"] is not None)
    assert rows["2030-05-13-bikeerg"]["decoupling_method"] == "pw_hr"  # watts from the C2 capture
    assert rows["2030-05-08-bikeerg"]["decoupling_method"] == "hr_drift"
    assert rows["2030-05-15-rowerg"]["decoupling_note"] == "window_too_short"
    assert rows["2030-05-18-walk"]["decoupling_note"] == "modality_excluded"
    assert rows["2030-05-13-bikeerg"]["efficiency_factor"] is not None


def test_dashboard_rendered_self_contained(pipeline):
    page = (pipeline.ws / "dashboard.html").read_text(encoding="utf-8")
    for section in ["Efficiency factor — BikeErg", "Avg watts per ride — BikeErg",
                    "Weekly minutes in zone", "Aerobic decoupling per session",
                    "HR drift per session", "Baseline activity", "VO&#8322;max in context",
                    "Benchmarks", "Recent sessions"]:
        assert f"<h2>{section}</h2>" in page, section
    assert "None" not in page
    for banned in ["http://", "https://", "src=", "@import"]:
        assert banned not in page, banned


def test_rerun_leaves_generated_files_byte_identical(pipeline):
    first, second, third = pipeline.snaps
    # proposals.json is the to-do list: run 1 consumed its auto-merges, so it
    # alone differs between runs 1 and 2; from run 2 on nothing changes at all
    assert {k for k in first.keys() | second.keys()
            if first.get(k) != second.get(k)} <= {"data/derived/proposals.json"}
    assert second == third
    proposals = json.loads((pipeline.ws / "data" / "derived" / "proposals.json").read_text())
    assert proposals["auto_merge"] == [] and proposals["ambiguous"] == []


def test_fixture_directory_untouched(pipeline):
    assert snapshot(FIXTURE_WORKSPACE) == pipeline.fixture_before
    for generated in ["data/sessions", "data/index.jsonl", "data/baseline.jsonl",
                      "dashboard.html", "data/derived/proposals.json"]:
        assert not (FIXTURE_WORKSPACE / generated).exists(), generated
