"""Deterministic routing and branch tests for the unified intent-routed graph.

These exercise the compiled ``StateGraph`` through its public ``invoke`` with
fake language models and a fake retriever, so no external model is ever called.
"""

import uuid

from app.agent.graph import Classification, build_graph
from app.agent.planner import PlannerOutput
from app.agent.repository_question import INSUFFICIENT_EVIDENCE_ANSWER
from app.enums.coding_run import CodingRunStatus
from app.models.source_document import SourceDocument
from app.schemas.agent_stream import Citation, PatchResult, RunStarted, Stage
from app.schemas.generation import ExternalReference, GeneratedFile, GenerationProposal
from app.schemas.research_intent import ResearchIntent


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

    def advance(self, coding_run_id, status):
        self.events.append(("advance", coding_run_id, status))

    def fail(self, coding_run_id, *, failed_stage, reason):
        self.events.append(("fail", coding_run_id, failed_stage, reason))

    def complete(self, coding_run_id, *, branch, diff, generated_files, external_references):
        self.events.append(("complete", coding_run_id, branch, diff, generated_files, external_references))


class FakeGenerator:
    """A ``TestGenerator`` returning a fixed proposal and recording its inputs."""

    def __init__(self, proposal: GenerationProposal | None = None) -> None:
        self.proposal = proposal or GenerationProposal()
        self.calls = []

    def generate(self, *, task, source_evidence, test_evidence):
        self.calls.append({"task": task, "source_evidence": source_evidence, "test_evidence": test_evidence})
        return self.proposal


class RaisingGenerator:
    """A ``TestGenerator`` that fails to produce a proposal."""

    def generate(self, *, task, source_evidence, test_evidence):
        raise RuntimeError("model unavailable")


class FakeWorkspace:
    """A ``GenerationWorkspace`` that records writes and returns a canned diff."""

    def __init__(self, diff: str = "") -> None:
        self._diff = diff
        self.prepared_from = None
        self.written = None

    def prepare_branch(self, indexed_commit_sha):
        self.prepared_from = indexed_commit_sha
        return "qa-tests/fake"

    def write_test_files(self, files):
        self.written = files

    def diff(self):
        return self._diff


def _workspace_factory(workspace=None):
    workspace = workspace or FakeWorkspace()
    return lambda _checkout_root: workspace


def _source(repository_id: uuid.UUID, source: str, content: str = "evidence") -> SourceDocument:
    return SourceDocument(repository_id=repository_id, content=content, doc_metadata={"source": source})


