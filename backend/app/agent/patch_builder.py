"""Deep Test Patch builder behind the graph's thin build-patch node."""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.agent.test_files import RejectedTestFile, validate_generated_test_files
from app.agent.workspace import GenerationWorkspace
from app.enums.coding_run import CodingRunStage
from app.schemas.agent_stream import PatchResult, RunFailure
from app.schemas.generation import ExternalReference, GeneratedFile

logger = logging.getLogger(__name__)

PATCH_DERIVATION_FAILED = "Could not write the generated tests or derive the patch."


@dataclass(frozen=True)
class PatchBuildRequest:
    """Plain inputs needed to build and persist a canonical Test Patch."""

    generated_files: list[GeneratedFile]
    checkout_root: Path | str | None
    is_revision_attempt: bool
    generation_branch: str
    coding_run_id: uuid.UUID
    external_references: list[ExternalReference]


@dataclass(frozen=True)
class PatchBuildOutcome:
    """A Test Patch result or a typed Run Failure."""

    patch_result: PatchResult | None = None
    failure: RunFailure | None = None


class PatchBuilder:
    """Validate proposals, write them, derive the Git diff, and persist the run."""

    def __init__(self, *, workspace_factory: Callable[[Path | str | None], GenerationWorkspace], recorder) -> None:
        self._workspace_factory = workspace_factory
        self._recorder = recorder

    def build(self, request: PatchBuildRequest) -> PatchBuildOutcome:
        try:
            validated = validate_generated_test_files(Path(request.checkout_root), request.generated_files) if request.checkout_root else list(request.generated_files)
        except RejectedTestFile as rejection:
            return PatchBuildOutcome(failure=RunFailure(failed_stage=CodingRunStage.generating, reason=rejection.reason))

        try:
            workspace = self._workspace_factory(request.checkout_root)
            if request.is_revision_attempt:
                workspace.reset_patch_state()
            workspace.write_test_files(validated)
            diff = workspace.diff()
            self._recorder.complete(
                request.coding_run_id,
                branch=request.generation_branch,
                diff=diff,
                generated_files=validated,
                external_references=request.external_references,
            )
        except Exception:
            logger.exception("Patch derivation failed")
            return PatchBuildOutcome(failure=RunFailure(failed_stage=CodingRunStage.generating, reason=PATCH_DERIVATION_FAILED))

        return PatchBuildOutcome(
            patch_result=PatchResult(
                coding_run_id=request.coding_run_id,
                diff=diff,
                generated_files=validated,
                external_references=request.external_references,
            )
        )
