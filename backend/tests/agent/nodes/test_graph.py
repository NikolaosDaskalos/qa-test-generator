"""Deterministic routing and branch tests for the unified intent-routed graph.

These exercise the compiled ``StateGraph`` through its public ``invoke`` with
fake language models and a fake retriever, so no external model is ever called.
"""

import subprocess
import uuid
from pathlib import Path

from langgraph.types import Command

from app.agent.graph import Classification, build_graph
from app.agent.nodes.planner import PlannerOutput
from app.agent.nodes.repository_question import INSUFFICIENT_EVIDENCE_ANSWER
from app.agent.nodes.test_generation import build_review_patch_node
from app.services.coding_runs.workspace import LocalGitWorkspace
from app.enums.coding_run import CodingRunStage
from app.errors.git_errors import GitError
from app.models.source_document import SourceDocument
from app.schemas.agent_stream import Citation, PatchResult, ReviewResult, RunApproved, RunFailure, RunRejected, RunStarted, Stage
from app.schemas.generation import ExternalReference, GeneratedFile, GenerationProposal
from app.schemas.research_intent import ResearchIntent
from app.schemas.review import PatchReview, ReviewFinding


class FakeClassifierLLM:
    """A structured-output LLM that always classifies to a fixed intent."""

    def __init__(self, intent: str) -> None:
        self._intent = intent
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, _messages):
        return self._schema(intent=self._intent)


class UncertainClassifierLLM:
    """A structured-output LLM that fails to commit to an intent."""

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        return None


class _Chunk:
    """A minimal stand-in for a streamed AIMessageChunk."""

    def __init__(self, content: str) -> None:
        self.content = content


class FakeGeneratorLLM:
    """A chat model that streams a fixed list of token chunks."""

    def __init__(self, tokens=("answer",)) -> None:
        self._tokens = tokens
        self.stream_calls = []

    def stream(self, messages):
        self.stream_calls.append(messages)
        for token in self._tokens:
            yield _Chunk(token)


