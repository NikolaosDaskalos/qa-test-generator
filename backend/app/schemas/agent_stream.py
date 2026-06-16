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

from app.schemas.generation import ExternalReference, GeneratedFile


class Citation(BaseModel):
    """A single Repository source backing an answer."""

    source: str


class Stage(BaseModel):
    """Ordered progress marker for a Repository question or Test-Generation Task."""

    type: Literal["stage"] = "stage"
    stage: Literal["classifying", "planning", "retrieving", "researching", "generating"]


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


class RunStarted(BaseModel):
    """Identifies the persisted Coding Run backing a Test-Generation Task stream."""

    type: Literal["run_started"] = "run_started"
    coding_run_id: uuid.UUID


class RunFailure(BaseModel):
    """The terminal event for a Test-Generation Task that fails a bounded stage.

    ``failed_stage`` names where the run stopped and ``reason`` is a sanitized,
    user-safe explanation — never raw exception text or model output. The
    persisted Coding Run is identified once it exists.
    """

    type: Literal["run_failure"] = "run_failure"
    coding_run_id: uuid.UUID | None = None
    failed_stage: Literal["planning", "retrieving", "generating"]
    reason: str


class PatchResult(BaseModel):
    """The terminal event for a Test-Generation Task that produced a Test Patch.

    Carries the canonical unified diff derived by Git, the complete generated file
    proposals, and the External References consulted while writing them. The
    persisted Coding Run backing the run is always identified.
    """

    type: Literal["patch_result"] = "patch_result"
    coding_run_id: uuid.UUID
    diff: str
    generated_files: list[GeneratedFile]
    external_references: list[ExternalReference]


AgentStreamEvent = Stage | Token | Answer | Result | RunStarted | RunFailure | PatchResult
