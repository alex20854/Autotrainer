import build_dashboard as bd
import build_index
import ingest
from lib import frontmatter

from conftest import WORKSPACE, requires_workspace


@requires_workspace
def test_dashboard_renders_workspace_state():
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


@requires_workspace
def test_workspace_sessions_satisfy_schema():
    problems = []
    for path in sorted((WORKSPACE / "data" / "sessions").rglob("*.md")):
        fm, _ = frontmatter.load(path)
        problems += build_index.validate(fm, path)
    assert problems == []
