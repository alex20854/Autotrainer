import build_dashboard as bd
import build_index
import ingest
from lib import frontmatter

from conftest import WORKSPACE, requires_workspace


@requires_workspace
def test_dashboard_renders_workspace_state():
    html_out = bd.build()
    for section in ["Efficiency factor", "Weekly minutes in zone",
                    "Baseline activity", "Benchmarks",
                    "Recent sessions", "prefers-color-scheme", "data-tip"]:
        assert section in html_out
    # titled by method: HR drift unless some session has a power trace
    assert "Aerobic decoupling per session" in html_out or "HR drift per session" in html_out
    # self-contained: no external requests of any kind
    for banned in ["http://", "https://", "src=", "@import"]:
        assert banned not in html_out, banned


def test_dashboard_in_ingest_pipeline():
    assert ingest.STEPS[-1] == "build_dashboard.py"


@requires_workspace
def test_workspace_sessions_satisfy_schema():
    problems = []
    for path in sorted((WORKSPACE / "data" / "sessions").rglob("*.md")):
        fm, _ = frontmatter.load(path)
        problems += build_index.validate(fm, path)
    assert problems == []


def _row(date, pct, method, modality="bikeerg"):
    return {"id": f"{date}-{modality}", "date": date, "modality": modality,
            "duration_s": 2400, "hr_avg": 135, "hr_max": 150, "watts_avg": 180,
            "efficiency_factor": 1.33, "compliance_score": None, "tier": 1,
            "decoupling_pct": pct, "decoupling_method": method,
            "decoupling_note": None if pct is not None else "window_too_short",
            "file": f"data/sessions/{date}.md"}


def _render(monkeypatch, index):
    config = {"athlete": {"lthr": 160}, "zones": {"bands": {
        "z1": [0.00, 0.85], "z2": [0.85, 0.89], "z3": [0.90, 0.94],
        "z4": [0.95, 0.99], "z5": [1.00, 9.99]}}}
    monkeypatch.setattr(bd, "load_data", lambda: (index, [], config, {}, []))
    return bd.build()


def _card(html_out, title):
    start = html_out.index(f"<h2>{title}</h2>")
    return html_out[start:html_out.index('<div class="card', start)]


def test_decoupling_and_hr_drift_never_share_a_chart(monkeypatch):
    html_out = _render(monkeypatch, [_row("2026-08-01", 3.0, "pw_hr"),
                                     _row("2026-08-02", 7.5, "hr_drift"),
                                     _row("2026-08-03", None, None)])
    pw = _card(html_out, "Aerobic decoupling per session")
    drift = _card(html_out, "HR drift per session")
    assert "3.0% decoupling" in pw and "7.5%" not in pw and ">5%<" in pw
    assert "7.5% HR drift" in drift and "3.0%" not in drift and ">5%<" not in drift
    # the table says which kind each number is
    assert "<td>3.0</td>" in html_out and "<td>7.5 (HR)</td>" in html_out


def test_hr_drift_only_and_zone2_tile(monkeypatch):
    html_out = _render(monkeypatch, [_row("2026-08-02", 7.5, "hr_drift")])
    assert "Aerobic decoupling per session" not in html_out
    assert ">5%<" not in _card(html_out, "HR drift per session")
    # Zone 2 tile uses the resolved, contiguous band: [136, 144) bpm at LTHR 160
    assert "136–143" in html_out