def _config(thread_id: str = "t1") -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _build(classifier_llm, *, retriever=None, llm=None, planner_llm=None, recorder=None, generator=None, workspace=None):
    return build_graph(
        classifier_llm=classifier_llm,
        retriever=retriever if retriever is not None else FakeRetriever(),
        llm=llm if llm is not None else FakeGeneratorLLM(),
        planner_llm=planner_llm if planner_llm is not None else FakePlannerLLM(PlannerOutput(in_scope=True, intents=[])),
        generator=generator if generator is not None else FakeGenerator(),
        run_recorder=recorder,
        workspace_factory=_workspace_factory(workspace),
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

    final = graph.invoke(
        {"question": "now write tests for the auth module", "repository_id": uuid.uuid4()},
        config=_config(),
    )

    assert final["intent"] == "test_generation"
    assert final["trace"][0] == "classify"
    assert "plan" in final["trace"]
    assert "retrieve" not in final["trace"]


def test_graph_routes_repository_question_intent_to_the_retrieval_branch() -> None:
    """A repository-question classification skips planning and retrieves first."""
    graph = _build(FakeClassifierLLM("repository_question"))

    final = graph.invoke(
        {"question": "how does the auth module work?", "repository_id": uuid.uuid4()},
        config=_config(),
    )

    assert final["intent"] == "repository_question"
    assert final["trace"][:2] == ["classify", "retrieve"]


def test_uncertain_classification_falls_back_to_the_repository_question_branch() -> None:
    """When the classifier cannot commit, the graph takes the read-only branch."""
    graph = _build(UncertainClassifierLLM())

    final = graph.invoke(
        {"question": "do something ambiguous", "repository_id": uuid.uuid4()},
        config=_config(),
    )

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

    final = graph.invoke(
        {"question": "how is auth tested?", "repository_id": repository_id},
        config=_config(),
    )

    assert retriever.calls[-1][0] == "how is auth tested?"
    assert retriever.calls[-1][1]["repository_id"] == repository_id
    assert final["answer"] == "the answer"
    assert final["citations"] == [Citation(source="app/auth.py"), Citation(source="app/login.py")]


def test_repository_question_branch_reports_insufficient_evidence_without_calling_the_model() -> None:
    """Empty Repository Evidence yields a deterministic answer and never streams the model."""
    repository_id = uuid.uuid4()
    llm = FakeGeneratorLLM(("unused",))
    graph = _build(FakeClassifierLLM("repository_question"), retriever=FakeRetriever([]), llm=llm)

    final = graph.invoke(
        {"question": "anything", "repository_id": repository_id},
        config=_config(),
    )

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

    final = graph.invoke(
        {"question": "add tests for the auth module", "repository_id": uuid.uuid4()},
        config=_config(),
    )

    assert final.get("failure") is None
    intents = final["research_intents"]
    assert [intent.target for intent in intents] == ["source", "test"]
    assert intents[0].candidate_paths == ["app/auth.py"]


def test_out_of_scope_task_is_rejected_at_the_planning_stage() -> None:
    """A request outside adding or improving tests fails at planning before any retrieval."""
    planner_output = PlannerOutput(in_scope=False, reason="This asks to refactor production code, not to add or improve tests.")
    graph = _build(FakeClassifierLLM("test_generation"), planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke(
        {"question": "rename the auth module everywhere", "repository_id": uuid.uuid4()},
        config=_config(),
    )

    failure = final["failure"]
    assert failure.failed_stage == "planning"
    assert failure.reason == "This asks to refactor production code, not to add or improve tests."
    assert not final.get("research_intents")


# ── test_generation branch: generic retrieve ──────────────────────


def test_test_generation_retrieve_partitions_source_and_test_evidence() -> None:
    """Planner intents are executed under the session's Repository and split source vs. test."""
    repository_id = uuid.uuid4()
    retriever = QueryRetriever(
        {
            "auth implementation": [_source(repository_id, "app/auth.py", "impl")],
            "auth tests": [_source(repository_id, "tests/test_auth.py", "test")],
        }
    )
    planner_output = PlannerOutput(
        in_scope=True,
        intents=[
            ResearchIntent(target="source", description="auth implementation"),
            ResearchIntent(target="test", description="auth tests"),
        ],
    )
    graph = _build(FakeClassifierLLM("test_generation"), retriever=retriever, planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke(
        {"question": "add tests for auth", "repository_id": repository_id},
        config=_config(),
    )

    assert [doc.doc_metadata["source"] for doc in final["source_evidence"]] == ["app/auth.py"]
    assert [doc.doc_metadata["source"] for doc in final["test_evidence"]] == ["tests/test_auth.py"]
    assert all(call[1]["repository_id"] == repository_id for call in retriever.calls)


def test_test_generation_retrieve_yields_empty_partitions_when_no_evidence() -> None:
    """When retrieval finds nothing, both evidence partitions are present and empty."""
    planner_output = PlannerOutput(in_scope=True, intents=[ResearchIntent(target="source", description="nothing here")])
    graph = _build(FakeClassifierLLM("test_generation"), retriever=FakeRetriever([]), planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke(
        {"question": "add tests", "repository_id": uuid.uuid4()},
        config=_config(),
    )

    assert final["source_evidence"] == []
    assert final["test_evidence"] == []


def test_test_generation_retrieve_confines_candidate_paths_to_validated_hints(tmp_path) -> None:
    """Untrusted candidate paths are confined to the checkout; unsafe ones never proceed."""
    repository_id = uuid.uuid4()
    planner_output = PlannerOutput(
        in_scope=True,
        intents=[ResearchIntent(target="source", description="auth", candidate_paths=["app/auth.py", "/etc/passwd", "../escape"])],
    )
    graph = _build(FakeClassifierLLM("test_generation"), retriever=FakeRetriever([]), planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke(
        {"question": "add tests", "repository_id": repository_id, "checkout_root": str(tmp_path)},
        config=_config(),
    )

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
        {"question": "add tests", "repository_id": repository_id, "repository_session_id": session_id, "checkout_root": "/unused"},
        config=_config("run-thread"),
    )

    assert [event[0] for event in recorder.events] == ["start", "advance", "advance", "advance", "complete"]
    assert recorder.events[0] == ("start", "run-thread", session_id)
    assert recorder.events[1][2] == CodingRunStatus.planning
    assert recorder.events[2][2] == CodingRunStatus.retrieving
    assert recorder.events[3][2] == CodingRunStatus.generating
    assert recorder.events[4][1] == recorder.run_id
    assert final["coding_run_id"] == recorder.run_id


def test_test_generation_marks_failure_at_planning_when_out_of_scope() -> None:
    """A rejected task records a planning failure and stops before retrieving."""
    recorder = RecordingRecorder()
    planner_output = PlannerOutput(in_scope=False, reason="Not a test request")
    graph = _build(FakeClassifierLLM("test_generation"), recorder=recorder, planner_llm=FakePlannerLLM(planner_output))

    final = graph.invoke(
        {"question": "refactor", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4()},
        config=_config(),
    )

    assert [event[0] for event in recorder.events] == ["start", "advance", "fail"]
    assert recorder.events[1][2] == CodingRunStatus.planning
    assert recorder.events[2][2] == "planning"
    assert recorder.events[2][3] == "Not a test request"
    assert final["failure"].coding_run_id == recorder.run_id


# ── test_generation branch: generation & patch ────────────────────


def _generation_graph(*, generator, recorder=None, workspace=None):
    planner_output = PlannerOutput(in_scope=True, intents=[ResearchIntent(target="source", description="x")])
    return _build(FakeClassifierLLM("test_generation"), recorder=recorder, planner_llm=FakePlannerLLM(planner_output), generator=generator, workspace=workspace)


def test_generator_receives_partitioned_evidence_and_emits_structured_files() -> None:
    """The generator is handed the task and partitioned evidence and returns complete-file proposals."""
    repository_id = uuid.uuid4()
    retriever = QueryRetriever({"impl": [_source(repository_id, "app/auth.py", "code")]})
    planner_output = PlannerOutput(in_scope=True, intents=[ResearchIntent(target="source", description="impl")])
    generator = FakeGenerator(GenerationProposal(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]))
    graph = _build(
        FakeClassifierLLM("test_generation"),
        retriever=retriever,
        planner_llm=FakePlannerLLM(planner_output),
        generator=generator,
    )

    final = graph.invoke(
        {"question": "add tests for auth", "repository_id": repository_id, "checkout_root": "/unused"},
        config=_config(),
    )

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

    final = graph.invoke(
        {"question": "add tests", "repository_id": repository_id, "checkout_root": "/unused"},
        config=_config(),
    )

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
        {"question": "add tests", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4(), "checkout_root": str(tmp_path), "indexed_commit_sha": "abc"},
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
        {"question": "add tests", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4(), "checkout_root": str(tmp_path)},
        config=_config(),
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
        {"question": "add tests", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4(), "checkout_root": str(tmp_path)},
        config=_config(),
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
        {"question": "add tests", "repository_id": uuid.uuid4(), "repository_session_id": uuid.uuid4(), "checkout_root": "/unused"},
        config=_config(),
    )

    assert final["failure"].failed_stage == "generating"
    assert final["failure"].coding_run_id == recorder.run_id
    assert final.get("patch_result") is None


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

    assert [event.stage for event in events if isinstance(event, Stage)] == ["classifying", "planning", "retrieving", "generating"]
    run_markers = [event for event in events if isinstance(event, RunStarted)]
    assert len(run_markers) == 1
    assert run_markers[0].coding_run_id == recorder.run_id


def test_repository_question_stream_emits_ordered_stage_markers() -> None:
    """Repository-question progress is classifying → retrieving → generating."""
    repository_id = uuid.uuid4()
    graph = _build(
        FakeClassifierLLM("repository_question"),
        retriever=FakeRetriever([_source(repository_id, "app/a.py", "x")]),
        llm=FakeGeneratorLLM(("a",)),
    )

    events = _custom_events(graph, {"question": "how?", "repository_id": repository_id})

    assert [event.stage for event in events if isinstance(event, Stage)] == ["classifying", "retrieving", "generating"]
