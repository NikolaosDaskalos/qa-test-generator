"""Confine untrusted candidate Repository paths to the checkout.

The planner may suggest candidate Repository paths, but they are untrusted hints.
Before any survive into later graph nodes they are normalized and confined to the
Repository checkout: absolute paths, parent-directory traversal, and symlink
escapes are rejected. A survivor is returned as a normalized, checkout-relative
POSIX string usable as a retrieval hint — never an absolute filesystem path.
"""

from pathlib import Path, PurePosixPath


def confine_candidate_path(checkout_root: Path, candidate: str) -> str | None:
    """Normalize and confine one candidate path, or return ``None`` if unsafe."""
    return _confine(Path(checkout_root).resolve(), candidate)


def confine_candidate_paths(checkout_root: Path, candidates: list[str]) -> list[str]:
    """Confine a list of candidate paths, dropping unsafe ones and preserving order."""
    root = Path(checkout_root).resolve()
    return [safe for candidate in candidates if (safe := _confine(root, candidate)) is not None]


def _confine(root: Path, candidate: str) -> str | None:
    """Confine one candidate against an already-resolved ``root``."""
    text = candidate.strip()
    if not text:
        return None
    if PurePosixPath(text).is_absolute() or "\x00" in text:
        return None

    # ``resolve`` collapses ``.``/``..`` and follows symlinks, so an escape via either
    # lands outside ``root`` and is caught by the containment check below.
    resolved = (root / text).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        return None

    return resolved.relative_to(root).as_posix()