class FakeRetriever:
    """Return canned Repository Evidence and record retrieval arguments."""

    def __init__(self, evidence=None) -> None:
        self.evidence = evidence or []
        self.calls = []

    def retrieve_evidence(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.evidence


class QueryRetriever:
    """Return evidence keyed by the retrieval query, recording every call."""

    def __init__(self, by_query: dict) -> None:
        self.by_query = by_query
        self.calls = []

    def retrieve_evidence(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.by_query.get(query, [])


class FakePlannerLLM:
    """A structured-output LLM returning a fixed planner result."""

    def __init__(self, output) -> None:
        self._output = output

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        return self._output


class RecordingRecorder:
    """Record Coding Run lifecycle calls made by the test-generation branch."""

    def __init__(self) -> None:
        self.events = []
        self.run_id = uuid.uuid4()

    def start(self, *, thread_id, repository_session_id):
        self.events.append(("start", thread_id, repository_session_id))
        return self.run_id

    def begin_planning(self, coding_run_id):
        self.events.append(("begin_planning", coding_run_id))

    def begin_retrieving(self, coding_run_id):
        self.events.append(("begin_retrieving", coding_run_id))

    def begin_generating(self, coding_run_id):
        self.events.append(("begin_generating", coding_run_id))

    def begin_reviewing(self, coding_run_id):
        self.events.append(("begin_reviewing", coding_run_id))

    def fail(self, coding_run_id, *, failed_stage, reason):
        self.events.append(("fail", coding_run_id, failed_stage, reason))

    def complete(self, coding_run_id, *, branch, diff, generated_files, external_references):
        self.events.append(("complete", coding_run_id, branch, diff, generated_files, external_references))

    def record_review(self, coding_run_id, *, accepted, findings):
        self.events.append(("record_review", coding_run_id, accepted, findings))

    def reject(self, coding_run_id):
        self.events.append(("reject", coding_run_id))

    def approve(self, coding_run_id):
        self.events.append(("approve", coding_run_id))


class FakeGenerator:
    """A ``TestGenerator`` returning a fixed proposal and recording its inputs.

    When a ``revision`` proposal is supplied it is returned by ``revise``; the
    revise inputs (prior proposal, canonical diff, reviewer findings) are recorded.
    """

    def __init__(self, proposal: GenerationProposal | None = None, *, revision: GenerationProposal | None = None) -> None:
        self.proposal = proposal or GenerationProposal()
        self.revision = revision
        self.calls = []
        self.revise_calls = []

    def generate(self, *, task, source_evidence, test_evidence):
        self.calls.append({"task": task, "source_evidence": source_evidence, "test_evidence": test_evidence})
        return self.proposal

    def revise(self, *, task, source_evidence, test_evidence, prior_files, diff, findings):
        self.revise_calls.append(
            {"task": task, "source_evidence": source_evidence, "test_evidence": test_evidence, "prior_files": prior_files, "diff": diff, "findings": findings}
        )
        return self.revision if self.revision is not None else self.proposal


class RaisingGenerator:
    """A ``TestGenerator`` that fails to produce a proposal."""

    def generate(self, *, task, source_evidence, test_evidence):
        raise RuntimeError("model unavailable")


class FakeReviewer:
    """A ``PatchReviewer`` returning fixed decisions and recording its inputs.

    A single ``review`` is returned on every call; a ``reviews`` sequence returns
    one decision per call (clamped to the last), so first-review and second-review
    verdicts can differ across a Revision Attempt.
    """

    def __init__(self, review: PatchReview | None = None, *, reviews: list[PatchReview] | None = None) -> None:
        if reviews is not None:
            self._reviews = list(reviews)
        else:
            self._reviews = [review if review is not None else PatchReview(score=10, findings=[])]
        self.calls = []

    def review(self, *, task, source_evidence, test_evidence, generated_files, diff):
        self.calls.append({"task": task, "source_evidence": source_evidence, "test_evidence": test_evidence, "generated_files": generated_files, "diff": diff})
        index = min(len(self.calls) - 1, len(self._reviews) - 1)
        return self._reviews[index]


class RaisingReviewer:
    """A ``PatchReviewer`` whose model/tool loop fails to produce a decision."""

    def review(self, *, task, source_evidence, test_evidence, generated_files, diff):
        raise RuntimeError("reviewer model unavailable")


class FakeWorkspace:
    """A ``GenerationWorkspace`` that records writes and returns a canned diff."""

    def __init__(self, diff: str = "") -> None:
        self._diff = diff
        self.prepared_from = None
        self.written = None
        self.reset_count = 0
        self.discarded = None

    def prepare_branch(self, indexed_commit_sha):
        self.prepared_from = indexed_commit_sha
        return "qa-tests/fake"

    def reset_patch_state(self):
        self.reset_count += 1

    def discard_generation(self, indexed_commit_sha, branch):
        self.discarded = (indexed_commit_sha, branch)

    def write_test_files(self, files):
        self.written = files

    def diff(self):
        return self._diff


class FakePublisher:
    """A ``PatchPublisher`` that records the commit/push and can fail either step.

    ``fail_on`` raises a ``GitError`` (whose text embeds a stand-in credential, so
    sanitization can be asserted) on the named step — ``"commit"`` or ``"push"``.
    """

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.committed = None
        self.pushed = False
        self._fail_on = fail_on

    def commit(self, message):
        if self._fail_on == "commit":
            raise GitError("git commit failed for secret-token")
        self.committed = message

    def push(self):
        if self._fail_on == "push":
            raise GitError("git push rejected for secret-token")
        self.pushed = True


def _workspace_factory(workspace=None):
    workspace = workspace or FakeWorkspace()
    return lambda _checkout_root: workspace


def _publisher_factory(publisher=None):
    publisher = publisher or FakePublisher()
    return lambda _repository_id: publisher


def _source(repository_id: uuid.UUID, source: str, content: str = "evidence") -> SourceDocument:
    return SourceDocument(repository_id=repository_id, content=content, doc_metadata={"source": source})


def _config(thread_id: str = "t1") -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def _init_repo_with_test_root(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Tester")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_existing.py").write_text("def test_existing():\n    assert True\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "indexed")
    return repo, _git(repo, "rev-parse", "HEAD")


def _build(classifier_llm, *, retriever=None, llm=None, planner_llm=None, recorder=None, generator=None, workspace=None, reviewer=None, publisher=None):
    return build_graph(
        classifier_llm=classifier_llm,
        retriever=retriever if retriever is not None else FakeRetriever(),
        llm=llm if llm is not None else FakeGeneratorLLM(),
        planner_llm=planner_llm if planner_llm is not None else FakePlannerLLM(PlannerOutput(in_scope=True, intents=[])),
        generator=generator if generator is not None else FakeGenerator(),
        reviewer=reviewer if reviewer is not None else FakeReviewer(),
        run_recorder=recorder,
        workspace_factory=_workspace_factory(workspace),
        publisher_factory=_publisher_factory(publisher),
    )


# ── Routing ───────────────────────────────────────────────────────


def test_structured_output_models_describe_all_llm_fields() -> None:
    """Structured LLM schemas carry field descriptions for better model guidance."""
    structured_output_models = [Classification, PlannerOutput, ResearchIntent]

    for model in structured_output_models:
        properties = model.model_json_schema()["properties"]
        assert properties
        assert all(property_schema.get("description") for property_schema in properties.values())


def test_graph_routes_test_generation_intent_to_the_test_branch() -> None:
    """A test-generation classification enters the planning branch, not retrieval-first."""
    graph = _build(FakeClassifierLLM("test_generation"))

    final = graph.invoke({"question": "now write tests for the auth module", "repository_id": uuid.uuid4()}, config=_config())

    assert final["intent"] == "test_generation"
    assert final["trace"][0] == "classify"
    assert "plan" in final["trace"]
    assert "retrieve" not in final["trace"]


def test_graph_routes_repository_question_intent_to_the_retrieval_branch() -> None:
    """A repository-question classification skips planning and retrieves first."""
    graph = _build(FakeClassifierLLM("repository_question"))

    final = graph.invoke({"question": "how does the auth module work?", "repository_id": uuid.uuid4()}, config=_config())

    assert final["intent"] == "repository_question"
    assert final["trace"][:2] == ["classify", "retrieve"]


def test_uncertain_classification_falls_back_to_the_repository_question_branch() -> None:
    """When the classifier cannot commit, the graph takes the read-only branch."""
    graph = _build(UncertainClassifierLLM())

    final = graph.invoke({"question": "do something ambiguous", "repository_id": uuid.uuid4()}, config=_config())

    assert final["intent"] == "repository_question"
    assert final["trace"][:2] == ["classify", "retrieve"]


# ── repository_question branch ────────────────────────────────────


def test_repository_question_branch_answers_from_retrieved_evidence() -> None:
    """The retrieve → generate branch grounds an answer and emits de-duplicated citations."""
    repository_id = uuid.uuid4()
    retriever = FakeRetriever(
        [
            _source(repository_id, "app/auth.py", "auth code"),
            _source(repository_id, "app/auth.py", "more auth code"),
            _source(repository_id, "app/login.py", "login code"),
        ]
    )
    graph = _build(FakeClassifierLLM("repository_question"), retriever=retriever, llm=FakeGeneratorLLM(("the ", "answer")))

    final = graph.invoke({"question": "how is auth tested?", "repository_id": repository_id}, config=_config())

    assert retriever.calls[-1][0] == "how is auth tested?"
    assert retriever.calls[-1][1]["repository_id"] == repository_id
    assert final["answer"] == "the answer"
    assert final["citations"] == [Citation(source="app/auth.py"), Citation(source="app/login.py")]


def test_repository_question_branch_reports_insufficient_evidence_without_calling_the_model() -> None:
    """Empty Repository Evidence yields a deterministic answer and never streams the model."""
    repository_id = uuid.uuid4()
    llm = FakeGeneratorLLM(("unused",))
    graph = _build(FakeClassifierLLM("repository_question"), retriever=FakeRetriever([]), llm=llm)

    final = graph.invoke({"question": "anything", "repository_id": repository_id}, config=_config())

    assert final["answer"] == INSUFFICIENT_EVIDENCE_ANSWER
    assert final["citations"] == []
    assert llm.stream_calls == []


# ── test_generation branch: planning ──────────────────────────────


def test_planner_emits_research_intents_tagged_source_and_test() -> None:
    """An in-scope task plans evidence to find, tagged source vs. test, with candidate path hints."""
    planner_output = PlannerOutput(
        in_scope=True,
        intents=[
            ResearchIntent(target="source", description="auth login implementation", candidate_paths=["app/auth.py"]),
            ResearchIntent(target="test", description="existing auth tests", candidate_paths=["tests/test_auth.py"]),
        ],
    )
    graph = _build(FakeClassifierLLM("test_generation"), planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke({"question": "add tests for the auth module", "repository_id": uuid.uuid4()}, config=_config())

    assert final.get("failure") is None
    intents = final["research_intents"]
    assert [intent.target for intent in intents] == ["source", "test"]
    assert intents[0].candidate_paths == ["app/auth.py"]


def test_out_of_scope_task_is_rejected_at_the_planning_stage() -> None:
    """A request outside adding or improving tests fails at planning before any retrieval."""
    planner_output = PlannerOutput(in_scope=False, reason="This asks to refactor production code, not to add or improve tests.")
    graph = _build(FakeClassifierLLM("test_generation"), planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke({"question": "rename the auth module everywhere", "repository_id": uuid.uuid4()}, config=_config())

    failure = final["failure"]
    assert failure.failed_stage == "planning"
    assert failure.reason == "This asks to refactor production code, not to add or improve tests."
    assert not final.get("research_intents")


# ── test_generation branch: generic retrieve ──────────────────────


def test_test_generation_retrieve_partitions_source_and_test_evidence() -> None:
    """Planner intents are executed under the session's Repository and split source vs. test."""
    repository_id = uuid.uuid4()
    retriever = QueryRetriever(
        {"auth implementation": [_source(repository_id, "app/auth.py", "impl")], "auth tests": [_source(repository_id, "tests/test_auth.py", "test")]}
    )
    planner_output = PlannerOutput(
        in_scope=True, intents=[ResearchIntent(target="source", description="auth implementation"), ResearchIntent(target="test", description="auth tests")]
    )
    graph = _build(FakeClassifierLLM("test_generation"), retriever=retriever, planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke({"question": "add tests for auth", "repository_id": repository_id}, config=_config())

    assert [doc.doc_metadata["source"] for doc in final["source_evidence"]] == ["app/auth.py"]
    assert [doc.doc_metadata["source"] for doc in final["test_evidence"]] == ["tests/test_auth.py"]
    assert all(call[1]["repository_id"] == repository_id for call in retriever.calls)


def test_test_generation_retrieve_yields_empty_partitions_when_no_evidence() -> None:
    """When retrieval finds nothing, both evidence partitions are present and empty."""
    planner_output = PlannerOutput(in_scope=True, intents=[ResearchIntent(target="source", description="nothing here")])
    graph = _build(FakeClassifierLLM("test_generation"), retriever=FakeRetriever([]), planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke({"question": "add tests", "repository_id": uuid.uuid4()}, config=_config())

    assert final["source_evidence"] == []
    assert final["test_evidence"] == []


def test_test_generation_retrieve_confines_candidate_paths_to_validated_hints(tmp_path) -> None:
    """Untrusted candidate paths are confined to the checkout; unsafe ones never proceed."""
    repository_id = uuid.uuid4()
    planner_output = PlannerOutput(
        in_scope=True, intents=[ResearchIntent(target="source", description="auth", candidate_paths=["app/auth.py", "/etc/passwd", "../escape"])]
    )
    graph = _build(FakeClassifierLLM("test_generation"), retriever=FakeRetriever([]), planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke({"question": "add tests", "repository_id": repository_id, "checkout_root": str(tmp_path)}, config=_config())

    assert final["candidate_hints"] == ["app/auth.py"]


# ── test_generation branch: Coding Run persistence ────────────────


def test_test_generation_persists_a_queued_run_and_advances_through_generation() -> None:
    """A routed task creates a Coding Run and advances it planning → retrieving → generating → complete."""
    recorder = RecordingRecorder()
    session_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    planner_output = PlannerOutput(in_scope=True, intents=[ResearchIntent(target="source", description="x")])
    graph = _build(FakeClassifierLLM("test_generation"), recorder=recorder, planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke(
        {"question": "add tests", "repository_id": repository_id, "repository_session_id": session_id, "checkout_root": "/unused"}, config=_config("run-thread")
    )

    assert [event[0] for event in recorder.events] == [
        "start",
        "begin_planning",
        "begin_retrieving",
        "begin_generating",
        "complete",
        "begin_reviewing",
        "record_review",
    ]
    assert recorder.events[0] == ("start", "run-thread", session_id)
    assert recorder.events[4][1] == recorder.run_id
    assert final["coding_run_id"] == recorder.run_id


def test_test_generation_marks_failure_at_planning_when_out_of_scope() -> None:
    """A rejected task records a planning failure and stops before retrieving."""
    recorder = RecordingRecorder()
    planner_output = PlannerOutput(in_scope=False, reason="Not a test request")
    graph = _build(FakeClassifierLLM("test_generation"), recorder=recorder, planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke({"question": "refactor", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4()}, config=_config())

    assert [event[0] for event in recorder.events] == ["start", "begin_planning", "fail"]
    assert recorder.events[2][2] == CodingRunStage.planning
    assert recorder.events[2][3] == "Not a test request"
    assert final["failure"].coding_run_id == recorder.run_id


# ── test_generation branch: generation & patch ────────────────────


def _generation_graph(*, generator, recorder=None, workspace=None, reviewer=None, publisher=None):
    planner_output = PlannerOutput(in_scope=True, intents=[ResearchIntent(target="source", description="x")])
    return _build(
        FakeClassifierLLM("test_generation"),
        recorder=recorder,
        planner_llm=FakePlannerLLM(planner_output),
        generator=generator,
        workspace=workspace,
        reviewer=reviewer,
        publisher=publisher,
    )


def test_generator_receives_partitioned_evidence_and_emits_structured_files() -> None:
    """The generator is handed the task and partitioned evidence and returns complete-file proposals."""
    repository_id = uuid.uuid4()
    retriever = QueryRetriever({"impl": [_source(repository_id, "app/auth.py", "code")]})
    planner_output = PlannerOutput(in_scope=True, intents=[ResearchIntent(target="source", description="impl")])
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    graph = _build(FakeClassifierLLM("test_generation"), retriever=retriever, planner_llm=FakePlannerLLM(planner_output), generator=generator)

    final = graph.invoke({"question": "add tests for auth", "repository_id": repository_id, "checkout_root": "/unused"}, config=_config())

    assert generator.calls[0]["task"] == "add tests for auth"
    assert [doc.doc_metadata["source"] for doc in generator.calls[0]["source_evidence"]] == ["app/auth.py"]
    assert [file.path for file in final["generated_files"]] == ["tests/test_auth.py"]


def test_external_references_are_collected_separately_from_repository_evidence() -> None:
    """Web results ride external_references, never mixed into source or test evidence."""
    repository_id = uuid.uuid4()
    generator = FakeGenerator(
        GenerationProposal(
            generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")],
            external_references=[ExternalReference(url="https://docs.pytest.org", title="pytest")],
        )
    )
    graph = _generation_graph(generator=generator)

    final = graph.invoke({"question": "add tests", "repository_id": repository_id, "checkout_root": "/unused"}, config=_config())

    assert [reference.url for reference in final["external_references"]] == ["https://docs.pytest.org"]
    assert all("docs.pytest.org" not in doc.content for doc in final.get("source_evidence", []))
    assert all("docs.pytest.org" not in doc.content for doc in final.get("test_evidence", []))


def test_build_patch_writes_validated_files_and_emits_a_patch_result(tmp_path) -> None:
    """Validated proposals are written, the diff is derived, and the run is completed with it."""
    (tmp_path / "tests").mkdir()  # an existing test root admits the new test file
    recorder = RecordingRecorder()
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_x(): ...")
    files = [GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]
    references = [ExternalReference(url="https://docs.pytest.org", title="pytest")]
    generator = FakeGenerator(GenerationProposal(generated_files=files, external_references=references))
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace)

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    assert workspace.prepared_from == "abc"
    assert [file.path for file in workspace.written] == ["tests/test_auth.py"]
    patch_result = final["patch_result"]
    assert isinstance(patch_result, PatchResult)
    assert patch_result.coding_run_id == recorder.run_id
    assert patch_result.diff == workspace.diff()
    assert [file.path for file in patch_result.generated_files] == ["tests/test_auth.py"]
    complete = next(event for event in recorder.events if event[0] == "complete")
    assert complete[2] == "qa-tests/fake"  # branch
    assert complete[3] == workspace.diff()


def test_unsafe_proposed_path_is_rejected_before_writing_as_a_generating_failure(tmp_path) -> None:
    """A proposal replacing an existing application file fails at generating and is never written."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text("real code")
    recorder = RecordingRecorder()
    workspace = FakeWorkspace()
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="app/auth.py", content="malicious")]))
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace)

    final = graph.invoke(
        {"question": "add tests", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4(), "checkout_root": str(tmp_path)}, config=_config()
    )

    assert final["failure"].failed_stage == "generating"
    assert final.get("patch_result") is None
    assert workspace.written is None
    assert recorder.events[-1][0] == "fail"


def test_new_test_file_without_an_existing_test_root_is_rejected_before_writing(tmp_path) -> None:
    """build_patch discovers test roots; a new test-named file with none fails and is never written."""
    recorder = RecordingRecorder()
    workspace = FakeWorkspace()
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace)

    final = graph.invoke(
        {"question": "add tests", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4(), "checkout_root": str(tmp_path)}, config=_config()
    )

    assert final["failure"].failed_stage == "generating"
    assert final.get("patch_result") is None
    assert workspace.written is None


def test_repository_question_never_reaches_the_web_search_generator() -> None:
    """The web-search-capable generator is unreachable from a read-only repository question."""
    repository_id = uuid.uuid4()
    generator = FakeGenerator()
    graph = _build(
        FakeClassifierLLM("repository_question"),
        retriever=FakeRetriever([_source(repository_id, "app/a.py", "x")]),
        llm=FakeGeneratorLLM(("a",)),
        generator=generator,
    )

    graph.invoke({"question": "how does auth work?", "repository_id": repository_id}, config=_config())

    assert generator.calls == []


def test_generation_failure_is_a_generating_run_failure() -> None:
    """A generator that cannot produce a proposal fails the run at the generating stage."""
    recorder = RecordingRecorder()
    graph = _generation_graph(generator=RaisingGenerator(), recorder=recorder)

    final = graph.invoke(
        {"question": "add tests", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4(), "checkout_root": "/unused"}, config=_config()
    )

    assert final["failure"].failed_stage == "generating"
    assert final["failure"].coding_run_id == recorder.run_id
    assert final.get("patch_result") is None


# ── test_generation branch: patch review ──────────────────────────


def _reviewed_graph(*, reviewer, recorder=None, files=None, diff="diff --git a/tests/test_auth.py b/tests/test_auth.py"):
    files = files if files is not None else [GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]
    generator = FakeGenerator(GenerationProposal(generated_files=files))
    return _generation_graph(generator=generator, recorder=recorder, workspace=FakeWorkspace(diff=diff), reviewer=reviewer)


def test_accepted_review_advances_to_awaiting_approval_and_emits_review_result(tmp_path) -> None:
    """An accepted first review records an accepted review and emits a ReviewResult carrying the final diff."""
    (tmp_path / "tests").mkdir()  # an existing test root so the proposal validates
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    diff = "diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_x(): ..."
    graph = _reviewed_graph(reviewer=reviewer, recorder=recorder, diff=diff)

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    review = final["review_result"]
    assert isinstance(review, ReviewResult)
    assert review.accepted is True
    assert review.coding_run_id == recorder.run_id
    assert review.diff == diff
    # User-visible output states tests were not executed and runtime correctness was not verified.
    assert "not executed" in review.disclaimer.lower()
    # The run advanced into reviewing and recorded an accepted review decision.
    assert ("begin_reviewing", recorder.run_id) in recorder.events
    record = next(event for event in recorder.events if event[0] == "record_review")
    assert record[2] is True


def test_reviewer_receives_the_task_partitioned_evidence_proposals_and_diff(tmp_path) -> None:
    """Review is invoked with the task, Repository Evidence (source/test), the proposals, and the canonical diff."""
    (tmp_path / "tests").mkdir()
    repository_id = uuid.uuid4()
    retriever = QueryRetriever(
        {"auth implementation": [_source(repository_id, "app/auth.py", "impl")], "auth tests": [_source(repository_id, "tests/test_auth.py", "existing test")]}
    )
    planner_output = PlannerOutput(
        in_scope=True, intents=[ResearchIntent(target="source", description="auth implementation"), ResearchIntent(target="test", description="auth tests")]
    )
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    files = [GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]
    generator = FakeGenerator(GenerationProposal(generated_files=files))
    diff = "diff --git a/tests/test_auth.py b/tests/test_auth.py"
    graph = _build(
        FakeClassifierLLM("test_generation"),
        retriever=retriever,
        planner_llm=FakePlannerLLM(planner_output),
        generator=generator,
        workspace=FakeWorkspace(diff=diff),
        reviewer=reviewer,
    )

    graph.invoke(
        {"question": "add tests for auth", "repository_id": repository_id, "checkout_root": str(tmp_path), "indexed_commit_sha": "abc"}, config=_config()
    )

    call = reviewer.calls[0]
    assert call["task"] == "add tests for auth"
    assert [doc.doc_metadata["source"] for doc in call["source_evidence"]] == ["app/auth.py"]
    assert [doc.doc_metadata["source"] for doc in call["test_evidence"]] == ["tests/test_auth.py"]
    assert [file.path for file in call["generated_files"]] == ["tests/test_auth.py"]
    assert call["diff"] == diff


def test_accepted_review_pauses_for_a_human_decision(tmp_path) -> None:
    """An accepted review suspends the run at a human-decision interrupt carrying the patch and findings."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    findings = [ReviewFinding(category="readability", detail="clear and idiomatic")]
    reviewer = FakeReviewer(PatchReview(score=10, findings=findings))
    diff = "diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_x(): ..."
    graph = _reviewed_graph(reviewer=reviewer, recorder=recorder, diff=diff)
    config = _config()

    result = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=config,
    )

    # The graph paused at the human-decision interrupt instead of ending the run.
    assert "__interrupt__" in result
    prompt = result["__interrupt__"][0].value
    assert prompt["coding_run_id"] == recorder.run_id
    assert prompt["diff"] == diff
    assert [finding["category"] for finding in prompt["findings"]] == ["readability"]
    # The accepted review is recorded (awaiting approval); no rejection has happened yet.
    assert ("record_review", recorder.run_id, True, findings) in recorder.events
    assert ("reject", recorder.run_id) not in recorder.events
    # The run is suspended at the decision node, ready to resume.
    assert graph.get_state(config).next == ("await_decision",)


def test_accepted_review_stream_emits_its_review_result(tmp_path) -> None:
    """An accepted Patch Review owns the terminal event emitted before the HITL pause."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    diff = "diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_x(): ..."
    graph = _reviewed_graph(reviewer=reviewer, recorder=recorder, diff=diff)

    events = _custom_events(
        graph,
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
    )

    reviews = [event for event in events if isinstance(event, ReviewResult)]
    assert len(reviews) == 1
    assert reviews[0].coding_run_id == recorder.run_id
    assert reviews[0].accepted is True
    assert reviews[0].diff == diff


def test_rejecting_a_paused_run_discards_the_patch_and_records_the_rejection(tmp_path) -> None:
    """Resuming a paused run with a rejection restores the checkout, removes the branch, and records the rejection."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    findings = [ReviewFinding(category="readability", detail="clear and idiomatic")]
    reviewer = FakeReviewer(PatchReview(score=10, findings=findings))
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_x(): ...")
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer)
    config = _config()
    graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=config,
    )

    final = graph.invoke(Command(resume={"approved": False}), config=config)

    # The discarded patch restores the checkout to the indexed commit and removes the temporary branch.
    assert workspace.discarded == ("abc", "qa-tests/fake")
    # The run is recorded rejected, after the accepted review was recorded.
    assert ("reject", recorder.run_id) in recorder.events
    # The terminal outcome preserves the assessed diff and findings for inspection.
    rejection = final["rejection_result"]
    assert isinstance(rejection, RunRejected)
    assert rejection.coding_run_id == recorder.run_id
    assert rejection.diff.startswith("diff --git")
    assert [finding.category for finding in rejection.findings] == ["readability"]
    assert "not executed" in rejection.disclaimer.lower()
    assert final.get("failure") is None


def test_rejecting_a_paused_run_stream_emits_run_rejected(tmp_path) -> None:
    """The discard node owns the rejection terminal event on the resume stream."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    findings = [ReviewFinding(category="readability", detail="clear and idiomatic")]
    reviewer = FakeReviewer(PatchReview(score=10, findings=findings))
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_x(): ...")
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer)
    config = _config()
    graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=config,
    )

    events = [chunk for _mode, chunk in graph.stream(Command(resume={"approved": False}), config=config, stream_mode=["custom"])]

    rejections = [event for event in events if isinstance(event, RunRejected)]
    assert len(rejections) == 1
    assert rejections[0].coding_run_id == recorder.run_id
    assert [finding.category for finding in rejections[0].findings] == ["readability"]


def test_approving_a_paused_run_commits_pushes_and_emits_run_approved(tmp_path) -> None:
    """Resuming with an approval commits and pushes the reviewed patch and ends in a RunApproved."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py")
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    publisher = FakePublisher()
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer, publisher=publisher)
    config = _config()
    graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=config,
    )

    final = graph.invoke(Command(resume={"approved": True}), config=config)

    # The reviewed patch was committed and its branch pushed.
    assert publisher.committed is not None
    assert publisher.pushed is True
    # The terminal outcome identifies the approved run and is not a rejection or failure.
    approval = final["approval_result"]
    assert isinstance(approval, RunApproved)
    assert approval.coding_run_id == recorder.run_id
    assert final.get("rejection_result") is None
    assert final.get("failure") is None


def test_approving_a_paused_run_stream_emits_run_approved(tmp_path) -> None:
    """The approval node owns the approval terminal event on the resume stream."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py")
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    publisher = FakePublisher()
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer, publisher=publisher)
    config = _config()
    graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=config,
    )

    events = [chunk for _mode, chunk in graph.stream(Command(resume={"approved": True}), config=config, stream_mode=["custom"])]

    approvals = [event for event in events if isinstance(event, RunApproved)]
    assert len(approvals) == 1
    assert approvals[0].coding_run_id == recorder.run_id
    assert approvals[0].branch == "qa-tests/fake"


def test_approval_records_the_run_and_restores_the_checkout_to_the_indexed_commit(tmp_path) -> None:
    """After pushing, approval records the run approved and restores the checkout, removing the local branch."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py")
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    publisher = FakePublisher()
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer, publisher=publisher)
    config = _config()
    graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=config,
    )

    final = graph.invoke(Command(resume={"approved": True}), config=config)

    # The run is recorded approved, after the accepted review was recorded.
    assert ("approve", recorder.run_id) in recorder.events
    assert ("reject", recorder.run_id) not in recorder.events
    # The local checkout is restored to the indexed commit and the temporary branch removed.
    assert workspace.discarded == ("abc", "qa-tests/fake")
    assert final["approval_result"].branch == "qa-tests/fake"


