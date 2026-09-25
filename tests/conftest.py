import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEMPLATE_WORKSPACE = REPO_ROOT / "templates" / "workspace"

# Integration tests run against a real workspace (the dev's own training repo):
# $AUTOTRAINER_WORKSPACE, else a sibling Autotrainer_Alex checkout. Set before
# any script module is imported, since they resolve paths at import time.
WORKSPACE = Path(os.environ.get("AUTOTRAINER_WORKSPACE") or REPO_ROOT.parent / "Autotrainer_Alex")
HAVE_WORKSPACE = (WORKSPACE / "config" / "athlete.yaml").is_file()
if HAVE_WORKSPACE:
    os.environ["AUTOTRAINER_WORKSPACE"] = str(WORKSPACE)

requires_workspace = pytest.mark.skipif(
    not HAVE_WORKSPACE, reason=f"no workspace at {WORKSPACE} (set AUTOTRAINER_WORKSPACE)")
