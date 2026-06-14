"""The closed, typed event vocabulary for the Agent Stream.

These Pydantic models are the single source of truth for what a Repository
question or Test-Generation Task may report. Each event carries a literal
``type`` discriminant so the union is exhaustively matchable. Only the SSE
adapter serializes them to the wire (via ``model_dump_json``); no other module
knows the wire format.

Deliberate outcomes (insufficient evidence, a rejected Test Patch) are normal
terminal ``Result`` events, never errors. Unexpected transport failures stay an
out-of-band concern of the adapter and are deliberately absent from this union.
"""

import uuid
from typing import Literal

from pydantic import BaseModel


class Citation(BaseModel):
    """A single Repository source backing an answer."""

    source: str


class Stage(BaseModel):
    """Stage progress for the synchronous answer flow."""

    type: Literal["stage"] = "stage"
    stage: Literal["retrieving", "generating"]


class Token(BaseModel):
    """One streamed chunk of generated answer content."""

    type: Literal["token"] = "token"
    content: str


class Sources(BaseModel):
    """Retrieved source paths.

    An internal hop only: the session service consumes this to build
    ``Citations`` and never forwards it, so it is never serialized to the wire.
    """

    type: Literal["sources"] = "sources"
    sources: list[str]


class Citations(BaseModel):
    """De-duplicated file citations for the answer."""

    type: Literal["citations"] = "citations"
    citations: list[Citation]


class Result(BaseModel):
    """The terminal domain event reflecting the persisted exchange."""

    type: Literal["result"] = "result"
    repository_session_id: uuid.UUID
    assistant_message_id: uuid.UUID
    answer: str
    citations: list[Citation]


AgentStreamEvent = Stage | Token | Sources | Citations | Result
