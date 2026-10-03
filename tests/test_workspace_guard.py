"""The engine-rule-4 guard in conftest.py, exercised on throwaway repos."""
import subprocess

import conftest


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@" "example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@" "example.invalid",
                        "HOME": str(path), "PATH": "/usr/bin:/bin:/usr/local/bin"})


def _repo(tmp_path):
    ws = tmp_path / "ws"
    (ws / "data" / "derived").mkdir(parents=True)
    (ws / ".gitignore").write_text("data/derived/proposals.json\n")
    (ws / "data" / "index.jsonl").write_text("{}\n")
    _git(ws, "init", "-q")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-qm", "init")
    return ws


def test_not_a_repo_is_a_noop(tmp_path):
    assert conftest._workspace_state(tmp_path) is None


def test_rewrite_of_dirty_file_and_ignored_output_are_caught(tmp_path):
    ws = _repo(tmp_path)
    (ws / "data" / "index.jsonl").write_text("{}\n{}\n")  # dirty before the session
    before = conftest._workspace_state(ws)
    assert conftest._state_diff(before, conftest._workspace_state(ws)) == []
    (ws / "data" / "index.jsonl").write_text("{}\n{}\n{}\n")  # porcelain unchanged: ' M'
    (ws / "data" / "derived" / "proposals.json").write_text("[]")  # gitignored
    changes = conftest._state_diff(before, conftest._workspace_state(ws))
    assert changes == ["created  data/derived/proposals.json", "modified data/index.jsonl"]


def test_commit_and_new_files_are_listed(tmp_path):
    ws = _repo(tmp_path)
    before = conftest._workspace_state(ws)
    (ws / "notes.md").write_text("x")
    _git(ws, "add", "notes.md")
    _git(ws, "commit", "-qm", "more")
    changes = conftest._state_diff(before, conftest._workspace_state(ws))
    assert changes[0].startswith("HEAD ") and "created  notes.md" in changes
