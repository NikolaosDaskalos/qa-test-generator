"""Response schema for the owner-scoped AI Cost rollup endpoints (ADR-0014)."""

from pydantic import BaseModel


class AiCostRollupPublic(BaseModel):
    """A summed AI Cost total across one attribution dimension — session, Repository, or user.

    Every rollup — per Repository Session, per Repository, per user, and the superuser-only
    all-users total — is the same ``SUM`` over the persisted Usage Records, differing only in
    the ownership-gated filter applied. ``cost`` sums the priced calls (an unpriced model
    contributes its tokens but no cost); a dimension with no recorded usage reads back a
    well-defined zero, never an error.
    """

    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
