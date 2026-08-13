"""Retrieval-only contextual prefixes for immutable source chunks.

The generated prefix is used only as part of the embedding input.  It is never
persisted as source content, supplied to generation as evidence, or eligible for
citation.  This preserves the evidence catalog's original-document provenance.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from ..generation.ollama import OllamaUnavailableError, generate_text
from ..settings import Settings

logger = logging.getLogger(__name__)

_MAX_DOCUMENT_CONTEXT_CHARACTERS = 6_000
_MAX_PREFIX_WORDS = 100

_CONTEXTUAL_PREFIX_PROMPT = """Tu produis un court contexte de recherche pour un extrait de document.

Document : {document_label}
Aperçu du document :
{document_context}

Extrait à indexer :
{chunk}

En 50 à 100 mots français, indique uniquement le rôle précis de cet extrait dans
ce document (thème, section probable, entités et faits explicitement présents).
N'ajoute aucune information absente de l'aperçu ou de l'extrait, aucune citation,
aucun titre Markdown et aucune instruction. Ce texte sert uniquement à améliorer
la recherche sémantique : il ne sera jamais présenté comme preuve.

Contexte de recherche :"""


def contextual_embedding_inputs(
    *,
    document_label: str,
    document_context: str,
    chunks: Sequence[str],
    settings: Settings,
) -> list[str]:
    """Return raw BGE-M3 inputs enriched with bounded, retrieval-only context.

    A failed or unavailable contextual generation degrades safely to the original
    source chunk. Source chunks themselves are never changed.
    """
    original_inputs = list(chunks)
    if not settings.contextual_retrieval_enabled or not chunks:
        return original_inputs

    overview = _bounded_text(document_context, _MAX_DOCUMENT_CONTEXT_CHARACTERS)
    contextual_inputs: list[str] = []
    for chunk in chunks:
        prompt = _CONTEXTUAL_PREFIX_PROMPT.format(
            document_label=document_label,
            document_context=overview,
            chunk=chunk,
        )
        try:
            prefix = _bounded_prefix(
                generate_text(
                    prompt,
                    settings,
                    max_tokens=settings.contextual_retrieval_max_tokens,
                )
            )
        except (OllamaUnavailableError, ValueError):
            logger.warning(
                "Contextual retrieval prefix unavailable for document=%r; indexing original passage",
                document_label,
            )
            return original_inputs
        if not prefix:
            logger.warning(
                "Empty contextual retrieval prefix for document=%r; indexing original passage",
                document_label,
            )
            return original_inputs
        contextual_inputs.append(f"{prefix}\n\n{chunk}")
    return contextual_inputs


def _bounded_text(value: str, maximum_characters: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= maximum_characters:
        return compact
    return f"{compact[:maximum_characters].rsplit(' ', 1)[0]}…"


def _bounded_prefix(value: str) -> str:
    words = re.sub(r"\s+", " ", value).strip().split(" ")
    return " ".join(words[:_MAX_PREFIX_WORDS]).strip()
