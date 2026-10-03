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


def is_upgradable(fm: dict) -> bool:
    """A Health-only session written automatically and never judged. A photo
    that arrives later (photos usually trail the Health pull) may upgrade it in
    place: propose_matches re-offers its record for pairing, apply_merges
    rewrites the file. Anything carrying judgment — compliance, a prescription
    link, a non-auto match — is never rewritten."""
    sources = fm.get("sources") or []
    return (len(sources) == 1 and sources[0].get("kind") == "health"
            and fm.get("match_method") == "auto"
            and fm.get("compliance") is None and fm.get("prescription_id") is None)


def upgradable_refs(sessions_dir: Path) -> set[str]:
    """Record refs held only by upgradable sessions (see is_upgradable)."""
    refs = set()
    if sessions_dir.is_dir():
        for path in sessions_dir.rglob("*.md"):
            fm, _ = frontmatter.load(path)
            if is_upgradable(fm):
                refs.add(fm["sources"][0].get("ref"))
    return refs - {None}


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
