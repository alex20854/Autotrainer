"""Engine vs workspace paths.

The engine (this repo: scripts, knowledge, templates) is shared; each athlete's
data lives in a separate *workspace* repo. A workspace is any directory with
`config/athlete.yaml`. Resolution order:

  1. $AUTOTRAINER_WORKSPACE
  2. the nearest ancestor of the current directory holding config/athlete.yaml
  3. the current directory (scripts that need a workspace call require())
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]
MARKER = Path("config") / "athlete.yaml"


def root() -> Path:
    env = os.environ.get("AUTOTRAINER_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        if (d / MARKER).is_file():
            return d
    return cwd


def require(path: Path) -> None:
    """Exit with a clear message when `path` is not an initialized workspace."""
    if not (path / MARKER).is_file():
        sys.exit(f"not an Autotrainer workspace: {path} (no {MARKER}). "
                 "cd into your workspace, set AUTOTRAINER_WORKSPACE, or run /coach setup.")
