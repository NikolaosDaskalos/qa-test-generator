"""The planner's structured request for Repository Documents."""

from typing import Literal

from pydantic import BaseModel, Field

RepositoryDocumentType = Literal["source", "test"]


class RetrievalRequest(BaseModel):
    """Describe Repository Documents to retrieve for a Code Generation Task."""

    document_type: RepositoryDocumentType = Field(description="Whether to retrieve source-code Repository Documents or existing-test Repository Documents.")
    description: str = Field(description="Natural-language query describing the Repository Documents needed for the task.")
    candidate_paths: list[str] = Field(
        default_factory=list,
        description="Optional repository-relative path hints that may contain relevant Repository Documents; absolute and unsafe paths are ignored.",
    )
