"""Small synchronous client for the local Ollama generation API."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Generator

import httpx

from ..settings import Settings

logger = logging.getLogger(__name__)


class OllamaUnavailableError(RuntimeError):
    """Raised when local generation cannot return a valid response."""


class OllamaStructuredOutputError(RuntimeError):
    """Structured generation ended before a valid JSON response was produced."""

    def __init__(self, message: str, *, done_reason: str | None, response: str) -> None:
        super().__init__(message)
        self.done_reason = done_reason
        self.response = response


_THINKING_BLOCK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _without_thinking(text: str) -> str:
    return _THINKING_BLOCK.sub("", text).strip()


def _visible_tokens(tokens: Generator[str, None, None]) -> Generator[str, None, None]:
    """Filter reasoning tags even when an upstream token splits their delimiters."""
    buffered = ""
    inside_thinking = False
    for token in tokens:
        buffered += token
        while buffered:
            if inside_thinking:
                closing = buffered.lower().find("</think>")
                if closing < 0:
                    buffered = buffered[-7:]
                    break
                buffered = buffered[closing + len("</think>"):]
                inside_thinking = False
                continue
            opening = buffered.lower().find("<think>")
            if opening >= 0:
                if opening:
                    yield buffered[:opening]
                buffered = buffered[opening + len("<think>"):]
                inside_thinking = True
                continue
            if len(buffered) > 7:
                yield buffered[:-7]
                buffered = buffered[-7:]
            break
    if not inside_thinking and buffered:
        yield buffered


def is_configured_model_available(settings: Settings) -> bool:
    """Return whether Ollama advertises the exact model selected by LLM_MODEL."""
    timeout = httpx.Timeout(5.0, connect=5.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            return any(
                model.get("name") == settings.llm_model
                for model in response.json().get("models", [])
            )
    except (httpx.HTTPError, ValueError):
        logger.exception("Unable to query configured Ollama model=%s", settings.llm_model)
        return False


def warm_up_configured_model(settings: Settings) -> None:
    """Load the selected model before accepting RFP traffic; raises on failure."""
    if not is_configured_model_available(settings):
        raise OllamaUnavailableError(f"Configured Ollama model unavailable: {settings.llm_model}")

    timeout_seconds = min(settings.ollama_warmup_timeout_seconds, settings.ollama_timeout_seconds)
    timeout = httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds))
    started = time.monotonic()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{settings.ollama_url.rstrip('/')}/api/generate",
                json={
                    "model": settings.llm_model,
                    "prompt": "Réponds uniquement: prêt",
                    "stream": False,
                    "think": False,
                    "keep_alive": settings.ollama_keep_alive,
                    "options": {"temperature": 0, "num_predict": 2, "num_ctx": settings.ollama_num_ctx},
                },
            )
            response.raise_for_status()
            if not response.json().get("response", "").strip():
                raise ValueError("Ollama warm-up returned an empty response")
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Ollama warm-up failed model=%s timeoutSeconds=%.2f", settings.llm_model, timeout_seconds)
        raise OllamaUnavailableError("Ollama model warm-up failed") from exc

    logger.info("Ollama model warm-up succeeded model=%s durationMs=%.0f", settings.llm_model, (time.monotonic() - started) * 1000)


def _safe_excerpt(value: str, limit: int = 240) -> str:
    """Keep diagnostics useful without logging an entire generated proposal."""
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _generation_payload(
    prompt: str, settings: Settings, max_tokens: int, output_schema: dict[str, Any] | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "keep_alive": settings.ollama_keep_alive,
        "options": {
            "temperature": 0,
            "num_predict": max_tokens,
            "num_ctx": settings.ollama_num_ctx,
        },
    }
    if output_schema is not None:
        payload["format"] = output_schema
    return payload


def _retryable(exc: Exception) -> bool:
    """Only timeouts are retried; requests may have already reached the LLM."""
    return isinstance(exc, httpx.TimeoutException)


def _backoff_seconds(settings: Settings, attempt: int, deadline: float) -> float:
    delay = settings.ollama_retry_backoff_seconds * (2 ** (attempt - 1))
    return max(0.0, min(delay, deadline - time.monotonic()))


def generate_text(
    prompt: str,
    settings: Settings,
    *,
    max_tokens: int,
    output_schema: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    request_id: str | None = None,
    stage: str | None = None,
) -> str:
    """Generate text with bounded retries and a total per-call timeout budget."""
    effective_timeout = timeout_seconds if timeout_seconds is not None else settings.ollama_timeout_seconds
    deadline = time.monotonic() + effective_timeout
    payload = _generation_payload(prompt, settings, max_tokens, output_schema)
    last_error: Exception | None = None

    for attempt in range(1, settings.ollama_retry_attempts + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            timeout = httpx.Timeout(remaining, connect=min(5.0, remaining))
            with httpx.Client(timeout=timeout) as client:
                response = client.post(f"{settings.ollama_url.rstrip('/')}/api/generate", json=payload)
                response.raise_for_status()
                result = response.json()
                generated = _without_thinking(result.get("response", "").strip())
                done_reason = result.get("done_reason")
            logger.warning(
                "Ollama structured response requestId=%s stage=%s doneReason=%s length=%s excerpt=%r",
                request_id, stage, done_reason, len(generated), _safe_excerpt(generated),
            )
            if not generated:
                raise ValueError("Ollama returned an empty response")
            if output_schema is not None and done_reason == "length":
                raise OllamaStructuredOutputError(
                    "Ollama structured response was truncated", done_reason=done_reason, response=generated,
                )
            return generated
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            retry = attempt < settings.ollama_retry_attempts and _retryable(exc)
            logger.exception(
                "Ollama generation attempt %s/%s failed model=%s timeoutSeconds=%.2f retry=%s",
                attempt, settings.ollama_retry_attempts, settings.llm_model, remaining, retry,
            )
            if not retry:
                break
            delay = _backoff_seconds(settings, attempt, deadline)
            if delay > 0:
                time.sleep(delay)

    raise OllamaUnavailableError("Local Ollama generation failed after retry budget was exhausted") from last_error


async def generate_text_async(
    prompt: str,
    settings: Settings,
    *,
    max_tokens: int,
    output_schema: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    request_id: str | None = None,
    stage: str | None = None,
) -> str:
    """Async generation with bounded retries and a total per-call timeout budget."""
    effective_timeout = timeout_seconds if timeout_seconds is not None else settings.ollama_timeout_seconds
    deadline = time.monotonic() + effective_timeout
    payload = _generation_payload(prompt, settings, max_tokens, output_schema)
    last_error: Exception | None = None

    for attempt in range(1, settings.ollama_retry_attempts + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            timeout = httpx.Timeout(remaining, connect=min(5.0, remaining))
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{settings.ollama_url.rstrip('/')}/api/generate", json=payload)
                response.raise_for_status()
                result = response.json()
                generated = _without_thinking(result.get("response", "").strip())
                done_reason = result.get("done_reason")
            logger.warning(
                "Ollama structured response requestId=%s stage=%s doneReason=%s length=%s excerpt=%r",
                request_id, stage, done_reason, len(generated), _safe_excerpt(generated),
            )
            if not generated:
                raise ValueError("Ollama returned an empty response")
            if output_schema is not None and done_reason == "length":
                raise OllamaStructuredOutputError(
                    "Ollama structured response was truncated", done_reason=done_reason, response=generated,
                )
            return generated
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            retry = attempt < settings.ollama_retry_attempts and _retryable(exc)
            logger.exception(
                "Ollama async generation attempt %s/%s failed model=%s timeoutSeconds=%.2f retry=%s",
                attempt, settings.ollama_retry_attempts, settings.llm_model, remaining, retry,
            )
            if not retry:
                break
            delay = _backoff_seconds(settings, attempt, deadline)
            if delay > 0:
                await asyncio.sleep(delay)

    raise OllamaUnavailableError("Local Ollama generation failed after retry budget was exhausted") from last_error


def generate_text_stream(
    prompt: str,
    settings: Settings,
    *,
    max_tokens: int,
    output_schema: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> Generator[str, None, None]:
    """Stream tokens from Ollama one by one using stream=True."""
    effective_timeout = timeout_seconds if timeout_seconds is not None else settings.ollama_timeout_seconds
    timeout = httpx.Timeout(effective_timeout, connect=5.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            payload: dict[str, Any] = {
                "model": settings.llm_model,
                "prompt": prompt,
                "stream": True,
                "think": False,
                "keep_alive": settings.ollama_keep_alive,
                "options": {
                    "temperature": 0,
                    "num_predict": max_tokens,
                    "num_ctx": settings.ollama_num_ctx,
                },
            }
            if output_schema is not None:
                payload["format"] = output_schema
            with client.stream(
                "POST",
                f"{settings.ollama_url.rstrip('/')}/api/generate",
                json=payload,
            ) as response:
                response.raise_for_status()
                logger.info("ollama stream connected")
                try:
                    def upstream_tokens() -> Generator[str, None, None]:
                        for line in response.iter_lines():
                            if not line:
                                continue
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break

                    yield from _visible_tokens(upstream_tokens())
                except GeneratorExit:
                    logger.info("ollama stream cancelled by downstream")
                    raise
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaUnavailableError("Local Ollama streaming failed") from exc
