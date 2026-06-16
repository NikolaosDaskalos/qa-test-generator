"""Structured generator output: complete file proposals and External References.

The generator returns complete file paths and contents — never diff text — so the
backend retains control of what is written and derives the canonical diff itself.
External References are the web results consulted for a test framework's current
syntax and best practices; they are kept separate from Repository Evidence and
never ground claims about the Repository's code.
"""

from pydantic import BaseModel, Field


class GeneratedFile(BaseModel):
    """One complete proposed file: a checkout-relative path and its full contents."""

    path: str = Field(description="Repository-relative path of the test file to write.")
    content: str = Field(description="The complete contents of the test file.")


class ExternalReference(BaseModel):
    """A web result consulted for test-writing guidance, kept apart from Repository Evidence."""

    url: str = Field(description="URL of the consulted external source.")
    title: str = Field(default="", description="Human-readable title of the external source.")


class GenerationProposal(BaseModel):
    """The generator's structured result: proposed files plus External References."""

    generated_files: list[GeneratedFile] = Field(default_factory=list)
    external_references: list[ExternalReference] = Field(default_factory=list)
