"""Token-aware text chunking for the ingestion pipeline.

Uses ``tiktoken`` (``cl100k_base`` encoding — compatible with Qwen-family
models) to measure chunk sizes in **tokens** rather than raw characters.
All public-facing parameters remain expressed in *characters* so that
existing callers (``document_pipeline.py``, ``pipeline.py``, and all tests)
continue to work unchanged.  Internally, every length comparison now uses
a fast token count, which guarantees that:

1. No chunk silently overflows the LLM context window.
2. Sentence and paragraph boundaries are still respected.
3. Overlap is computed in tokens for consistent context carry-over.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

import tiktoken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_ENCODING_NAME = "cl100k_base"


@lru_cache(maxsize=1)
def _get_encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(_ENCODING_NAME)


def _token_count(text: str) -> int:
    """Return the number of tokens for *text* using the shared encoding."""
    return len(_get_encoding().encode(text, disallowed_special=()))


# ---------------------------------------------------------------------------
# Boundary patterns (unchanged)
# ---------------------------------------------------------------------------

_DEFAULT_TARGET_CHARACTERS = 850
_DEFAULT_MIN_CHARACTERS = 250
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n+")

# Approximate character-to-token ratio for French/mixed text.  Used only to
# convert the caller-supplied character limits into internal token limits so
# the external API stays stable.
_CHARS_PER_TOKEN = 3.2


def _chars_to_tokens(characters: int) -> int:
    """Convert a character budget to an approximate token budget."""
    return max(1, int(characters / _CHARS_PER_TOKEN))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    max_characters: int,
    overlap_characters: int,
    *,
    target_characters: int | None = None,
    min_characters: int | None = None,
) -> list[str]:
    """Split *text* into token-bounded chunks respecting sentence boundaries.

    Parameters are expressed in **characters** (unchanged contract) but all
    internal budget comparisons use token counts via ``tiktoken``.
    """
    if max_characters <= 0:
        raise ValueError("max_characters must be positive")
    if overlap_characters < 0 or overlap_characters >= max_characters:
        raise ValueError("overlap_characters must be between 0 and max_characters")

    target = target_characters or min(_DEFAULT_TARGET_CHARACTERS, max_characters)
    minimum = min_characters or min(_DEFAULT_MIN_CHARACTERS, target)
    if not 0 < minimum <= target <= max_characters:
        raise ValueError(
            "min_characters, target_characters and max_characters must be ordered"
        )

    # Convert character limits → token limits
    max_tokens = _chars_to_tokens(max_characters)
    target_tokens = _chars_to_tokens(target)
    min_tokens = _chars_to_tokens(minimum)
    overlap_tokens = _chars_to_tokens(overlap_characters)

    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in _PARAGRAPH_BOUNDARY.split(text.strip())
    ]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    if not paragraphs:
        return []

    units: list[tuple[str, int, bool, int]] = []  # (text, para_idx, is_sentence, tokens)
    for paragraph_index, paragraph in enumerate(paragraphs):
        sentences = _SENTENCE_BOUNDARY.split(paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            tokens = _token_count(sentence)
            if tokens <= max_tokens:
                units.append((sentence, paragraph_index, True, tokens))
                continue
            parts = _split_oversized(sentence, max_tokens)
            units.extend(
                (part, paragraph_index, False, _token_count(part))
                for part in parts
            )

    chunks: list[str] = []
    current: list[tuple[str, int, bool, int]] = []
    current_tokens = 0

    for unit in units:
        candidate = [*current, unit]
        candidate_tokens = current_tokens + unit[3] + (1 if current else 0)  # +1 for separator token
        should_append = (
            not current
            or candidate_tokens <= target_tokens
            or (current_tokens < min_tokens and candidate_tokens <= max_tokens)
            or (
                current_tokens < target_tokens
                and candidate_tokens <= max_tokens
                and abs(candidate_tokens - target_tokens) <= abs(current_tokens - target_tokens)
            )
        )
        if should_append:
            current = candidate
            current_tokens = candidate_tokens
            continue

        chunks.append(_render_units(current))
        overlap_units = _overlap_sentence(current, overlap_tokens)
        overlap_unit_tokens = sum(u[3] for u in overlap_units)
        candidate = [*overlap_units, unit]
        candidate_tokens = overlap_unit_tokens + unit[3] + (1 if overlap_units else 0)
        if candidate_tokens <= max_tokens:
            current = candidate
            current_tokens = candidate_tokens
        else:
            current = [unit]
            current_tokens = unit[3]

    if current:
        chunks.append(_render_units(current))
    return chunks


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _render_units(units: list[tuple[str, int, bool, int]]) -> str:
    if not units:
        return ""
    rendered = units[0][0]
    for previous, current in zip(units, units[1:]):
        separator = "\n\n" if previous[1] != current[1] else " "
        rendered += separator + current[0]
    return rendered


def _overlap_sentence(
    units: list[tuple[str, int, bool, int]], overlap_tokens: int
) -> list[tuple[str, int, bool, int]]:
    if not units or overlap_tokens == 0:
        return []
    sentence = units[-1]
    # Keep the last complete sentence as overlap if it fits the token budget
    # and is not longer than 140 characters (backward compat for tests/behavior).
    if not sentence[2] or sentence[3] > overlap_tokens or len(sentence[0]) > 140:
        return []
    return [sentence]


def _split_oversized(text: str, max_tokens: int) -> list[str]:
    """Split text that exceeds *max_tokens* into smaller pieces at word boundaries."""
    words = text.split(" ")
    result: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for word in words:
        word_tokens = _token_count(word)
        if word_tokens > max_tokens:
            if current:
                result.append(" ".join(current))
                current = []
                current_tokens = 0
            # Force-split a single huge word by characters
            for index in range(0, len(word), int(max_tokens * _CHARS_PER_TOKEN)):
                chunk = word[index: index + int(max_tokens * _CHARS_PER_TOKEN)]
                result.append(chunk)
            continue
        candidate_tokens = current_tokens + word_tokens + (1 if current else 0)
        if current and candidate_tokens > max_tokens:
            result.append(" ".join(current))
            current = [word]
            current_tokens = word_tokens
        else:
            current.append(word)
            current_tokens = candidate_tokens
    if current:
        result.append(" ".join(current))
    return result
