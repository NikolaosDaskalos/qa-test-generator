"""Write-safety validation of proposed Test File paths before any write."""

from pathlib import Path

import pytest

from app.agent.test_files import RejectedTestFile, validate_test_file


def test_recognized_test_file_inside_checkout_is_accepted(tmp_path: Path) -> None:
    """A repo-relative path to a test-named Python file survives as a normalized hint."""
    assert validate_test_file(tmp_path, "tests/test_auth.py") == "tests/test_auth.py"


def test_suffix_test_module_outside_a_tests_dir_is_accepted(tmp_path: Path) -> None:
    """A ``*_test.py`` module is recognized even outside a tests directory."""
    assert validate_test_file(tmp_path, "app/auth_test.py") == "app/auth_test.py"


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "/etc/test_passwd.py")


def test_parent_traversal_escaping_the_checkout_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "../tests/test_escape.py")


def test_non_python_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "tests/test_auth.txt")


def test_application_or_source_file_is_rejected(tmp_path: Path) -> None:
    """A Python file that is not a recognized test is rejected as application code."""
    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "app/auth.py")


def test_symlink_target_is_rejected(tmp_path: Path) -> None:
    """A path whose component is a symlink inside the checkout is rejected."""
    (tmp_path / "tests").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "tests" / "link").symlink_to(outside)

    with pytest.raises(RejectedTestFile):
        validate_test_file(tmp_path, "tests/link/test_auth.py")
