"""The AI Cost rollup service: owner-scoped sums across the attribution dimensions (ADR-0014)."""

import uuid

from app.core.errors.repository_errors import RepositoryAccessForbidden, RepositoryNotFound
from app.core.errors.session_errors import RepositorySessionAccessForbidden, RepositorySessionNotFound
from app.db.models import User
from app.db.persistence import CostTotals, RepositorySessionStore, RepositoryStore, UsageRecordStore
from app.schemas import AiCostRollupPublic


class CostRollupService:
    """Sum AI Cost across a Repository Session, a Repository, a user, or all users.

    Every rollup is the same ``SUM`` over the persisted Usage Records, differing only in the
    ownership-gated filter. The per-scope reads (session, Repository) are strictly owner-only —
    a user cannot read another user's totals — while the all-users rollup is superuser-only and
    gated at the route. A dimension with no recorded usage sums to a well-defined zero.
    """

    def __init__(self, session_store: RepositorySessionStore, repository_store: RepositoryStore, usage_record_store: UsageRecordStore) -> None:
        self.session_store = session_store
        self.repository_store = repository_store
        self.usage_record_store = usage_record_store

    def session_rollup(self, *, repository_session_id: uuid.UUID, user: User) -> AiCostRollupPublic:
        """Return a Repository Session's total, summed over its turns' Usage Records for the owner."""
        repository_session = self.session_store.get_by_id(repository_session_id)
        if not repository_session:
            raise RepositorySessionNotFound()
        if repository_session.user_id != user.id:
            raise RepositorySessionAccessForbidden()
        return self._public(self.usage_record_store.totals(repository_session_id=repository_session.id))

    def repository_rollup(self, *, repository_id: uuid.UUID, user: User) -> AiCostRollupPublic:
        """Return a Repository's total across all its sessions, summed for the owner."""
        repository = self.repository_store.get_by_id(repository_id)
        if not repository:
            raise RepositoryNotFound()
        if repository.user_id != user.id:
            raise RepositoryAccessForbidden()
        return self._public(self.usage_record_store.totals(repository_id=repository.id))

    def user_rollup(self, *, user: User) -> AiCostRollupPublic:
        """Return the requesting user's total across all their repositories."""
        return self._public(self.usage_record_store.totals(user_id=user.id))

    def all_users_rollup(self) -> AiCostRollupPublic:
        """Return the global total across every user (superuser-only, gated at the route)."""
        return self._public(self.usage_record_store.totals())

    @staticmethod
    def _public(totals: CostTotals) -> AiCostRollupPublic:
        return AiCostRollupPublic(
            cost=totals.cost, input_tokens=totals.input_tokens, output_tokens=totals.output_tokens, total_tokens=totals.total_tokens
        )
