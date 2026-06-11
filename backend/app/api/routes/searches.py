## Schema -> response_model -> API's output validation
## Model -> DB table inference

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from app.agent.graph import run_agent_on_session
from app.dependencies import CurrentUser, SessionDep
from app.models.search import SearchSession
from app.schemas.search import AgentChatRequest, AgentChatResponse, SearchSessionCreate, SearchSessionPublic, SearchSessionsPublic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/searches", tags=["searches"])


## Get all sessions
@router.get("/", response_model=SearchSessionsPublic)
def read_searches(session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100):
    if current_user.is_superuser:
        count_statement = select(func.count()).select_from(SearchSession)
        count = session.exec(count_statement).one()
        statement = select(SearchSession).offset(skip).limit(limit)
        sessions = session.exec(statement).all()
    else:
        count_statement = select(func.count()).select_from(SearchSession).where(SearchSession.owner_id == current_user.id)
        count = session.exec(count_statement).one()
        statement = select(SearchSession).where(SearchSession.owner_id == current_user.id).offset(skip).limit(limit)
        sessions = session.exec(statement).all()

    logger.info("Search sessions listed user_id=%s returned_count=%s total_count=%s", current_user.id, len(sessions), count)
    return SearchSessionsPublic(data=sessions, count=count)  # type: ignore[arg-type]


## Create new search session
@router.post("/", response_model=SearchSessionPublic)
def create_search(*, session: SessionDep, current_user: CurrentUser, search_in: SearchSessionCreate) -> Any:
    search_session = SearchSession.model_validate(search_in, update={"owner_id": current_user.id})
    session.add(search_session)
    session.commit()
    session.refresh(search_session)
    logger.info("Search session created session_id=%s owner_id=%s", search_session.id, current_user.id)
    return search_session


## Continue Search with Agent (use previous memory)


@router.post("/{id}/chat", response_model=AgentChatResponse)
async def chat_with_agent_on_search(*, session: SessionDep, current_user: CurrentUser, id: uuid.UUID, chat_in: AgentChatRequest) -> Any:
    search_session = session.get(SearchSession, id)
    if not search_session:
        logger.warning("Search chat rejected because the session was not found session_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=404, detail="Search session not found")

    if not current_user.is_superuser and (search_session.owner_id != current_user.id):
        logger.warning("Search chat access denied session_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=403, detail="Not authorized to access this search session")

    if not chat_in.message or not chat_in.message.strip():
        logger.warning("Search chat rejected because the message is empty session_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=400, detail="Message is required. It cannot be empty or whitespace")

    logger.info("Search chat started session_id=%s user_id=%s message_length=%s", id, current_user.id, len(chat_in.message))
    try:
        reply = await run_agent_on_session(session_db=session, search_session=search_session, current_user_id=current_user.id, user_message=chat_in.message)
    except Exception:
        logger.error("Search chat failed session_id=%s user_id=%s", id, current_user.id, exc_info=True)
        raise

    logger.info("Search chat completed session_id=%s user_id=%s reply_length=%s", id, current_user.id, len(reply))
    return AgentChatResponse(session_id=search_session.id, reply=reply)
