"""Small synchronous client for the local Ollama generation API."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Generator

import httpx

from ..settings import Settings

logger = logging.getLogger(__name__)


class OllamaUnavailableError(RuntimeError):
    """Raised when local generation cannot return a valid response."""


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
        return False


def generate_text(
    prompt: str,
    settings: Settings,
    *,
    max_tokens: int,
    output_schema: dict[str, Any] | None = None,
) -> str:
    """Generate one non-streamed response with the configured local model."""
    timeout = httpx.Timeout(settings.ollama_timeout_seconds, connect=5.0)
    try:
        with httpx.Client(timeout=timeout) as client:
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
            response = client.post(
                f"{settings.ollama_url.rstrip('/')}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            generated = response.json().get("response", "").strip()
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaUnavailableError("Local Ollama generation failed") from exc

    generated = _without_thinking(generated)
    if not generated:
        raise OllamaUnavailableError("Local Ollama returned an empty response")
    return generated


def generate_text_stream(
    prompt: str,
    settings: Settings,
    *,
    max_tokens: int,
    output_schema: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    """Stream tokens from Ollama one by one using stream=True."""
    timeout = httpx.Timeout(settings.ollama_timeout_seconds, connect=5.0)
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
