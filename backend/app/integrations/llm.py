"""Construct the concrete chat-model and reranker clients the app composes.

These factories keep provider SDK details (OpenAI, Anthropic, Cohere) in one
integration module so the composition root wires behavior without owning the
client construction.
"""

from langchain_anthropic import ChatAnthropic
from langchain_cohere import CohereRerank
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core import settings


def create_chat_model(model: str, max_tokens: int) -> ChatOpenAI:
    """Build a streaming OpenAI chat model for the given model id."""
    return ChatOpenAI(model=model, temperature=settings.TEMPERATURE, max_tokens=max_tokens, streaming=True, api_key=settings.OPENAI_API_KEY)


def create_anthropic_chat_model(model: str, max_tokens: int) -> ChatAnthropic:
    """Build a streaming Anthropic chat model for the given model id."""
    return ChatAnthropic(
        model_name=model,
        temperature=settings.TEMPERATURE,
        max_tokens_to_sample=max_tokens,
        streaming=True,
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=None,
        stop=None,
    )


def create_reranker() -> CohereRerank:
    """Build the Cohere reranker used to order retrieved Repository Documents."""
    return CohereRerank(model=settings.COHERE_RERANK_MODEL, cohere_api_key=SecretStr(settings.COHERE_API_KEY), top_n=settings.TOP_K)
