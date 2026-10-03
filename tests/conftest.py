import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEMPLATE_WORKSPACE = REPO_ROOT / "templates" / "workspace"
# Fully synthetic workspace (invented dates, values, ids): inputs only. The
# pipeline fixture below generates sessions, index, baseline and dashboard.
FIXTURE_WORKSPACE = FIXTURES / "workspace_min"

# Integration tests run against a real workspace (the dev's own training repo):
# $AUTOTRAINER_WORKSPACE, else a sibling Autotrainer_Alex checkout. Set before
# any script module is imported, since most resolve paths at import time.
WORKSPACE = Path(os.environ.get("AUTOTRAINER_WORKSPACE") or REPO_ROOT.parent / "Autotrainer_Alex")
HAVE_WORKSPACE = (WORKSPACE / "config" / "athlete.yaml").is_file()
if HAVE_WORKSPACE:
    os.environ["AUTOTRAINER_WORKSPACE"] = str(WORKSPACE)

requires_workspace = pytest.mark.skipif(
    not HAVE_WORKSPACE, reason=f"no workspace at {WORKSPACE} (set AUTOTRAINER_WORKSPACE)")


# ---------------------------------------------------------------- engine rule 4

# Large binary inputs: stat-only (a write still moves mtime/size); every other
# file is also content-hashed, so a rewrite of an already-dirty or gitignored
# file is caught too.
_STAT_ONLY = ("data/raw/photos/",)


def _git_state(path: Path) -> tuple[str, str] | None:
    """(HEAD, porcelain status) of the git repo rooted at `path`, or None when
    `path` is not the top of a work tree. --no-optional-locks keeps `git
    status` from refreshing the index file: the check itself writes nothing."""
    def git(*args):
        result = subprocess.run(["git", "--no-optional-locks", "-C", str(path), *args],
                                capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else None

    top = git("rev-parse", "--show-toplevel")
    if top is None or Path(top.strip()).resolve() != path.resolve():
        return None
    head = git("rev-parse", "--verify", "-q", "HEAD") or ""
    status = git("status", "--porcelain", "--untracked-files=all")
    return None if status is None else (head.strip(), status)


def _tree_state(path: Path) -> dict[str, tuple]:
    """{relative path: (size, mtime_ns[, sha256])} for every file under `path`
    outside .git, ignored files included; git status alone cannot see a
    rewrite of a file that was already modified, nor any gitignored output."""
    out = {}
    for p in sorted(path.rglob("*")):
        rel = p.relative_to(path).as_posix()
        if rel == ".git" or rel.startswith(".git/") or not p.is_file() or p.is_symlink():
            continue
        st = p.stat()
        entry = (st.st_size, st.st_mtime_ns)
        if not rel.startswith(_STAT_ONLY):
            entry += (hashlib.sha256(p.read_bytes()).hexdigest(),)
        out[rel] = entry
    return out


def _workspace_state(path: Path) -> dict | None:
    git = _git_state(path)
    return None if git is None else {"head": git[0], "status": git[1], "tree": _tree_state(path)}


def _state_diff(before: dict, after: dict, limit: int = 20) -> list[str]:
    """Human-readable differences between two _workspace_state snapshots."""
    lines = []
    if before["head"] != after["head"]:
        lines.append(f"HEAD {before['head'][:12] or '(none)'} -> {after['head'][:12] or '(none)'}")
    old, new = set(before["status"].splitlines()), set(after["status"].splitlines())
    lines += [f"status - {l}" for l in sorted(old - new)] + [f"status + {l}" for l in sorted(new - old)]
    t0, t1 = before["tree"], after["tree"]
    for rel in sorted(t0.keys() | t1.keys()):
        if rel not in t1:
            lines.append(f"removed  {rel}")
        elif rel not in t0:
            lines.append(f"created  {rel}")
        elif t0[rel] != t1[rel]:
            lines.append(f"modified {rel}")
    return lines[:limit] + ([f"... and {len(lines) - limit} more"] if len(lines) > limit else [])


@pytest.fixture(scope="session", autouse=True)
def real_workspace_untouched():
    """Engine rule 4: tests read the real workspace, never write it. Records
    HEAD, `git status --porcelain` and every file's size, mtime and content
    hash (gitignored files included) before the session and fails it if any
    differs afterwards, listing what changed. No-op without a workspace or
    when it is not a git repo. A coaching session editing the workspace
    concurrently trips it too, so the message names both possible causes."""
    before = _workspace_state(WORKSPACE) if HAVE_WORKSPACE else None
    yield
    if before is None:
        return
    after = _workspace_state(WORKSPACE) or {"head": "", "status": "", "tree": {}}
    changes = _state_diff(before, after)
    if changes:
        pytest.fail(f"the workspace at {WORKSPACE} changed during the test session — "
                    "either a test wrote to it (tests must never write to it, engine "
                    "rule 4) or something else edited it concurrently (re-run once "
                    "that is done):\n  " + "\n  ".join(changes), pytrace=False)


# ---------------------------------------------------------------- synthetic pipeline

def snapshot(root: Path) -> dict[str, str]:
    """{relative path: sha256} for every file under root."""
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def run_ingest(ws: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "AUTOTRAINER_WORKSPACE": str(ws)}
    return subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "ingest.py")],
                          env=env, cwd=ws, capture_output=True, text=True)


@pytest.fixture(scope="session")
def pipeline(tmp_path_factory):
    """FIXTURE_WORKSPACE copied to a temp dir and run through scripts/ingest.py
    (as a subprocess, exactly as /coach ingest does) three times. The first
    run does the work; the second and third must change nothing but the
    first run's consumed proposals."""
    fixture_before = snapshot(FIXTURE_WORKSPACE)
    ws = tmp_path_factory.mktemp("pipeline") / "workspace"
    shutil.copytree(FIXTURE_WORKSPACE, ws)
    runs, snaps = [], []
    for _ in range(3):
        runs.append(run_ingest(ws))
        snaps.append(snapshot(ws))
    return SimpleNamespace(ws=ws, runs=runs, snaps=snaps, fixture_before=fixture_before)
