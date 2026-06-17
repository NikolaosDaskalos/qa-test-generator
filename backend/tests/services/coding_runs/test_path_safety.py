"""Confinement of untrusted candidate Repository paths to the checkout."""

from pathlib import Path

from app.services.coding_runs.path_safety import confine_candidate_path, confine_candidate_paths


def test_normal_nested_path_is_normalized_and_confined(tmp_path: Path) -> None:
    """A repo-relative path inside the checkout survives as a normalized POSIX hint."""
    assert confine_candidate_path(tmp_path, "app/./auth/../auth.py") == "app/auth.py"


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    assert confine_candidate_path(tmp_path, "/etc/passwd") is None


def test_parent_traversal_escaping_the_checkout_is_rejected(tmp_path: Path) -> None:
    assert confine_candidate_path(tmp_path, "../../etc/passwd") is None


def test_the_checkout_root_itself_is_rejected(tmp_path: Path) -> None:
    assert confine_candidate_path(tmp_path, ".") is None


def test_blank_candidate_is_rejected(tmp_path: Path) -> None:
    assert confine_candidate_path(tmp_path, "   ") is None


def test_symlink_escaping_the_checkout_is_rejected(tmp_path: Path) -> None:
    """A symlink inside the checkout pointing outside resolves out of root and is rejected."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("secret")
    (checkout / "link").symlink_to(outside)

    assert confine_candidate_path(checkout, "link/secret.py") is None


def test_plural_filter_keeps_safe_paths_in_order_and_drops_unsafe(tmp_path: Path) -> None:
    safe = confine_candidate_paths(tmp_path, ["app/auth.py", "/etc/passwd", "../escape", "tests/test_auth.py"])
    assert safe == ["app/auth.py", "tests/test_auth.py"]
