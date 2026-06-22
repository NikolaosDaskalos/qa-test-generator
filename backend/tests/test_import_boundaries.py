"""Enforce the dependency direction of the feature-oriented backend structure.

Feature workflows (``services``, ``agents``, ``rag``) describe *what* the system
does and must never reach back into HTTP transport or the composition root.
``core`` holds only shared configuration, security, exceptions, and lifecycle, so
it must not depend on the database, integrations, or any feature package. These
checks fail when an import leaks an HTTP or infrastructure concern into a layer
that should not know about it, regardless of whether behavior still works.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

# Map a package to import prefixes it is forbidden from depending on.
FORBIDDEN_IMPORTS: dict[str, list[str]] = {
    # Feature workflows must not import HTTP transport or the composition root.
    "app.services": ["fastapi", "app.api", "app.dependencies", "app.main"],
    "app.agents": ["fastapi", "app.api", "app.dependencies", "app.main"],
    "app.rag": ["fastapi", "app.api", "app.dependencies", "app.main"],
    # core stays a leaf of shared concerns: no HTTP, no infra, no features.
    "app.core": [
        "fastapi",
        "app.api",
        "app.dependencies",
        "app.main",
        "app.db",
        "app.db.models",
        "app.db.persistence",
        "app.crud",
        "app.integrations",
        "app.services",
        "app.agents",
        "app.rag",
    ],
}


def _module_name(path: Path) -> str:
    """Return the dotted module name for a file under ``app``."""
    relative = path.relative_to(APP_ROOT.parent).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return ".".join(parts)


def _imported_modules(path: Path) -> Iterator[str]:
    """Yield every fully-qualified module a file imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _violations() -> list[str]:
    """Collect human-readable boundary violations across the app package."""
    found: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if "alembic" in path.parts:
            continue
        module = _module_name(path)
        for package, forbidden in FORBIDDEN_IMPORTS.items():
            if module != package and not module.startswith(f"{package}."):
                continue
            for imported in _imported_modules(path):
                for prefix in forbidden:
                    if imported == prefix or imported.startswith(f"{prefix}."):
                        found.append(f"{module} imports {imported} (forbidden for {package})")
    return found


def test_no_forbidden_cross_layer_imports() -> None:
    violations = _violations()
    assert not violations, "Import-direction violations:\n" + "\n".join(sorted(violations))
