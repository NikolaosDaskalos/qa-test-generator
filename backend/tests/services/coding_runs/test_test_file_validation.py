"""Write-safety validation of proposed Test File paths before any write."""

from pathlib import Path

import pytest

from app.schemas import GeneratedFile
from app.services.coding_runs.test_file_validation import RejectedTestFile, discover_test_roots, validate_test_file, verify_test_file_boundary


def test_new_test_file_beneath_an_existing_top_level_root_is_accepted(tmp_path: Path) -> None:
    """A new ``.py`` directly under an already-existing ``tests`` root is accepted."""
    (tmp_path / "tests").mkdir()
    roots = discover_test_roots(tmp_path)
    assert validate_test_file(tmp_path, "tests/test_auth.py", roots) == "tests/test_auth.py"


def test_new_test_file_in_a_new_subdir_beneath_an_existing_root_is_accepted(tmp_path: Path) -> None:
    """A new nested file is accepted as long as an ancestor test root already exists."""
    (tmp_path / "tests").mkdir()
    roots = discover_test_roots(tmp_path)
    assert validate_test_file(tmp_path, "tests/unit/test_auth.py", roots) == "tests/unit/test_auth.py"


def test_new_test_file_beneath_an_existing_nested_root_is_accepted(tmp_path: Path) -> None:
    """A new ``.py`` beneath an already-existing nested ``test`` root is accepted."""
    (tmp_path / "src" / "pkg" / "test").mkdir(parents=True)
    roots = discover_test_roots(tmp_path)
    assert validate_test_file(tmp_path, "src/pkg/test/test_auth.py", roots) == "src/pkg/test/test_auth.py"


def test_new_file_resembling_a_test_outside_existing_roots_is_rejected(tmp_path: Path) -> None:
    """A ``*_test.py`` name alone no longer admits a new file with no existing test root."""
    roots = discover_test_roots(tmp_path)
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "app/auth_test.py", roots)


def test_new_top_level_test_root_is_rejected(tmp_path: Path) -> None:
    """A new file that would create a top-level ``tests`` root (none exists) is rejected."""
    roots = discover_test_roots(tmp_path)
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "tests/test_auth.py", roots)


def test_new_nested_test_root_is_rejected(tmp_path: Path) -> None:
    """A new nested ``test`` root is rejected even when a top-level root exists."""
    (tmp_path / "tests").mkdir()
    roots = discover_test_roots(tmp_path)
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "src/pkg/test/test_auth.py", roots)


def test_modifying_an_existing_recognized_test_file_is_accepted(tmp_path: Path) -> None:
    """An existing recognized Test File may be overwritten even outside a discovered root."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth_test.py").write_text("def test_x(): ...")
    roots = discover_test_roots(tmp_path)
    assert validate_test_file(tmp_path, "app/auth_test.py", roots) == "app/auth_test.py"


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "/etc/test_passwd.py", discover_test_roots(tmp_path))


def test_parent_traversal_escaping_the_checkout_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "../tests/test_escape.py", discover_test_roots(tmp_path))


def test_non_python_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "tests/test_auth.txt", discover_test_roots(tmp_path))


def test_replacing_an_existing_source_file_is_rejected(tmp_path: Path) -> None:
    """Overwriting an existing non-test Python file is rejected as application code."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text("real code")
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "app/auth.py", discover_test_roots(tmp_path))


def test_symlink_target_is_rejected(tmp_path: Path) -> None:
    """A path whose component is a symlink inside the checkout is rejected."""
    (tmp_path / "tests").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "tests" / "link").symlink_to(outside)

    roots = discover_test_roots(tmp_path)
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "tests/link/test_auth.py", roots)


def test_discover_test_roots_finds_top_level_and_nested_dirs_only(tmp_path: Path) -> None:
    """Discovery returns existing ``tests``/``test`` directories, ignoring like-named files."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "pkg" / "test").mkdir(parents=True)
    (tmp_path / "test.py").write_text("not a directory")

    assert discover_test_roots(tmp_path) == frozenset({"tests", "src/pkg/test"})


def test_boundary_verifier_returns_no_finding_for_valid_test_files(tmp_path: Path) -> None:
    """The shared verifier accepts proposals that remain inside Test File scope."""
    (tmp_path / "tests").mkdir()

    finding = verify_test_file_boundary(tmp_path, [GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")])

    assert finding is None


def test_boundary_verifier_returns_a_scope_finding_for_application_code(tmp_path: Path) -> None:
    """The shared verifier turns a boundary escape into a review-ready finding."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text("real code")

    finding = verify_test_file_boundary(tmp_path, [GeneratedFile(path="app/auth.py", content="malicious")])

    assert finding is not None
    assert finding.category == "scope"
    assert "application code" in finding.detail
