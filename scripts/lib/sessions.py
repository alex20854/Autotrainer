"""Read helpers over the canonical session files (shared by scripts)."""

from __future__ import annotations

from pathlib import Path

from . import frontmatter


def already_claimed(sessions_dir: Path) -> set[str]:
    """Refs (record files / photos / extractions) already attached to a session."""
    claimed = set()
    if sessions_dir.is_dir():
        for path in sessions_dir.rglob("*.md"):
            fm, _ = frontmatter.load(path)
            for src in fm.get("sources") or []:
                for key in ("ref", "extraction"):
                    if src.get(key):
                        claimed.add(src[key])
    return claimed


def load_sessions(sessions_dir: Path) -> list[dict]:
    """Existing sessions' time ranges, for attach-to-session detection."""
    sessions = []
    if sessions_dir.is_dir():
        for path in sorted(sessions_dir.rglob("*.md")):
            fm, _ = frontmatter.load(path)
            if fm.get("start") and fm.get("end"):
                sessions.append({"id": fm.get("id"), "start": fm["start"],
                                 "end": fm["end"], "modality": fm.get("modality")})
    return sessions
