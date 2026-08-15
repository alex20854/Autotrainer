import build_dashboard as bd
import ingest


def test_dashboard_renders_repo_state():
    html_out = bd.build()
    for section in ["Efficiency factor", "Weekly minutes in zone",
                    "Aerobic decoupling", "Baseline activity", "Benchmarks",
                    "Recent sessions", "prefers-color-scheme", "data-tip"]:
        assert section in html_out
    # self-contained: no external requests of any kind
    for banned in ["http://", "https://", "src=", "@import"]:
        assert banned not in html_out, banned


def test_dashboard_in_ingest_pipeline():
    assert ingest.STEPS[-1] == "build_dashboard.py"
