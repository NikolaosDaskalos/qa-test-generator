"""Write-safety validation of proposed Test File paths.

The generator proposes complete files by path, but those paths are untrusted: the
backend writes only validated Test Files. Before any write a candidate is confined
to the checkout (absolute paths, traversal, and symlink targets rejected) and
required to be a Python file. Whether it may be written then depends on what is
already in the Repository: an *existing* file may be overwritten only if it is a
recognized Test File (never application or source code), while a *new* file is
permitted only beneath a test root (`tests`/`test`) that already exists in the
checkout — the generator may not invent a test structure. A survivor is a
normalized, checkout-relative POSIX string; failures raise ``RejectedTestFile``
carrying a user-safe reason.
"""

import os
from pathlib import Path, PurePosixPath

from app.agent.paths import confine_candidate_path

# Directory names that constitute a test root.
TEST_ROOT_NAMES = {"tests", "test"}


class RejectedTestFile(Exception):
    """A proposed Test File failed a write-safety boundary; carries a user-safe reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def discover_test_roots(checkout_root: Path) -> frozenset[str]:
    """Find the checkout's existing test roots as checkout-relative POSIX dirs.

    A test root is a directory named ``tests`` or ``test`` that already exists in
    the Repository, top-level or nested. Discovery does not follow symlinks and
    skips the ``.git`` directory. These roots are discovered once before any
    proposal is written; new files are admitted only beneath one of them.
    """
    root = Path(checkout_root).resolve()
    if not root.is_dir():
        return frozenset()

    found: set[str] = set()
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in dirnames:
            if name in TEST_ROOT_NAMES:
                found.add((Path(dirpath) / name).relative_to(root).as_posix())
    return frozenset(found)


def validate_test_file(checkout_root: Path, candidate: str, test_roots: frozenset[str]) -> str:
    """Return the safe checkout-relative POSIX path, or raise ``RejectedTestFile``.

    ``test_roots`` are the checkout's already-existing test roots (see
    ``discover_test_roots``); a new file is admitted only beneath one of them.
    """
    safe = confine_candidate_path(checkout_root, candidate)
    if safe is None:
        raise RejectedTestFile(f"Path is outside the repository checkout: {candidate!r}")

    if PurePosixPath(safe).suffix != ".py":
        raise RejectedTestFile(f"Only Python test files may be written: {safe!r}")
    # ``confine`` follows symlinks and returns the real target, so a symlink that
    # stays inside the checkout would pass containment; reject by walking the
    # original candidate's components for any symlink.
    if _has_symlink_component(Path(checkout_root), candidate):
        raise RejectedTestFile(f"Test file path resolves through a symlink: {safe!r}")

    if (Path(checkout_root) / safe).is_file():
        # Overwriting an existing file: only a recognized Test File, never source code.
        if not _is_test_path(safe):
            raise RejectedTestFile(f"Only recognized test files may be written, not application code: {safe!r}")
    elif not _under_test_root(safe, test_roots):
        # A new file may live only beneath a test root that already exists; the
        # generator may not create a new top-level or nested test root.
        raise RejectedTestFile(f"New test files are only allowed beneath an existing test root: {safe!r}")

    return safe


def _under_test_root(relative_posix: str, test_roots: frozenset[str]) -> bool:
    """Whether an existing test root is an ancestor directory of the path."""
    return any(parent.as_posix() in test_roots for parent in PurePosixPath(relative_posix).parents)


def _is_test_path(relative_posix: str) -> bool:
    """A recognized Python test file: a ``test_``/``_test`` module or under a tests dir."""
    pure = PurePosixPath(relative_posix)
    name = pure.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(part in TEST_ROOT_NAMES for part in pure.parts[:-1])


def _has_symlink_component(checkout_root: Path, candidate: str) -> bool:
    """Whether any component of the candidate under the checkout is a symlink."""
    current = checkout_root
    for part in PurePosixPath(os.path.normpath(candidate)).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False