def test_approval_commit_failure_is_a_git_commit_stage_failure(tmp_path, caplog) -> None:
    """A commit that fails records a git_commit-stage failure, never pushes, and does not approve."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py")
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    publisher = FakePublisher(fail_on="commit")
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer, publisher=publisher)
    config = _config()
    graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=config,
    )

    final = graph.invoke(Command(resume={"approved": True}), config=config)

    failure = final["failure"]
    assert failure.failed_stage == "git_commit"
    assert failure.coding_run_id == recorder.run_id
    # The patch was never pushed and the run was never approved; the failure is sanitized.
    assert publisher.pushed is False
    assert ("approve", recorder.run_id) not in recorder.events
    assert final.get("approval_result") is None
    assert "secret-token" not in failure.reason
    assert "secret-token" not in caplog.text


def test_approval_push_failure_is_a_git_push_stage_failure(tmp_path, caplog) -> None:
    """A push that fails after a successful commit records a git_push-stage failure with a sanitized reason."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py")
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    publisher = FakePublisher(fail_on="push")
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer, publisher=publisher)
    config = _config()
    graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=config,
    )

    final = graph.invoke(Command(resume={"approved": True}), config=config)

    failure = final["failure"]
    assert failure.failed_stage == "git_push"
    assert failure.coding_run_id == recorder.run_id
    # The commit happened but the run was not approved, and the credential is never leaked.
    assert publisher.committed is not None
    assert ("approve", recorder.run_id) not in recorder.events
    assert final.get("approval_result") is None
    assert "secret-token" not in failure.reason
    assert "secret-token" not in caplog.text


