import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from sqlmodel import Session

from app.agent.tools import web_search
from app.core.config import settings
from app.models.search import SearchHistory, SearchSession

logger = logging.getLogger(__name__)

# LLM initialize
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=settings.OPENAI_API_KEY)


agent_app = create_agent(
    model=llm,
    tools=[web_search],
    # system_prompt=(
    #     "You are a helpful research assistant. "
    #     "Use the available tools when fresh or external information is needed. "
    #     "Answer clearly and concisely."
    # ),
    system_prompt=(
        "You are a helpful research assistant. "
        "Use the available tools when fresh or external information is needed. "
        "Always trust and cite tool results over your own knowledge. "
        "Do not guess dates. "
        "Answer clearly and concisely."
    ),
)


# Helpers


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_memory_from_session(search_session: SearchSession) -> list[dict[str, str]]:
    raw = search_session.memory or "[]"

    try:
        data = json.loads(raw)

        if not isinstance(data, list):
            logger.warning("Search session memory ignored because it is not a list session_id=%s", search_session.id)
            return []

        cleaned_messages: list[dict[str, str]] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role in {"user", "assistant"} and isinstance(content, str):
                cleaned_messages.append({"role": role, "content": content})

        logger.info("Search session memory loaded session_id=%s message_count=%s", search_session.id, len(cleaned_messages))
        return cleaned_messages

    except json.JSONDecodeError:
        logger.warning("Search session memory ignored because it contains invalid JSON session_id=%s", search_session.id)
        return []


def _convert_to_lc_messages(messages: list[dict[str, str]]) -> list[BaseMessage]:
    lc_messages: list[BaseMessage] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))

    return lc_messages


def _message_content_to_text(content: Any) -> str:
    """
    LangChain messages usually have str content, but newer model APIs
    may return structured content blocks. This helper keeps the DB memory clean.
    """

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)

        return "\n".join(parts).strip()

    return str(content)


def _extract_final_reply(result: dict[str, Any]) -> str:
    result_messages = result.get("messages", [])

    if not result_messages:
        return "No response from agent."

    last_msg = result_messages[-1]

    if isinstance(last_msg, AIMessage):
        return _message_content_to_text(last_msg.content)

    content = getattr(last_msg, "content", None)

    if content is None:
        return "No response content."

    return _message_content_to_text(content)


def _append_and_trim_memory(existing: list[dict[str, str]], user_message: str, assistant_message: str, max_messages: int = 50) -> list[dict[str, str]]:
    updated = [*existing, {"role": "user", "content": user_message}, {"role": "assistant", "content": assistant_message}]

    return updated[-max_messages:]


def _save_memory_to_session(session_db: Session, search_session: SearchSession, messages: list[dict[str, str]]) -> None:
    search_session.memory = json.dumps(messages, ensure_ascii=False)
    search_session.updated_at = _utc_now()

    session_db.add(search_session)
    session_db.commit()
    session_db.refresh(search_session)
    logger.info("Search session memory saved session_id=%s message_count=%s", search_session.id, len(messages))


def _save_search_history(session_db: Session, search_session: SearchSession, current_user_id: uuid.UUID, user_message: str, reply_text: str) -> None:
    history = SearchHistory(session_id=search_session.id, owner_id=current_user_id, query=user_message, result=reply_text)

    session_db.add(history)
    session_db.commit()
    logger.info("Search history saved session_id=%s history_id=%s user_id=%s", search_session.id, history.id, current_user_id)


# Main Executor


async def run_agent_on_session(session_db: Session, search_session: SearchSession, current_user_id: uuid.UUID, user_message: str) -> str:
    logger.info("Search agent run started session_id=%s user_id=%s", search_session.id, current_user_id)
    # Step 1: Load previous memory
    memory_messages = _load_memory_from_session(search_session)

    # Step 2: Convert memory to LangChain messages and append current user message
    lc_messages = _convert_to_lc_messages(memory_messages)
    lc_messages.append(HumanMessage(content=user_message))

    # Step 3: Invoke LangChain v1 agent
    try:
        result = await agent_app.ainvoke({"messages": lc_messages})
    except Exception:
        logger.error("Search agent invocation failed session_id=%s user_id=%s", search_session.id, current_user_id, exc_info=True)
        raise

    reply_text = _extract_final_reply(result)
    if not reply_text:
        logger.warning("Search agent returned an empty reply session_id=%s user_id=%s", search_session.id, current_user_id)

    # Step 4: Update session memory
    new_memory = _append_and_trim_memory(existing=memory_messages, user_message=user_message, assistant_message=reply_text)

    _save_memory_to_session(session_db=session_db, search_session=search_session, messages=new_memory)

    # Step 5: Record search history
    _save_search_history(
        session_db=session_db, search_session=search_session, current_user_id=current_user_id, user_message=user_message, reply_text=reply_text
    )

    logger.info("Search agent run completed session_id=%s user_id=%s reply_length=%s", search_session.id, current_user_id, len(reply_text))
    return reply_text
