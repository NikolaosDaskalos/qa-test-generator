"""DecisionFinalizer owns the owner's approve/reject finalization from plain inputs.

These exercise the deep finalizer directly — with a fake publisher, workspace, and
recorder — without resuming or running the graph. It commits, pushes, records, and
restores the checkout for an approval; discards and records the rejection for a
reject; and maps a commit/push failure to a typed ``git_commit`` / ``git_push`` Run
Failure, never an escaping exception and never a raw state dict.
"""

import uuid

from app.core.errors.git_errors import GitError
from app.core.errors.github_errors import GitHubError
from app.schemas import ReviewFinding, RunApproved, RunFailure, RunRejected
from app.services.coding_runs.decision_finalizer import DecisionFinalizer

PR_URL = "https://github.com/o/r/pull/7"


class TimelinePublisher:
    """A ``PatchPublisher`` recording commit/push/PR onto a shared timeline; can fail any step."""

    def __init__(self, timeline: list, *, fail_on: str | None = None) -> None:
        self._timeline = timeline
        self._fail_on = fail_on
        self.committed = None
        self.pushed = False
        self.pull_request_kwargs = None

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

    def open_pull_request(self, *, title, body, head):
        if self._fail_on == "pull_request":
            raise GitHubError("pull request rejected for secret-token")
        self.pull_request_kwargs = {"title": title, "body": body, "head": head}
        self._timeline.append(("open_pull_request", head))
        return PR_URL


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
        self.approved_pull_request_url = None

    def approve(self, coding_run_id, *, pull_request_url):
        self.approved_pull_request_url = pull_request_url
        self._timeline.append(("approve", coding_run_id))

    def reject(self, coding_run_id):
        self._timeline.append(("reject", coding_run_id))


def _approve(finalizer, publisher, workspace, *, coding_run_id, score=8, threshold=7, findings=None):
    """Drive an approval with the Patch Review the PR body is rendered from."""
    return finalizer.approve(
        publisher=publisher,
        workspace=workspace,
        coding_run_id=coding_run_id,
        generation_branch="qa-tests/fake",
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
        indexed_commit_sha="abc",
        score=score,
        threshold=threshold,
        findings=findings or [],
    )


def test_approve_commits_pushes_opens_pr_records_then_restores_checkout_in_order() -> None:
    """An approval commits, pushes, opens the PR, records approved, then restores the checkout — in that order."""
    timeline: list = []
    coding_run_id = uuid.uuid4()
    publisher = TimelinePublisher(timeline)
    workspace = TimelineWorkspace(timeline)
    finalizer = DecisionFinalizer(recorder=TimelineRecorder(timeline))

    outcome = _approve(finalizer, publisher, workspace, coding_run_id=coding_run_id)

    assert isinstance(outcome, RunApproved)
    assert outcome.coding_run_id == coding_run_id
    assert outcome.branch == "qa-tests/fake"
    assert outcome.diff.startswith("diff --git")
    # The approval terminal exposes the created Pull Request's URL to the owner.
    assert outcome.pull_request_url == PR_URL
    # The PR is opened from the generation branch.
    assert publisher.pull_request_kwargs["head"] == "qa-tests/fake"
    # Commit precedes push precedes PR precedes record-approved precedes checkout restore.
    assert [step[0] for step in timeline] == ["commit", "push", "open_pull_request", "approve", "discard_generation"]
    assert workspace.discarded == ("abc", "qa-tests/fake")


def test_approve_records_the_pull_request_url_on_the_durable_run() -> None:
    """The created Pull Request URL is handed to the recorder so the durable run carries it for reload."""
    timeline: list = []
    publisher = TimelinePublisher(timeline)
    workspace = TimelineWorkspace(timeline)
    recorder = TimelineRecorder(timeline)
    finalizer = DecisionFinalizer(recorder=recorder)

    _approve(finalizer, publisher, workspace, coding_run_id=uuid.uuid4())

    assert recorder.approved_pull_request_url == PR_URL


def test_approve_renders_the_patch_review_into_the_pull_request_body() -> None:
    """The PR body carries the review score, the configured pass threshold, and the categorized findings."""
    timeline: list = []
    publisher = TimelinePublisher(timeline)
    workspace = TimelineWorkspace(timeline)
    finalizer = DecisionFinalizer(recorder=TimelineRecorder(timeline))
    findings = [
        ReviewFinding(category="coverage", detail="Covers the happy path well."),
        ReviewFinding(category="conventions", detail="Follows the project's pytest style."),
    ]

    _approve(finalizer, publisher, workspace, coding_run_id=uuid.uuid4(), score=9, threshold=7, findings=findings)

    body = publisher.pull_request_kwargs["body"]
    assert "9" in body and "7" in body
    assert "coverage" in body and "Covers the happy path well." in body
    assert "conventions" in body and "Follows the project's pytest style." in body


def test_approve_pull_request_failure_after_push_is_a_github_pull_request_failure(caplog) -> None:
    """A PR creation failure after a successful push is a sanitized github_pull_request Run Failure, never approving or restoring."""
    timeline: list = []
    publisher = TimelinePublisher(timeline, fail_on="pull_request")
    workspace = TimelineWorkspace(timeline)
    finalizer = DecisionFinalizer(recorder=TimelineRecorder(timeline))

    outcome = _approve(finalizer, publisher, workspace, coding_run_id=uuid.uuid4())

    assert isinstance(outcome, RunFailure)
    assert outcome.failed_stage == "github_pull_request"
    # A failed PR yields no approval terminal, so there is no PR URL or branch message to show.
    assert not hasattr(outcome, "pull_request_url")
    # The branch is pushed, but the run is neither approved nor the checkout restored, and the credential never leaks.
    assert publisher.pushed is True
    assert [step[0] for step in timeline] == ["commit", "push"]
    assert workspace.discarded is None
    assert "secret-token" not in outcome.reason
    assert "secret-token" not in caplog.text


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

    outcome = _approve(finalizer, publisher, workspace, coding_run_id=uuid.uuid4())

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

    outcome = _approve(finalizer, publisher, workspace, coding_run_id=uuid.uuid4())

    assert isinstance(outcome, RunFailure)
    assert outcome.failed_stage == "git_push"
    # A failed push yields no approval terminal, so there is no branch-naming message to show.
    assert not hasattr(outcome, "message")
    # The commit happened, but the run is neither approved nor the checkout restored, and the credential is never leaked.
    assert publisher.committed is not None
    assert [step[0] for step in timeline] == ["commit"]
    assert workspace.discarded is None
    assert "secret-token" not in outcome.reason
    assert "secret-token" not in caplog.text