def test_rejected_first_review_records_its_findings_before_revising(tmp_path) -> None:
    """A first rejection persists its findings as a recorded review and routes onward to a Revision Attempt, not a failure."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    findings = [ReviewFinding(category="imports", detail="imports a helper not visible in Repository Evidence")]
    reviewer = FakeReviewer(reviews=[PatchReview(score=3, findings=findings), PatchReview(score=10, findings=[])])
    graph = _reviewed_graph(reviewer=reviewer, recorder=recorder)

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    # The first rejection is recorded with its findings; it is a deliberate review outcome, not a RunFailure.
    first_record = next(event for event in recorder.events if event[0] == "record_review")
    assert first_record[2] is False
    assert [finding.category for finding in first_record[3]] == ["imports"]
    assert final.get("failure") is None


def test_review_rejects_a_patch_with_changes_unrelated_to_the_task(tmp_path) -> None:
    """The reviewer rejects a patch that introduces changes unrelated to the Test-Generation Task."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    findings = [ReviewFinding(category="scope", detail="adds an unrelated test unrelated to the requested task")]
    reviewer = FakeReviewer(reviews=[PatchReview(score=3, findings=findings), PatchReview(score=10, findings=[])])
    graph = _reviewed_graph(reviewer=reviewer, recorder=recorder)

    graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    # The reviewer's rejection of the unrelated change is recorded with its finding.
    record = next(event for event in recorder.events if event[0] == "record_review")
    assert record[2] is False
    assert any("unrelated" in finding.detail for finding in record[3])


