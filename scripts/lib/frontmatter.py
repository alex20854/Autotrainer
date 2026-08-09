"""Markdown + YAML frontmatter read/write.

Session files, plan files, and KB entries all use the same envelope:

    ---
    <yaml mapping>
    ---
    <markdown body>

parse() and dump() round-trip that envelope without touching the body.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DELIM = "---"


class FrontmatterError(ValueError):
    pass


def parse(text: str) -> tuple[dict, str]:
    """Split a document into (frontmatter dict, body). Body keeps no leading newline."""
    if not text.startswith(DELIM + "\n"):
        raise FrontmatterError("document does not start with '---' frontmatter")
    try:
        fm_text, body = _split_rest(text)
    except ValueError as e:
        raise FrontmatterError(str(e)) from None
    data = yaml.safe_load(fm_text)
    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter is not a YAML mapping")
    return data, body


def _split_rest(text: str) -> tuple[str, str]:
    # text = "---\n<yaml>\n---\n<body>"
    rest = text[len(DELIM) + 1 :]
    idx = rest.find("\n" + DELIM + "\n")
    if idx == -1:
        # allow a file that is frontmatter-only, closed by a trailing "---\n" or "---"
        stripped = rest.rstrip("\n")
        if stripped.endswith("\n" + DELIM):
            return stripped[: -len(DELIM) - 1], ""
        raise ValueError("closing '---' not found")
    return rest[:idx], rest[idx + len(DELIM) + 2 :].lstrip("\n")


def dump(data: dict, body: str = "") -> str:
    fm = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=None)
    doc = f"{DELIM}\n{fm}{DELIM}\n"
    if body:
        doc += "\n" + body.rstrip("\n") + "\n"
    return doc


def load(path: str | Path) -> tuple[dict, str]:
    return parse(Path(path).read_text(encoding="utf-8"))


def save(path: str | Path, data: dict, body: str = "") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(data, body), encoding="utf-8")


def update(path: str | Path, updates: dict) -> dict:
    """Merge top-level keys into an existing file's frontmatter, preserving the body."""
    data, body = load(path)
    data.update(updates)
    save(path, data, body)
    return data
