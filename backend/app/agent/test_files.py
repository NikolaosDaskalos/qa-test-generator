"""Write-safety validation of proposed Test File paths.

The generator proposes complete files by path, but those paths are untrusted: the
backend writes only validated Test Files. Before any write a candidate is confined
to the checkout (absolute paths, traversal, and symlink targets rejected), required
to be a Python file, and required to be a *recognized test file* — never an
application or source file. A survivor is a normalized, checkout-relative POSIX
string; failures raise ``RejectedTestFile`` carrying a user-safe reason.
"""

import os
from pathlib import Path, PurePosixPath

from app.agent.paths import confine_candidate_path


class RejectedTestFile(Exception):
    """A proposed Test File failed a write-safety boundary; carries a user-safe reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def validate_test_file(checkout_root: Path, candidate: str) -> str:
    """Return the safe checkout-relative POSIX path, or raise ``RejectedTestFile``."""
    safe = confine_candidate_path(checkout_root, candidate)
    if safe is None:
        raise RejectedTestFile(f"Path is outside the repository checkout: {candidate!r}")

    if PurePosixPath(safe).suffix != ".py":
        raise RejectedTestFile(f"Only Python test files may be written: {safe!r}")
    if not _is_test_path(safe):
        raise RejectedTestFile(f"Only recognized test files may be written, not application code: {safe!r}")
    # ``confine`` follows symlinks and returns the real target, so a symlink that
    # stays inside the checkout would pass containment; reject by walking the
    # original candidate's components for any symlink.
    if _has_symlink_component(Path(checkout_root), candidate):
        raise RejectedTestFile(f"Test file path resolves through a symlink: {safe!r}")

    return safe


def _is_test_path(relative_posix: str) -> bool:
    """A recognized Python test file: a ``test_``/``_test`` module or under a tests dir."""
    pure = PurePosixPath(relative_posix)
    name = pure.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(part in {"tests", "test"} for part in pure.parts[:-1])


def _has_symlink_component(checkout_root: Path, candidate: str) -> bool:
    """Whether any component of the candidate under the checkout is a symlink."""
    current = checkout_root
    for part in PurePosixPath(os.path.normpath(candidate)).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False