def _review_state(tmp_path, recorder):
    return {
        "coding_run_id": recorder.run_id,
        "question": "add tests",
        "checkout_root": str(tmp_path),
        "diff": "diff --git a/tests/test_auth.py b/tests/test_auth.py",
        "generated_files": [GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")],
    }


def test_score_above_threshold_is_accepted_by_the_backend(tmp_path) -> None:
    """The backend, not the model, decides the pass: a score above the threshold is accepted."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    node = build_review_patch_node(FakeReviewer(PatchReview(score=8, findings=[])), recorder, threshold=7)

    result = node(_review_state(tmp_path, recorder))

    assert result["review_result"].accepted is True
    record = next(event for event in recorder.events if event[0] == "record_review")
    assert record[2] is True


def test_score_at_threshold_is_accepted_by_the_backend(tmp_path) -> None:
    """A score exactly at the threshold passes: the pass bar is ``score >= threshold``."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    node = build_review_patch_node(FakeReviewer(PatchReview(score=7, findings=[])), recorder, threshold=7)

    result = node(_review_state(tmp_path, recorder))

    assert result["review_result"].accepted is True


def test_score_below_threshold_is_not_accepted_by_the_backend(tmp_path) -> None:
    """A score under the threshold fails the pass decision, leaving routing to request a revision."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    node = build_review_patch_node(FakeReviewer(PatchReview(score=6, findings=[])), recorder, threshold=7)

    result = node(_review_state(tmp_path, recorder))

    assert result["review_result"].accepted is False
    record = next(event for event in recorder.events if event[0] == "record_review")
    assert record[2] is False


def test_review_result_carries_the_score_and_the_threshold_it_was_judged_against(tmp_path) -> None:
    """The ReviewResult surfaces the reviewer's score and the threshold the backend judged it against."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    node = build_review_patch_node(FakeReviewer(PatchReview(score=8, findings=[])), recorder, threshold=7)

    review = node(_review_state(tmp_path, recorder))["review_result"]

    assert review.score == 8
    assert review.threshold == 7


def test_backend_independently_rejects_out_of_scope_files_even_when_the_score_passes(tmp_path) -> None:
    """The score is never the sole gate: a Test File boundary escape rejects a passing-score patch."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text("real application code")
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=10, findings=[]))
    node = build_review_patch_node(reviewer, recorder, threshold=7)
    state = {
        "coding_run_id": recorder.run_id,
        "question": "add tests",
        "checkout_root": str(tmp_path),
        "diff": "diff --git a/app/auth.py b/app/auth.py",
        "generated_files": [GeneratedFile(path="app/auth.py", content="malicious")],
    }

    result = node(state)

    review = result["review_result"]
    assert review.accepted is False
    assert any(finding.category == "scope" for finding in review.findings)
    record = next(event for event in recorder.events if event[0] == "record_review")
    assert record[2] is False


def test_reviewer_failure_is_a_reviewing_run_failure(tmp_path) -> None:
    """A reviewer that raises records a reviewing-stage failure instead of leaving the run stuck."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    graph = _reviewed_graph(reviewer=RaisingReviewer(), recorder=recorder)

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    assert final["failure"].failed_stage == "reviewing"
    assert final["failure"].coding_run_id == recorder.run_id
    assert final.get("review_result") is None
    # The run advanced into reviewing and then recorded the failure; it is never left without one.
    assert ("begin_reviewing", recorder.run_id) in recorder.events
    fail = next(event for event in recorder.events if event[0] == "fail")
    assert fail[2] == "reviewing"
    # A reviewer crash is sanitized, never leaking raw exception text.
    assert "unavailable" not in final["failure"].reason


def test_reviewer_failure_stream_emits_run_failure(tmp_path) -> None:
    """The failure node owns the reviewing-stage RunFailure terminal event."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    graph = _reviewed_graph(reviewer=RaisingReviewer(), recorder=recorder)

    events = _custom_events(
        graph,
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
    )

    failures = [event for event in events if isinstance(event, RunFailure)]
    assert len(failures) == 1
    assert failures[0].coding_run_id == recorder.run_id
    assert failures[0].failed_stage == "reviewing"


# ── test_generation branch: bounded revision ──────────────────────


def test_first_rejection_triggers_one_revision_that_is_accepted(tmp_path) -> None:
    """A rejected first review routes through one Revision Attempt; an accepted second review reaches awaiting approval."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    findings = [ReviewFinding(category="coverage", detail="missing unhappy-path test")]
    reviewer = FakeReviewer(reviews=[PatchReview(score=3, findings=findings), PatchReview(score=10, findings=[])])
    revised = GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...\ndef test_y(): ...")])
    generator = FakeGenerator(
        GenerationProposal(
            generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")],
            external_references=[ExternalReference(url="https://docs.pytest.org", title="pytest")],
        ),
        revision=revised,
    )
    graph = _generation_graph(
        generator=generator, recorder=recorder, workspace=FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py"), reviewer=reviewer
    )

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    # Exactly one revision happened and the second review accepted the revised patch.
    assert len(generator.revise_calls) == 1
    assert final["review_result"].accepted is True
    assert final.get("failure") is None
    assert [reference.url for reference in final["external_references"]] == ["https://docs.pytest.org"]
    # Two reviews were recorded in order: the rejection, then the acceptance.
    review_records = [event for event in recorder.events if event[0] == "record_review"]
    assert [record[2] for record in review_records] == [False, True]


def test_revision_receives_the_task_evidence_prior_proposal_diff_and_findings(tmp_path) -> None:
    """The Revision Attempt is handed the original task, partitioned evidence, its prior proposal, the canonical diff, and the findings."""
    (tmp_path / "tests").mkdir()
    repository_id = uuid.uuid4()
    retriever = QueryRetriever(
        {"auth implementation": [_source(repository_id, "app/auth.py", "impl")], "auth tests": [_source(repository_id, "tests/test_auth.py", "existing test")]}
    )
    planner_output = PlannerOutput(
        in_scope=True, intents=[ResearchIntent(target="source", description="auth implementation"), ResearchIntent(target="test", description="auth tests")]
    )
    findings = [ReviewFinding(category="coverage", detail="missing unhappy-path test")]
    reviewer = FakeReviewer(reviews=[PatchReview(score=3, findings=findings), PatchReview(score=10, findings=[])])
    prior = GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")
    generator = FakeGenerator(
        GenerationProposal(generated_files=[prior]),
        revision=GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...\ndef test_y(): ...")]),
    )
    diff = "diff --git a/tests/test_auth.py b/tests/test_auth.py"
    graph = _build(
        FakeClassifierLLM("test_generation"),
        retriever=retriever,
        planner_llm=FakePlannerLLM(planner_output),
        generator=generator,
        workspace=FakeWorkspace(diff=diff),
        reviewer=reviewer,
    )

    graph.invoke(
        {"question": "add tests for auth", "repository_id": repository_id, "checkout_root": str(tmp_path), "indexed_commit_sha": "abc"}, config=_config()
    )

    revise = generator.revise_calls[0]
    assert revise["task"] == "add tests for auth"
    assert [doc.doc_metadata["source"] for doc in revise["source_evidence"]] == ["app/auth.py"]
    assert [doc.doc_metadata["source"] for doc in revise["test_evidence"]] == ["tests/test_auth.py"]
    assert [file.path for file in revise["prior_files"]] == ["tests/test_auth.py"]
    assert revise["diff"] == diff
    assert [finding.category for finding in revise["findings"]] == ["coverage"]


def test_revised_files_are_validated_and_rediffed_through_the_same_path(tmp_path) -> None:
    """Revised proposals are written and a new canonical diff is derived by Git, exactly like initial generation."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(reviews=[PatchReview(score=3, findings=[]), PatchReview(score=10, findings=[])])
    revised_file = GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...\ndef test_y(): ...")
    generator = FakeGenerator(
        GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]),
        revision=GenerationProposal(generated_files=[revised_file]),
    )
    revised_diff = "diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_y(): ..."
    workspace = FakeWorkspace(diff=revised_diff)
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer)

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    # The revised file was written and the new diff carried onto the accepted review.
    assert workspace.written[-1].content == revised_file.content
    assert final["review_result"].diff == revised_diff
    # The revised second review assessed the new canonical diff, not the original.
    assert reviewer.calls[-1]["diff"] == revised_diff


def test_revision_resets_prior_generated_patch_before_writing_revised_files(tmp_path) -> None:
    """A revised proposal replaces the rejected patch, including files it omits."""
    repo, indexed_sha = _init_repo_with_test_root(tmp_path)
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(reviews=[PatchReview(score=3, findings=[]), PatchReview(score=10, findings=[])])
    generator = FakeGenerator(
        GenerationProposal(generated_files=[GeneratedFile(path="tests/test_removed.py", content="def test_removed():\n    assert True\n")]),
        revision=GenerationProposal(generated_files=[GeneratedFile(path="tests/test_kept.py", content="def test_kept():\n    assert True\n")]),
    )
    graph = build_graph(
        classifier_llm=FakeClassifierLLM("test_generation"),
        retriever=FakeRetriever(),
        llm=FakeGeneratorLLM(),
        planner_llm=FakePlannerLLM(PlannerOutput(in_scope=True, intents=[])),
        generator=generator,
        reviewer=reviewer,
        run_recorder=recorder,
        workspace_factory=lambda checkout_root: LocalGitWorkspace(checkout_root),
    )

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(repo),
            "indexed_commit_sha": indexed_sha,
        },
        config=_config(),
    )

    assert final["review_result"].accepted is True
    assert "tests/test_kept.py" in final["diff"]
    assert "tests/test_removed.py" not in final["diff"]
    assert (repo / "tests" / "test_kept.py").exists()
    assert not (repo / "tests" / "test_removed.py").exists()


def test_second_review_rejection_terminates_as_a_review_stage_failure(tmp_path) -> None:
    """A rejected second review fails the run at the review stage with a sanitized reason, never an unbounded retry."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=3, findings=[ReviewFinding(category="coverage", detail="still incomplete")]))
    generator = FakeGenerator(
        GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]),
        revision=GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...  # revised")]),
    )
    graph = _generation_graph(
        generator=generator, recorder=recorder, workspace=FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py"), reviewer=reviewer
    )

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    # Exactly one revision was attempted, then the run terminated as a review-stage failure.
    assert len(generator.revise_calls) == 1
    failure = final["failure"]
    assert failure.failed_stage == "reviewing"
    assert failure.coding_run_id == recorder.run_id
    # The reason is user-safe and never leaks raw model output or exception text.
    assert "reject" in failure.reason.lower()
    # Both reviews recorded a rejection and the run was failed.
    assert [event[2] for event in recorder.events if event[0] == "record_review"] == [False, False]
    assert recorder.events[-1][0] == "fail"


