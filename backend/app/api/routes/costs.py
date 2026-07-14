"""AI Cost rollup routes: owner-scoped sums per session, Repository, user, and (superuser) all users."""

import uuid

from fastapi import APIRouter, Depends

from app.api.dependencies import CostRollupServiceDep, CurrentUser, get_current_active_superuser
from app.schemas import AiCostRollupPublic

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/session/{repository_session_id}", response_model=AiCostRollupPublic)
def read_session_cost(*, cost_rollup_service: CostRollupServiceDep, current_user: CurrentUser, repository_session_id: uuid.UUID) -> AiCostRollupPublic:
    """Return a Repository Session's total AI Cost — the sum of its turns' costs — for its owner (ADR-0014)."""
    return cost_rollup_service.session_rollup(repository_session_id=repository_session_id, user=current_user)


@router.get("/repository/{repository_id}", response_model=AiCostRollupPublic)
def read_repository_cost(*, cost_rollup_service: CostRollupServiceDep, current_user: CurrentUser, repository_id: uuid.UUID) -> AiCostRollupPublic:
    """Return a Repository's total AI Cost across all its sessions, for its owner (ADR-0014)."""
    return cost_rollup_service.repository_rollup(repository_id=repository_id, user=current_user)


@router.get("/me", response_model=AiCostRollupPublic)
def read_my_cost(*, cost_rollup_service: CostRollupServiceDep, current_user: CurrentUser) -> AiCostRollupPublic:
    """Return the requesting user's total AI Cost across all their repositories (ADR-0014)."""
    return cost_rollup_service.user_rollup(user=current_user)


@router.get("/all", response_model=AiCostRollupPublic, dependencies=[Depends(get_current_active_superuser)])
def read_all_users_cost(*, cost_rollup_service: CostRollupServiceDep) -> AiCostRollupPublic:
    """Return the global AI Cost total across every user — superuser-only (ADR-0014)."""
    return cost_rollup_service.all_users_rollup()
