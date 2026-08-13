"""Ingestion pipeline: corpus JSON → chunking → embeddings → PostgreSQL.

Reads mission data, chunks document content, generates embeddings via the
embedding model, and inserts everything into the mission + doc_chunk tables.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extras import execute_batch

from ..db import get_connection
from ..embeddings import encode, is_loaded
from ..schemas import IngestMissionRequest
from ..settings import get_settings
from .chunking import chunk_text
from .contextual import contextual_embedding_inputs

logger = logging.getLogger(__name__)


def ingest_missions(
    missions: list[IngestMissionRequest],
    chunk_max_characters: int = 512,
    chunk_overlap_characters: int = 64,
) -> dict[str, int]:
    """Ingest a batch of missions into PostgreSQL.

    Returns:
        Dict with missions_inserted, chunks_inserted, chunks_with_embeddings counts.
    """
    if not is_loaded():
        raise RuntimeError("Embedding model not loaded. Cannot ingest without embeddings.")

    total_missions = 0
    total_chunks = 0
    total_embedded = 0

    for mission in missions:
        with get_connection() as conn:
            mission_id = _upsert_mission(conn, mission)
            chunks = _build_chunks(mission, mission_id, chunk_max_characters, chunk_overlap_characters)

            if chunks:
                texts = contextual_embedding_inputs(
                    document_label=mission.title,
                    document_context="\n\n".join(document.content for document in mission.documents),
                    chunks=[chunk["content"] for chunk in chunks],
                    settings=get_settings(),
                )
                vectors = encode(texts)
                if len(vectors) != len(chunks):
                    raise RuntimeError("Embedding count does not match chunk count.")

                params_list = [
                    (
                        chunk["mission_id"],
                        chunk["chunk_index"],
                        chunk["content"],
                        chunk["sector"],
                        chunk["mission_type"],
                        chunk["technologies"],
                        chunk["year"],
                        chunk["corpus_scope"],
                        vector.tolist(),
                    )
                    for chunk, vector in zip(chunks, vectors)
                ]

                with conn.cursor() as cur:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO doc_chunk
                            (mission_id, chunk_index, content, sector, mission_type, technologies, year, corpus_scope, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                        """,
                        params_list,
                        page_size=50,
                    )

                total_chunks += len(chunks)
                total_embedded += len(chunks)

        total_missions += 1

    logger.info(
        "Ingestion complete: %d missions, %d chunks, %d embeddings",
        total_missions, total_chunks, total_embedded,
    )
    return {
        "missions_inserted": total_missions,
        "chunks_inserted": total_chunks,
        "chunks_with_embeddings": total_embedded,
    }


def _upsert_mission(conn: Any, mission: IngestMissionRequest) -> int:
    """Insert a mission and return its database id.

    If a mission with the same title already exists, return its id.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM mission WHERE title = %s LIMIT 1", (mission.title,))
        existing = cur.fetchone()
        if existing:
            mission_id = existing[0]
            logger.debug("Mission '%s' already exists (id=%d), replacing chunks.", mission.title, mission_id)
            cur.execute(
                """
                UPDATE mission
                SET sector = %s,
                    mission_type = %s,
                    technologies = %s,
                    year = %s,
                    referent_tag = %s,
                    summary = %s
                WHERE id = %s
                """,
                (
                    mission.sector,
                    mission.mission_type,
                    mission.technologies,
                    mission.year,
                    mission.referent_tag,
                    mission.summary,
                    mission_id,
                ),
            )
            cur.execute("DELETE FROM doc_chunk WHERE mission_id = %s", (mission_id,))
            return mission_id

        cur.execute(
            """
            INSERT INTO mission (title, sector, mission_type, technologies, year, referent_tag, summary)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                mission.title,
                mission.sector,
                mission.mission_type,
                mission.technologies,
                mission.year,
                mission.referent_tag,
                mission.summary,
            ),
        )
        return cur.fetchone()[0]


def _build_chunks(
    mission: IngestMissionRequest,
    mission_id: int,
    max_characters: int,
    overlap_characters: int,
) -> list[dict[str, Any]]:
    """Chunk all documents of a mission into indexable pieces."""
    chunks: list[dict[str, Any]] = []
    global_index = 0

    for doc in mission.documents:
        text_chunks = chunk_text(doc.content, max_characters, overlap_characters)
        for text in text_chunks:
            chunks.append({
                "mission_id": mission_id,
                "chunk_index": global_index,
                "content": text,
                "sector": mission.sector,
                "mission_type": mission.mission_type,
                "technologies": mission.technologies,
                "year": mission.year,
                "corpus_scope": "MISSION",
            })
            global_index += 1

    return chunks