def test_revision_generation_failure_is_a_generating_run_failure(tmp_path) -> None:
    """A reviser that cannot produce a revised proposal fails the run at the generating stage."""
    (tmp_path / "tests").mkdir()
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=3, findings=[]))

    class RaisingReviser(FakeGenerator):
        def revise(self, *, task, source_evidence, test_evidence, prior_files, diff, findings):
            raise RuntimeError("model unavailable")

    generator = RaisingReviser(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    graph = _generation_graph(
        generator=generator, recorder=recorder, workspace=FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py"), reviewer=reviewer
    )

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    assert final["failure"].failed_stage == "generating"
    assert final["failure"].coding_run_id == recorder.run_id
    # A reviser crash is sanitized, never leaking raw exception text.
    assert "unavailable" not in final["failure"].reason
    assert recorder.events[-1][0] == "fail"


def test_revision_validation_failure_is_a_generating_run_failure(tmp_path) -> None:
    """A revised proposal escaping Test File scope is rejected before writing as a generating-stage failure."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text("real application code")
    recorder = RecordingRecorder()
    reviewer = FakeReviewer(PatchReview(score=3, findings=[]))
    generator = FakeGenerator(
        GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]),
        revision=GenerationProposal(generated_files=[GeneratedFile(path="app/auth.py", content="malicious")]),
    )
    workspace = FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py")
    graph = _generation_graph(generator=generator, recorder=recorder, workspace=workspace, reviewer=reviewer)

    final = graph.invoke(
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
        config=_config(),
    )

    assert final["failure"].failed_stage == "generating"
    # The revised out-of-scope file was never written.
    assert all(file.path != "app/auth.py" for file in (workspace.written or []))
    assert recorder.events[-1][0] == "fail"


def test_revision_stream_distinguishes_revising_and_second_review_stages(tmp_path) -> None:
    """The Agent Stream marks the revision and second-review passes with distinct stages and ends with one terminal review result."""
    (tmp_path / "tests").mkdir()
    reviewer = FakeReviewer(reviews=[PatchReview(score=3, findings=[]), PatchReview(score=10, findings=[])])
    generator = FakeGenerator(
        GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]),
        revision=GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...\ndef test_y(): ...")]),
    )
    graph = _generation_graph(generator=generator, workspace=FakeWorkspace(diff="diff --git a/tests/test_auth.py b/tests/test_auth.py"), reviewer=reviewer)

    events = _custom_events(
        graph,
        {
            "question": "add tests",
            "repository_id": uuid.uuid4(),
            "repository_session_id": uuid.uuid4(),
            "checkout_root": str(tmp_path),
            "indexed_commit_sha": "abc",
        },
    )

    stages = [event.stage for event in events if isinstance(event, Stage)]
    assert stages == ["classifying", "planning", "retrieving", "generating", "reviewing", "revising", "re_reviewing"]


# ── Agent Stream ordering (custom mode) ───────────────────────────


def _custom_events(graph, graph_input):
    items = graph.stream(graph_input, config=_config(), stream_mode=["custom"])
    return [chunk for _mode, chunk in items]


def test_test_generation_stream_emits_ordered_stage_and_run_markers() -> None:
    """Test-generation progress is classifying → planning → retrieving → generating and identifies the run."""
    recorder = RecordingRecorder()
    planner_output = PlannerOutput(in_scope=True, intents=[ResearchIntent(target="source", description="x")])
    graph = _build(FakeClassifierLLM("test_generation"), recorder=recorder, planner_llm=FakePlannerLLM(planner_output))

    events = _custom_events(graph, {"question": "add tests", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4(), "checkout_root": "/unused"})

    assert [event.stage for event in events if isinstance(event, Stage)] == ["classifying", "planning", "retrieving", "generating", "reviewing"]
    run_markers = [event for event in events if isinstance(event, RunStarted)]
    assert len(run_markers) == 1
    assert run_markers[0].coding_run_id == recorder.run_id


def test_repository_question_stream_emits_ordered_stage_markers() -> None:
    """Repository-question progress is classifying → retrieving → generating."""
    repository_id = uuid.uuid4()
    graph = _build(FakeClassifierLLM("repository_question"), retriever=FakeRetriever([_source(repository_id, "app/a.py", "x")]), llm=FakeGeneratorLLM(("a",)))

    events = _custom_events(graph, {"question": "how?", "repository_id": repository_id})

    assert [event.stage for event in events if isinstance(event, Stage)] == ["classifying", "retrieving", "generating"]
