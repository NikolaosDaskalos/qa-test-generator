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


class Answer(BaseModel):
    """The complete generated answer with its de-duplicated file citations.

    An internal hop only: the chain builder emits one at the end of a turn and
    the session service consumes it to persist the exchange and build the
    terminal ``Result``, so it is never serialized to the wire.
    """

    type: Literal["answer"] = "answer"
    text: str
    citations: list[Citation]


class Result(BaseModel):
    """The terminal domain event reflecting the persisted exchange."""

    type: Literal["result"] = "result"
    repository_session_id: uuid.UUID
    assistant_message_id: uuid.UUID
    answer: str
    citations: list[Citation]


AgentStreamEvent = Stage | Token | Answer | Result
