"""PatchBuilder owns Test Patch validation, writing, diff derivation, and persistence."""

import uuid

from app.services.coding_runs.patch_builder import PatchBuilder, PatchBuildRequest
from app.schemas.agent_stream import PatchResult
from app.schemas.generation import ExternalReference, GeneratedFile

from tests.agent.nodes.test_graph import FakeWorkspace, RecordingRecorder, _workspace_factory


class RaisingDiffWorkspace(FakeWorkspace):
    """A workspace whose Git-derived diff step fails."""

    def diff(self):
        raise RuntimeError("git diff exploded")


def test_builder_writes_validated_files_derives_diff_and_persists_the_patch(tmp_path) -> None:
    """PatchBuilder returns a Test Patch result from plain inputs, without graph state."""
    (tmp_path / "tests").mkdir()
    coding_run_id = uuid.uuid4()
    recorder = RecordingRecorder()
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_login(): ...")
    files = [GeneratedFile(path="tests/test_auth.py", content="def test_login(): ...")]
    references = [ExternalReference(url="https://docs.pytest.org", title="pytest")]
    builder = PatchBuilder(workspace_factory=_workspace_factory(workspace), recorder=recorder)

    outcome = builder.build(
        PatchBuildRequest(
            generated_files=files,
            checkout_root=tmp_path,
            is_revision_attempt=False,
            generation_branch="qa-tests/direct",
            coding_run_id=coding_run_id,
            external_references=references,
        )
    )

    assert outcome.failure is None
    assert isinstance(outcome.patch_result, PatchResult)
    assert outcome.patch_result.coding_run_id == coding_run_id
    assert outcome.patch_result.diff == workspace.diff()
    assert [file.path for file in workspace.written] == ["tests/test_auth.py"]
    complete = next(event for event in recorder.events if event[0] == "complete")
    assert complete[1] == coding_run_id
    assert complete[2] == "qa-tests/direct"


def test_builder_returns_a_typed_failure_for_rejected_paths_before_writing(tmp_path) -> None:
    """Rejected Test File boundaries are generating-stage Run Failures, not exceptions."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text("real code")
    recorder = RecordingRecorder()
    workspace = FakeWorkspace()
    builder = PatchBuilder(workspace_factory=_workspace_factory(workspace), recorder=recorder)

    outcome = builder.build(
        PatchBuildRequest(
            generated_files=[GeneratedFile(path="app/auth.py", content="malicious")],
            checkout_root=tmp_path,
            is_revision_attempt=False,
            generation_branch="qa-tests/direct",
            coding_run_id=uuid.uuid4(),
            external_references=[],
        )
    )

    assert outcome.patch_result is None
    assert outcome.failure is not None
    assert outcome.failure.failed_stage == "generating"
    assert "application code" in outcome.failure.reason
    assert workspace.written is None
    assert recorder.events == []


def test_builder_returns_a_typed_failure_when_patch_derivation_fails(tmp_path) -> None:
    """Workspace failures become sanitized generating-stage Run Failures."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    workspace = RaisingDiffWorkspace()
    builder = PatchBuilder(workspace_factory=_workspace_factory(workspace), recorder=recorder)

    outcome = builder.build(
        PatchBuildRequest(
            generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_login(): ...")],
            checkout_root=tmp_path,
            is_revision_attempt=False,
            generation_branch="qa-tests/direct",
            coding_run_id=uuid.uuid4(),
            external_references=[],
        )
    )

    assert outcome.patch_result is None
    assert outcome.failure is not None
    assert outcome.failure.failed_stage == "generating"
    assert outcome.failure.reason == "Could not write the generated tests or derive the patch."
    assert workspace.written is not None
    assert recorder.events == []


def test_builder_resets_prior_patch_state_for_a_revision_attempt(tmp_path) -> None:
    """A Revision Attempt replaces the prior generated patch before writing again."""
    (tmp_path / "tests").mkdir()
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py")
    builder = PatchBuilder(workspace_factory=_workspace_factory(workspace), recorder=RecordingRecorder())

    outcome = builder.build(
        PatchBuildRequest(
            generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_revised(): ...")],
            checkout_root=tmp_path,
            is_revision_attempt=True,
            generation_branch="qa-tests/direct",
            coding_run_id=uuid.uuid4(),
            external_references=[],
        )
    )

    assert outcome.failure is None
    assert workspace.reset_count == 1
    assert [file.content for file in workspace.written] == ["def test_revised(): ..."]
