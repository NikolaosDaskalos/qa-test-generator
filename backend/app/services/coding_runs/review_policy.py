"""The resolved Patch Review policy, fixed once at application composition.

Patch Review is governed by two numbers: the ``pass_threshold`` a Test Patch's
score must reach for the backend to accept it, and the ``max_generation_retries``
budget the post-review router spends revising a below-threshold (or empty) patch
before it escalates or reports the tests as already covering. Resolving both into
one frozen value at the composition root keeps them coherent: no graph node,
router, or Generation Retries helper reads global settings later, and the two
values can never drift apart or be threaded one without the other.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import settings


@dataclass(frozen=True)
class ReviewPolicy:
    """The pass bar and the Generation Retries budget for one graph composition."""

    pass_threshold: int
    max_generation_retries: int

    @classmethod
    def from_settings(cls) -> "ReviewPolicy":
        """Resolve the production policy from global configuration, once."""
        return cls(
            pass_threshold=settings.REVIEW_PASS_THRESHOLD,
            max_generation_retries=settings.MAX_GENERATION_RETRIES,
        )
