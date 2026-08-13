"""Transactional extraction, chunking and embedding of uploaded documents."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from psycopg2.extras import execute_batch

from ..db import get_connection
from ..embeddings import encode, is_loaded
from ..settings import get_settings
from .chunking import chunk_text
from .contextual import contextual_embedding_inputs
from .extraction import ExtractedSection, extract_document

_CHUNK_MIN_CHARACTERS = 250
_CHUNK_TARGET_CHARACTERS = 850
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedChunk:
    index: int
    content: str
    page: int | None


def ingest_document(
    document_id: int,
    filename: str,
    data: bytes,
    chunk_max_characters: int = 1150,
    chunk_overlap_characters: int = 140,
) -> dict[str, int]:
    if not is_loaded():
        raise RuntimeError("Embedding model not loaded. Cannot ingest without embeddings.")

    sections = extract_document(filename, data)
    chunks = _prepare_chunks(sections, chunk_max_characters, chunk_overlap_characters)
    embedding_inputs = _embedding_inputs(filename, sections, chunks)
    vectors = encode(embedding_inputs)
    if len(vectors) != len(chunks):
        raise RuntimeError("Embedding count does not match chunk count.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM doc_chunk WHERE source_document_id = %s", (document_id,))
            execute_batch(
                cursor,
                """
                INSERT INTO doc_chunk
                    (mission_id, source_document_id, source_page, chunk_index, content, corpus_scope, embedding)
                VALUES (NULL, %s, %s, %s, %s, 'PDF', %s::vector)
                """,
                [
                    (document_id, chunk.page, chunk.index, chunk.content, vector.tolist())
                    for chunk, vector in zip(chunks, vectors)
                ],
                page_size=50,
            )

    pages = {section.page for section in sections if section.page is not None}
    page_counts = [section.page_count for section in sections if section.page_count]
    logger.info(
        "Indexed document_id=%s pages=%s chunks=%s characters=%s",
        document_id,
        max(page_counts or pages or {1}),
        len(chunks),
        sum(len(section.content) for section in sections),
    )
    return {
        "document_id": document_id,
        "page_count": max(page_counts or pages or {1}),
        "chunks_inserted": len(chunks),
        "characters_extracted": sum(len(section.content) for section in sections),
    }


def _embedding_inputs(
    filename: str,
    sections: list[ExtractedSection],
    chunks: list[PreparedChunk],
) -> list[str]:
    """Build retrieval inputs without ever mutating citation source content."""
    return contextual_embedding_inputs(
        document_label=filename,
        document_context="\n\n".join(section.content for section in sections),
        chunks=[chunk.content for chunk in chunks],
        settings=get_settings(),
    )


def _prepare_chunks(
    sections: list[ExtractedSection],
    max_characters: int,
    overlap_characters: int,
) -> list[PreparedChunk]:
    prepared: list[PreparedChunk] = []
    for section in sections:
        for content in chunk_text(
            section.content,
            max_characters,
            overlap_characters,
            target_characters=min(_CHUNK_TARGET_CHARACTERS, max_characters),
            min_characters=min(_CHUNK_MIN_CHARACTERS, max_characters),
        ):
            prepared.append(
                PreparedChunk(index=len(prepared), content=content, page=section.page)
            )
    return prepared