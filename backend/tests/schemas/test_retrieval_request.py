"""Specify the planner's Repository Document retrieval contract."""

from app.agents.nodes.planner import PlannerOutput
from app.schemas import RetrievalRequest


def test_planner_output_describes_source_and_test_repository_documents() -> None:
    source_request = RetrievalRequest(document_type="source", description="authentication implementation", candidate_paths=["app/auth.py"])
    test_request = RetrievalRequest(document_type="test", description="existing authentication tests")

    output = PlannerOutput(in_scope=True, retrieval_requests=[source_request, test_request])

    assert output.model_dump() == {
        "in_scope": True,
        "retrieval_requests": [
            {"document_type": "source", "description": "authentication implementation", "candidate_paths": ["app/auth.py"]},
            {"document_type": "test", "description": "existing authentication tests", "candidate_paths": []},
        ],
        "reason": None,
    }
