"""Rank missions by semantic similarity and technology-tag overlap."""

from __future__ import annotations

from ..db import execute_query
from ..embeddings import encode
from ..schemas import SimilarMission, SimilarRequest, SimilarResponse

_VECTOR_WEIGHT = 0.85
_TAG_WEIGHT = 0.15


def find_similar_missions(request: SimilarRequest) -> SimilarResponse:
    """Find missions with related chunks and technologies mentioned in the need."""
    query_vector = encode([request.description])[0].tolist()
    conditions = ["dc.embedding IS NOT NULL", "dc.corpus_scope = 'MISSION'", "dc.mission_id IS NOT NULL"]
    filter_params: list[object] = []

    if request.sector:
        conditions.append("m.sector = %s")
        filter_params.append(request.sector)
    if request.mission_type:
        conditions.append("m.mission_type = %s")
        filter_params.append(request.mission_type)

    where_clause = " AND ".join(conditions)
    query = f"""
        WITH semantic_scores AS (
            SELECT
                m.id AS mission_id,
                MAX(1 - (dc.embedding <=> %s::vector)) AS vector_score
            FROM mission m
            JOIN doc_chunk dc ON dc.mission_id = m.id
            WHERE {where_clause}
            GROUP BY m.id
        )
        SELECT
            m.id,
            m.title,
            m.sector,
            m.mission_type,
            m.technologies,
            m.year,
            m.summary,
            (
                %s * GREATEST(0.0, semantic_scores.vector_score)
                + %s * COALESCE(tag_matches.match_ratio, 0.0)
            ) AS similarity_score
        FROM semantic_scores
        JOIN mission m ON m.id = semantic_scores.mission_id
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)::double precision
                / NULLIF(cardinality(m.technologies), 0) AS match_ratio
            FROM unnest(m.technologies) AS technology
            WHERE %s ILIKE '%%' || technology || '%%'
        ) tag_matches ON true
        ORDER BY similarity_score DESC, m.id
        LIMIT %s
    """
    rows = execute_query(
        query,
        (
            str(query_vector),
            *filter_params,
            _VECTOR_WEIGHT,
            _TAG_WEIGHT,
            request.description,
            request.top_k,
        ),
    )

    return SimilarResponse(
        missions=[
            SimilarMission(
                id=row["id"],
                title=row["title"],
                sector=row["sector"],
                mission_type=row["mission_type"],
                technologies=row["technologies"],
                year=row["year"],
                summary=row["summary"],
                similarity_score=float(row["similarity_score"]),
            )
            for row in rows
        ]
    )