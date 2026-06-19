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

from app.enums.coding_run import CodingRunStage
from app.schemas.generation import ExternalReference, GeneratedFile
from app.schemas.review import ReviewFinding

# User-safe disclaimer carried on every review outcome: Patch Review is a static,
# evidence-based assessment that never runs the generated tests.
REVIEW_DISCLAIMER = "These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only."


class Citation(BaseModel):
    """A single Repository source backing an answer."""

    source: str


class Stage(BaseModel):
    """Ordered progress marker for a Repository question or Test-Generation Task."""

    type: Literal["stage"] = "stage"
    stage: Literal["classifying", "planning", "retrieving", "researching", "generating", "reviewing", "revising", "re_reviewing"]


class Token(BaseModel):
    """One streamed chunk of generated answer content."""

    type: Literal["token"] = "token"
    content: str


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
    failed_stage: CodingRunStage
    reason: str


class PatchResult(BaseModel):
    """The internal state record for a Test-Generation Task that produced a Test Patch.

    Carries the canonical unified diff derived by Git, the complete generated file
    proposals, and the External References consulted while writing them. The
    persisted Coding Run backing the run is always identified. This is built into
    graph state but never emitted on the Agent Stream, so it is not a member of the
    ``AgentStreamEvent`` union.
    """

    type: Literal["patch_result"] = "patch_result"
    coding_run_id: uuid.UUID
    diff: str
    generated_files: list[GeneratedFile]
    external_references: list[ExternalReference]


class ReviewResult(BaseModel):
    """The terminal event for a Test-Generation Task that completed Patch Review.

    A review is a scored, deliberate decision, not an error: ``score`` (0–10) is the
    reviewer's quality rating and ``threshold`` the pass bar the backend judged it
    against, so a client can show "8/10 — passed". ``accepted`` carries the backend's
    derived verdict, ``findings`` the human-readable observations behind it, and
    ``diff`` the assessed canonical Test Patch. ``disclaimer`` states that the tests
    were not executed and runtime correctness was not verified.
    """

    type: Literal["review_result"] = "review_result"
    coding_run_id: uuid.UUID
    accepted: bool
    score: int
    threshold: int
    findings: list[ReviewFinding]
    diff: str
    disclaimer: str = REVIEW_DISCLAIMER


class RunRejected(BaseModel):
    """The terminal event for a reviewed Test Patch the owner rejected and discarded.

    Rejection is a deliberate outcome, not an error: the generated changes are
    discarded from the working tree and the temporary branch removed, but the
    persisted review record is preserved, so this carries the assessed canonical
    diff and findings for inspection. ``disclaimer`` restates that the tests were
    never executed.
    """

    type: Literal["run_rejected"] = "run_rejected"
    coding_run_id: uuid.UUID
    diff: str
    findings: list[ReviewFinding]
    disclaimer: str = REVIEW_DISCLAIMER


class RunApproved(BaseModel):
    """The terminal event for a reviewed Test Patch the owner approved and pushed.

    Approval is a deliberate outcome: the reviewed patch is committed on its unique
    non-default ``branch`` and pushed to the remote with the Repository Credential,
    leaving that remote branch available for manual inspection or pull-request
    creation. The local checkout is then restored to the indexed commit. This carries
    the pushed branch and the approved canonical diff, a ready-to-show ``message``
    naming the pushed branch, and a ``disclaimer`` restating that the tests were never
    executed.
    """

    type: Literal["run_approved"] = "run_approved"
    coding_run_id: uuid.UUID
    branch: str
    diff: str
    message: str = ""
    disclaimer: str = REVIEW_DISCLAIMER


class RunNoChanges(BaseModel):
    """The terminal event when the generator proposes no test changes across all attempts.

    A deliberate, benign outcome — not an error: after the Revision Budget is spent the
    proposal is still empty, which the system reports as the existing tests already
    covering the requested cases. Carries the persisted Coding Run and a ready-to-show
    ``message``; no diff, since there is nothing to apply.
    """

    type: Literal["run_no_changes"] = "run_no_changes"
    coding_run_id: uuid.UUID
    message: str = ""


AgentStreamEvent = Stage | Token | Result | RunStarted | RunFailure | ReviewResult | RunRejected | RunApproved | RunNoChanges
