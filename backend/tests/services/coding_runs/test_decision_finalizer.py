"""DecisionFinalizer owns the owner's approve/reject finalization from plain inputs.

These exercise the deep finalizer directly — with a fake publisher, workspace, and
recorder — without resuming or running the graph. It commits, pushes, records, and
restores the checkout for an approval; discards and records the rejection for a
reject; and maps a commit/push failure to a typed ``git_commit`` / ``git_push`` Run
Failure, never an escaping exception and never a raw state dict.
"""

import uuid

from app.services.coding_runs.decision_finalizer import DecisionFinalizer
from app.errors.git_errors import GitError
from app.schemas.agent_stream import RunApproved, RunFailure, RunRejected
from app.schemas.review import ReviewFinding


class TimelinePublisher:
    """A ``PatchPublisher`` recording commit/push onto a shared timeline; can fail either step."""

    def __init__(self, timeline: list, *, fail_on: str | None = None) -> None:
        self._timeline = timeline
        self._fail_on = fail_on
        self.committed = None
        self.pushed = False

    def commit(self, message):
        if self._fail_on == "commit":
            raise GitError("git commit failed for secret-token")
        self.committed = message
        self._timeline.append(("commit", message))

    def push(self):
        if self._fail_on == "push":
            raise GitError("git push rejected for secret-token")
        self.pushed = True
        self._timeline.append(("push",))


class TimelineWorkspace:
    """A ``GenerationWorkspace`` recording the checkout-restore onto a shared timeline."""

    def __init__(self, timeline: list) -> None:
        self._timeline = timeline
        self.discarded = None

    def discard_generation(self, indexed_commit_sha, branch):
        self.discarded = (indexed_commit_sha, branch)
        self._timeline.append(("discard_generation", indexed_commit_sha, branch))


class TimelineRecorder:
    """A ``RunRecorder`` recording approve/reject onto a shared timeline."""

    def __init__(self, timeline: list) -> None:
        self._timeline = timeline

    def approve(self, coding_run_id):
        self._timeline.append(("approve", coding_run_id))

    def reject(self, coding_run_id):
        self._timeline.append(("reject", coding_run_id))


def test_approve_commits_pushes_records_then_restores_checkout_in_order() -> None:
    """An approval commits, pushes, records the run approved, then restores the checkout — in that order."""
    timeline: list = []
    coding_run_id = uuid.uuid4()
    publisher = TimelinePublisher(timeline)
    workspace = TimelineWorkspace(timeline)
    finalizer = DecisionFinalizer(recorder=TimelineRecorder(timeline))

    outcome = finalizer.approve(
        publisher=publisher,
        workspace=workspace,
        coding_run_id=coding_run_id,
        generation_branch="qa-tests/fake",
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
        indexed_commit_sha="abc",
    )

    assert isinstance(outcome, RunApproved)
    assert outcome.coding_run_id == coding_run_id
    assert outcome.branch == "qa-tests/fake"
    assert outcome.diff.startswith("diff --git")
    # Commit precedes push precedes record-approved precedes checkout restore.
    assert [step[0] for step in timeline] == ["commit", "push", "approve", "discard_generation"]
    assert workspace.discarded == ("abc", "qa-tests/fake")


def test_discard_restores_checkout_then_records_the_rejection() -> None:
    """A reject restores the checkout and removes the branch, then records the run rejected, preserving the findings."""
    timeline: list = []
    coding_run_id = uuid.uuid4()
    workspace = TimelineWorkspace(timeline)
    finalizer = DecisionFinalizer(recorder=TimelineRecorder(timeline))
    findings = [ReviewFinding(category="readability", detail="clear and idiomatic")]

    outcome = finalizer.discard(
        workspace=workspace,
        coding_run_id=coding_run_id,
        generation_branch="qa-tests/fake",
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
        indexed_commit_sha="abc",
        findings=findings,
    )

    assert isinstance(outcome, RunRejected)
    assert outcome.coding_run_id == coding_run_id
    assert outcome.diff.startswith("diff --git")
    assert [finding.category for finding in outcome.findings] == ["readability"]
    # The checkout is restored (local Git only — no commit or push) before the run is recorded rejected.
    assert [step[0] for step in timeline] == ["discard_generation", "reject"]
    assert workspace.discarded == ("abc", "qa-tests/fake")


def test_approve_commit_failure_short_circuits_before_push(caplog) -> None:
    """A failed commit is a sanitized git_commit Run Failure that never pushes, approves, or restores the checkout."""
    timeline: list = []
    publisher = TimelinePublisher(timeline, fail_on="commit")
    workspace = TimelineWorkspace(timeline)
    finalizer = DecisionFinalizer(recorder=TimelineRecorder(timeline))

    outcome = finalizer.approve(
        publisher=publisher,
        workspace=workspace,
        coding_run_id=uuid.uuid4(),
        generation_branch="qa-tests/fake",
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
        indexed_commit_sha="abc",
    )

    assert isinstance(outcome, RunFailure)
    assert outcome.failed_stage == "git_commit"
    # Nothing past the commit ran, and the credential is never leaked into the reason or logs.
    assert publisher.pushed is False
    assert timeline == []
    assert "secret-token" not in outcome.reason
    assert "secret-token" not in caplog.text


def test_approve_push_failure_after_commit_is_a_git_push_failure(caplog) -> None:
    """A push that fails after a successful commit is a sanitized git_push Run Failure that never approves or restores."""
    timeline: list = []
    publisher = TimelinePublisher(timeline, fail_on="push")
    workspace = TimelineWorkspace(timeline)
    finalizer = DecisionFinalizer(recorder=TimelineRecorder(timeline))

    outcome = finalizer.approve(
        publisher=publisher,
        workspace=workspace,
        coding_run_id=uuid.uuid4(),
        generation_branch="qa-tests/fake",
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
        indexed_commit_sha="abc",
    )

    assert isinstance(outcome, RunFailure)
    assert outcome.failed_stage == "git_push"
    # The commit happened, but the run is neither approved nor the checkout restored, and the credential is never leaked.
    assert publisher.committed is not None
    assert [step[0] for step in timeline] == ["commit"]
    assert workspace.discarded is None
    assert "secret-token" not in outcome.reason
    assert "secret-token" not in caplog.text
