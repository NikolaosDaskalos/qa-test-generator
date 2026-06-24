"""Cross-provider retry/fallback foundation for the unified graph's LLM call sites.

Bounded SDK-level retry lives on the model constructors (``app/integrations/llm``);
this module owns the two pieces that retry cannot express: a shared predicate that
decides which provider errors are worth falling back on, and an agent-level fallback
wrapper that re-runs a compiled agent on a cross-provider replacement when — and only
when — the primary failed transiently.
"""

import logging
from collections.abc import Callable, Iterator
from typing import Any

import anthropic
import openai
from langchain_core.runnables import Runnable, RunnableLambda

logger = logging.getLogger(__name__)

# Transient HTTP statuses worth retrying on the other provider: request timeout,
# conflict, and rate-limit. 5xx (and Anthropic's 529 overloaded, which arrives as the
# base APIStatusError rather than a 5xx subclass) are handled by the >= 500 check.
_TRANSIENT_STATUS = {408, 409, 429}


def is_transient_llm_error(exc: BaseException) -> bool:
    """Return whether a provider error is an availability blip worth a cross-provider fallback.

    Transient: connection failures and timeouts, rate-limits (429), and any 5xx —
    including Anthropic's 529 ``overloaded_error``, which surfaces as the base
    ``APIStatusError`` and so must be caught by status code, not by exception type.
    Deterministic errors (400 bad-request, 401 auth, context-length, content-policy,
    404, 422) are not transient and must fail fast rather than burn a second call.
    """
    if isinstance(exc, (openai.APIConnectionError, anthropic.APIConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _TRANSIENT_STATUS or status >= 500
    return False


class _TransientProviderError(Exception):
    """Internal marker: a transient primary failure that should trigger the fallback.

    ``Runnable.with_fallbacks`` matches handled exceptions by type, but a precise
    transient-only filter cannot — a 529 and a 400 both arrive as the base
    ``APIStatusError``. So the guarded primary re-raises only *transient* failures as
    this marker, which ``with_fallbacks`` is configured to catch; deterministic
    failures propagate as themselves and fail fast.
    """


def with_agent_fallback(primary: Runnable, fallback: Runnable, *, primary_label: str, fallback_label: str) -> Runnable:
    """Compose ``primary`` with a cross-provider ``fallback`` that fires only on transient errors.

    ``create_agent`` rejects a non-``BaseChatModel`` model, so fallback cannot live on
    the model object and must wrap the compiled agent: the whole bounded ReAct loop
    re-runs on the fallback provider. A transient primary failure logs a WARNING and is
    re-raised as the internal marker ``with_fallbacks`` catches; a deterministic failure
    propagates untouched so the run fails fast without burning a second provider call.
    """

    def guarded(agent_input):
        try:
            return primary.invoke(agent_input)
        except _TransientProviderError:
            raise
        except BaseException as exc:
            if not is_transient_llm_error(exc):
                raise
            logger.warning("LLM provider fallback firing primary=%s fallback=%s reason=%s", primary_label, fallback_label, _reason(exc))
            raise _TransientProviderError(str(exc)) from exc

    return RunnableLambda(guarded).with_fallbacks(
        [RunnableLambda(lambda agent_input: fallback.invoke(agent_input))],
        exceptions_to_handle=(_TransientProviderError,),
    )


class _TransientGuard(Runnable):
    """Runnable wrapper that converts only transient provider failures into the fallback marker."""

    def __init__(self, runnable: Runnable, *, primary_label: str, fallback_label: str) -> None:
        self._runnable = runnable
        self._primary_label = primary_label
        self._fallback_label = fallback_label

    def invoke(self, direct_input: Any, config=None, **kwargs):
        try:
            return self._runnable.invoke(direct_input, config=config, **kwargs)
        except _TransientProviderError:
            raise
        except BaseException as exc:
            self._raise_for_fallback(exc)

    def stream(self, direct_input: Any, config=None, **kwargs) -> Iterator[Any]:
        try:
            yield from self._runnable.stream(direct_input, config=config, **kwargs)
        except _TransientProviderError:
            raise
        except BaseException as exc:
            self._raise_for_fallback(exc)

    def batch(self, direct_inputs: Any, config=None, *, return_exceptions: bool = False, **kwargs):
        # Keep the batched call a single underlying ``batch`` (not N invokes). ``with_fallbacks``
        # drives batch via ``return_exceptions=True`` and inspects each item, so transient
        # provider errors are converted per-item to the marker it re-runs on the fallback; a
        # deterministic error stays itself and fails fast. A model whose ``batch`` raises as a
        # whole is fanned across the inputs so the same per-item handling applies.
        try:
            outputs = self._runnable.batch(direct_inputs, config, return_exceptions=True, **kwargs)
        except BaseException as exc:
            outputs = [exc] * len(direct_inputs)
        converted = [self._as_fallback_marker(output) for output in outputs]
        if return_exceptions:
            return converted
        for output in converted:
            if isinstance(output, BaseException):
                raise output
        return converted

    def _as_fallback_marker(self, output: Any) -> Any:
        if isinstance(output, BaseException) and not isinstance(output, _TransientProviderError) and is_transient_llm_error(output):
            logger.warning(
                "LLM provider fallback firing primary=%s fallback=%s reason=%s",
                self._primary_label,
                self._fallback_label,
                _reason(output),
            )
            return _TransientProviderError(str(output))
        return output

    def _raise_for_fallback(self, exc: BaseException) -> None:
        if not is_transient_llm_error(exc):
            raise exc
        logger.warning(
            "LLM provider fallback firing primary=%s fallback=%s reason=%s",
            self._primary_label,
            self._fallback_label,
            _reason(exc),
        )
        raise _TransientProviderError(str(exc)) from exc


def with_provider_fallback(primary: Any, fallback: Any, adapt: Callable[[Any], Runnable], *, primary_label: str, fallback_label: str) -> Runnable:
    """Adapt two direct-provider models, then compose transient-only fallback.

    Direct sites such as structured classification/planning and streamed repository
    answers must adapt real ``BaseChatModel`` instances before fallback wrapping, since
    the wrapper is no longer itself a chat model.
    """
    primary_runnable = adapt(primary)
    fallback_runnable = adapt(fallback)
    return _TransientGuard(primary_runnable, primary_label=primary_label, fallback_label=fallback_label).with_fallbacks(
        [fallback_runnable],
        exceptions_to_handle=(_TransientProviderError,),
    )


def model_label(model: Any) -> str:
    """Return a stable human label for provider fallback logs."""
    for attr in ("model_name", "model"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return value
    return type(model).__name__


def _reason(exc: BaseException) -> str:
    """A compact, log-safe description of why the fallback fired (type plus HTTP status)."""
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    return f"{name} status={status}" if isinstance(status, int) else name
