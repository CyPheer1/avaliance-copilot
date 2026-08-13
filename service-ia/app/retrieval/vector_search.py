"""Hybrid pgvector and French full-text retrieval merged with RRF."""

from __future__ import annotations

import logging
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from ..db import execute_query, is_initialized
from ..embeddings import encode
from ..schemas import RetrievedChunk, RetrieveRequest, RetrieveResponse
from ..settings import get_settings
from .reranker import rerank

logger = logging.getLogger(__name__)

_RRF_K = 60
# Preserve a small local evidence window for the strongest pages. PDFs commonly split a
# heading, a table, and its decisive values across adjacent physical chunks. The window
# replaces unrelated tail rows; it never increases the request's final context budget.
_PAGE_SIBLING_ANCHORS = 3
_PAGE_SIBLING_MAX_PER_PAGE = 3
# Strong PDF evidence often continues on the following physical page (team table
# then financial table, or process then measured outcome). Keep a bounded
# document-local continuation window; it replaces unrelated tail context.
_ADJACENT_PAGE_MAX_PER_ANCHOR = 1
# Each returned citation must fully cover the text supplied to generation. Adjacent
# chunks remain independently retrievable until explicit multi-chunk span metadata exists.
_CONTENT_SELECT = """
            dc.content AS content,
"""


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).lower()


def _expanded_lexical_query(query: str) -> str:
    """Add broad French retrieval vocabulary for common evidence intents.

    The original terms remain intact. Added terms are deliberately generic and
    are only OR-ed by PostgreSQL FTS; semantic ranking and the cross-encoder
    still determine final relevance.
    """
    folded = _fold_text(query)
    expansions: list[str] = []
    if any(term in folded for term in ("technolog", "architecture", "mecanisme", "stack")):
        expansions.extend(("broker", "certificat", "flux", "base", "series", "temporelles", "api"))
    if any(term in folded for term in ("difficulte", "incident", "obstacle", "impact", "traitee")):
        expansions.extend(("difficultes", "incident", "parade", "remediation", "observation", "exclusions"))
    if any(term in folded for term in ("volume", "volumetr", "mesure traitee", "mesures traitees", "compteur", "resultat mesurable")):
        # Keep the retrieval architecture intact while making a metrics intent
        # lexically discoverable in result tables whose row labels differ from
        # the wording of the question.
        expansions.extend(("resultats", "indicateur", "mesures", "traitees", "debit", "soutenu", "pointe"))
    return " ".join((query, *expansions))


def _coverage_aware_selection(
    rows: list[dict],
    *,
    desired_count: int,
    min_final_chunks: int,
    max_final_chunks: int,
    reserved_chunk_ids: set[int] | None = None,
) -> list[dict]:
    """Retain independently strong evidence and page continuations.

    A page may be split into several chunks (for example a heading in one chunk
    and the decisive table row in the next). Page-level deduplication discarded
    those continuations and made an answer impossible even when its evidence was
    retrieved. Chunk identity—not page identity—is the safe deduplication key.
    """
    target = min(max(desired_count, min_final_chunks), max_final_chunks, len(rows))
    selected: list[dict] = []
    selected_ids: set[int] = set()

    for row in rows:
        chunk_id = int(row["chunk_id"])
        if chunk_id not in (reserved_chunk_ids or set()) or chunk_id in selected_ids:
            continue
        selected.append(row)
        selected_ids.add(chunk_id)
        if len(selected) == target:
            return selected

    for row in rows:
        chunk_id = int(row["chunk_id"])
        if chunk_id in selected_ids:
            continue
        selected.append(row)
        selected_ids.add(chunk_id)
        if len(selected) == target:
            break
    return selected


def _lexical_reserve_ids(rows: list[dict], reserve_count: int) -> set[int]:
    """Choose exact lexical matches from distinct pages for final evidence."""
    if reserve_count == 0:
        return set()
    selected_ids: set[int] = set()
    seen_positions: set[tuple[object, object]] = set()
    lexical_rows = sorted(
        (row for row in rows if row.get("text_score") is not None),
        key=lambda row: (-float(row["text_score"]), int(row["chunk_id"])),
    )
    for row in lexical_rows:
        position = (row.get("document_id"), row.get("page"))
        if position in seen_positions:
            continue
        selected_ids.add(int(row["chunk_id"]))
        seen_positions.add(position)
        if len(selected_ids) == reserve_count:
            break
    return selected_ids


def _protected_evidence_ids(
    rows: list[dict], *, lexical_reserve: int, safeguard_rank: int
) -> set[int]:
    """Return independently strong evidence to retain through cross-encoding.

    The lexical reserve protects exact terms from long PDFs even where RRF ranks
    them below results that appear in both branches. The broader safeguard keeps
    stable top candidates from every retrieval signal. Neither adds new rows.
    """
    protected_ids: set[int] = set()
    protected_ids.update(_lexical_reserve_ids(rows, lexical_reserve))
    if safeguard_rank:
        for score_field in ("rrf_score", "vector_score"):
            ranked = sorted(
                (row for row in rows if row.get(score_field) is not None),
                key=lambda row: (-float(row[score_field]), int(row["chunk_id"])),
            )
            protected_ids.update(int(row["chunk_id"]) for row in ranked[:safeguard_rank])
    return protected_ids


def _with_evidence_rank_safeguard(
    rows: list[dict], safeguard_rank: int, lexical_reserve: int = 0
) -> list[dict]:
    """Order protected evidence before cross-encoder-only candidates."""
    protected_ids = _protected_evidence_ids(
        rows, lexical_reserve=lexical_reserve, safeguard_rank=safeguard_rank
    )
    return sorted(
        rows,
        key=lambda row: (
            int(row["chunk_id"]) not in protected_ids,
            -float(row["score"]),
            int(row["chunk_id"]),
        ),
    )


def _rerank_candidates(
    query: str,
    rows: list[dict],
    *,
    desired_count: int,
    rerank_limit: int,
    lexical_bonus: float,
    lexical_evidence_reserve: int,
    evidence_rank_safeguard: int,
    min_final_chunks: int,
    max_final_chunks: int,
) -> list[dict]:
    """Rerank the top RRF candidates, then retain coverage-aware evidence."""
    lexical_reserved_ids = _lexical_reserve_ids(rows, lexical_evidence_reserve)
    protected_ids = _protected_evidence_ids(
        rows,
        lexical_reserve=lexical_evidence_reserve,
        safeguard_rank=evidence_rank_safeguard,
    )
    protected_rows = [row for row in rows if int(row["chunk_id"]) in protected_ids]
    unprotected_rows = [row for row in rows if int(row["chunk_id"]) not in protected_ids]
    rerank_pool = (protected_rows + unprotected_rows)[:rerank_limit]
    if not rerank_pool:
        return []

    scores = rerank(query, [str(row["content"]) for row in rerank_pool])
    rescored: list[dict] = []
    for row, reranker_score in zip(rerank_pool, scores, strict=True):
        lexical_score = float(row.get("text_score") or 0.0)
        final_score = reranker_score + lexical_bonus * lexical_score
        rescored.append(
            {
                **row,
                "reranker_score": reranker_score,
                "lexical_bonus_score": lexical_bonus * lexical_score,
                "score": final_score,
            }
        )
    rescored.sort(key=lambda row: (-float(row["score"]), int(row["chunk_id"])))
    rescored = _with_evidence_rank_safeguard(
        rescored,
        evidence_rank_safeguard,
        lexical_reserve=lexical_evidence_reserve,
    )
    selected = _coverage_aware_selection(
        rescored,
        desired_count=desired_count,
        min_final_chunks=min_final_chunks,
        max_final_chunks=max_final_chunks,
        reserved_chunk_ids=lexical_reserved_ids,
    )
    # The rerank pool is intentionally bounded for latency; siblings can be in the
    # wider hybrid candidate set (as happens for continuation table rows). Use that
    # scored pool only for local-page expansion, never for global selection.
    return _with_page_sibling_windows(rows, selected)


def _bounded_relevance(vector_score: float | None, text_score: float | None) -> float:
    """Return bounded semantic relevance, separate from lexical and RRF scores."""
    if vector_score is None:
        return 0.0
    return max(0.0, min(1.0, float(vector_score)))


def _page_sibling_rows(
    rows: list[dict],
    *,
    anchor_rows: list[dict],
    max_per_page: int = _PAGE_SIBLING_MAX_PER_PAGE,
) -> list[dict]:
    """Return nearby chunks from anchor pages, ordered by physical chunk position.

    ``rows`` is deliberately the candidate pool already scored by hybrid retrieval;
    fetching arbitrary database siblings would bypass corpus and ranking constraints.
    """
    anchor_pages = {
        (row.get("document_id"), row.get("page"))
        for row in anchor_rows
        if row.get("document_id") is not None and row.get("page") is not None
    }
    siblings: list[dict] = []
    for document_id, page in anchor_pages:
        page_rows = sorted(
            (
                row
                for row in rows
                if (row.get("document_id"), row.get("page")) == (document_id, page)
            ),
            key=lambda row: (int(row.get("chunk_index", row["chunk_id"])), int(row["chunk_id"])),
        )
        anchor_ids = {
            int(row["chunk_id"])
            for row in anchor_rows
            if (row.get("document_id"), row.get("page")) == (document_id, page)
        }
        anchor_positions = [
            index for index, row in enumerate(page_rows) if int(row["chunk_id"]) in anchor_ids
        ]
        # A page with no additional chunk has no local context to contribute.
        # Skipping it prevents one-page anchors from displacing another page's
        # decisive continuation during the replacement pass.
        if not any(int(row["chunk_id"]) not in anchor_ids for row in page_rows):
            continue
        # Keep each anchor and its immediate physical continuation rather than
        # truncating the page before the continuation can be considered.
        start = min(anchor_positions, default=0)
        siblings.extend(page_rows[start : start + max_per_page])
    return siblings


def _adjacent_page_rows(rows: list[dict], *, anchor_rows: list[dict]) -> list[dict]:
    """Return candidate-pool continuations from following physical pages."""
    anchors = {
        (row.get("document_id"), int(row["page"]) + 1)
        for row in anchor_rows
        if row.get("document_id") is not None and row.get("page") is not None
    }
    continuations: list[dict] = []
    for document_id, page in sorted(anchors, key=lambda value: (int(value[0]), value[1])):
        page_rows = sorted(
            (
                row for row in rows
                if (row.get("document_id"), row.get("page")) == (document_id, page)
            ),
            key=lambda row: (
                -float(row.get("score", 0.0)),
                int(row.get("chunk_index", row["chunk_id"])),
                int(row["chunk_id"]),
            ),
        )
        continuations.extend(page_rows[:_ADJACENT_PAGE_MAX_PER_ANCHOR])
    return continuations


def _fetch_following_page_rows(anchor_rows: list[dict]) -> list[dict]:
    """Fetch a bounded physical continuation for strong PDF evidence pages.

    Hybrid retrieval ranks the anchor page, but its next page can contain a
    logically separate table (for example the cost row for a named team member)
    and therefore never enter either top-N branch. This query is constrained to
    the selected source document and immediately following page, ordered by the
    durable ingestion ``chunk_index``. It is generic document navigation, not a
    question, client, or answer lookup.
    """
    anchor_by_position = {
        (int(row["document_id"]), int(row["page"]) + 1): row
        for row in anchor_rows
        if row.get("document_id") is not None and row.get("page") is not None
    }
    if not anchor_by_position or not is_initialized():
        return []

    positions = sorted(anchor_by_position)
    values_sql = ", ".join(["(%s, %s)"] * len(positions))
    params: list[object] = [item for position in positions for item in position]
    query = f"""
        WITH requested_pages(document_id, page) AS (VALUES {values_sql}),
        ranked AS (
            SELECT
                dc.id AS chunk_id,
                dc.mission_id,
                m.title AS mission_title,
                dc.source_document_id AS document_id,
                sd.original_filename AS document_name,
                dc.source_page AS page,
                dc.chunk_index AS chunk_index,
                dc.sector,
                dc.mission_type,
                dc.corpus_scope,
                dc.content AS content,
                ROW_NUMBER() OVER (
                    PARTITION BY dc.source_document_id, dc.source_page
                    ORDER BY dc.chunk_index, dc.id
                ) AS page_rank
            FROM doc_chunk dc
            JOIN requested_pages rp
              ON rp.document_id = dc.source_document_id AND rp.page = dc.source_page
            LEFT JOIN mission m ON m.id = dc.mission_id
            JOIN source_document sd ON sd.id = dc.source_document_id
            WHERE dc.corpus_scope = 'PDF' AND sd.status = 'INDEXED'
        )
        SELECT * FROM ranked WHERE page_rank <= %s
        ORDER BY document_id, page, chunk_index, chunk_id
    """
    fetched = execute_query(query, tuple(params + [_PAGE_SIBLING_MAX_PER_PAGE]))
    enriched: list[dict] = []
    for row in fetched:
        position = (int(row["document_id"]), int(row["page"]))
        # The database join guarantees this in production. Keep this defensive
        # guard so an unexpected adapter/mock row cannot bypass source-scoped
        # continuation constraints.
        anchor = anchor_by_position.get(position)
        if anchor is None:
            continue
        anchor_score = float(anchor.get("score", 0.0))
        enriched.append({
            **row,
            "vector_score": None,
            "text_score": None,
            "rrf_score": float(anchor.get("rrf_score", anchor_score)),
            "relevance_score": float(anchor.get("relevance_score", 0.0)),
            # Keep the page continuation behind its selected anchor while
            # allowing it to replace unrelated tail context.
            "score": anchor_score - 0.0001,
        })
    return enriched


def _with_page_sibling_windows(rows: list[dict], selected: list[dict]) -> list[dict]:
    """Replace unrelated tail context with local companions of strong evidence."""
    if not selected:
        return selected
    anchors = selected[:_PAGE_SIBLING_ANCHORS]
    sibling_rows = _page_sibling_rows(rows, anchor_rows=anchors)
    # Prefer existing hybrid candidates, then fill only missing immediate-page
    # continuations through the bounded, source-scoped navigation query.
    continuation_rows = _adjacent_page_rows(rows, anchor_rows=anchors)
    known_continuation_ids = {int(row["chunk_id"]) for row in continuation_rows}
    requested_positions = {
        (row.get("document_id"), int(row["page"]) + 1)
        for row in anchors
        if row.get("document_id") is not None and row.get("page") is not None
    }
    present_positions = {
        (row.get("document_id"), row.get("page")) for row in continuation_rows
    }
    missing_anchors = [
        row for row in anchors
        if row.get("document_id") is not None
        and row.get("page") is not None
        and (row.get("document_id"), int(row["page"]) + 1) not in present_positions
    ]
    if missing_anchors:
        continuation_rows.extend(
            row
            for row in _fetch_following_page_rows(missing_anchors)
            if int(row["chunk_id"]) not in known_continuation_ids
        )
    companion_rows = sibling_rows + continuation_rows
    if not companion_rows:
        return selected

    target = len(selected)
    selected_ids = {int(row["chunk_id"]) for row in selected}
    result = list(selected)
    # Add source-order siblings first; trim the lowest ranked unrelated tail rows.
    for sibling in companion_rows:
        sibling_id = int(sibling["chunk_id"])
        if sibling_id in selected_ids:
            continue
        anchor_key = (sibling.get("document_id"), sibling.get("page"))
        replace_index = next(
            (
                index
                for index in range(len(result) - 1, -1, -1)
                if (result[index].get("document_id"), result[index].get("page"))
                != anchor_key
            ),
            None,
        )
        if replace_index is None:
            continue
        removed = result[replace_index]
        selected_ids.remove(int(removed["chunk_id"]))
        result[replace_index] = sibling
        selected_ids.add(sibling_id)

    # Evidence pages are compacted in document order, while unrelated evidence keeps
    # its relevance ordering. This makes table continuations readable to the selector.
    page_positions: dict[tuple[object, object], list[int]] = {}
    for index, row in enumerate(result):
        page_positions.setdefault((row.get("document_id"), row.get("page")), []).append(index)
    for indexes in page_positions.values():
        if len(indexes) > 1:
            ordered = sorted(
                (result[index] for index in indexes),
                key=lambda row: (int(row.get("chunk_index", row["chunk_id"])), int(row["chunk_id"])),
            )
            for index, row in zip(indexes, ordered, strict=True):
                result[index] = row
    return result[:target]


@lru_cache(maxsize=256)
def _query_embedding(query: str) -> tuple[float, ...]:
    """Cache CPU-heavy query embeddings while leaving database results fresh."""
    return tuple(float(value) for value in encode([query])[0])


def reciprocal_rank_fusion(
    rankings: list[list[dict]],
    *,
    rrf_k: int = _RRF_K,
    top_k: int,
    weights: tuple[float, ...] | None = None,
) -> list[dict]:
    """Merge ranked chunk lists using Reciprocal Rank Fusion."""
    fused: dict[int, dict] = {}
    scores: dict[int, float] = {}

    score_fields = ("vector_score", "text_score")
    for ranking_index, ranking in enumerate(rankings):
        weight = weights[ranking_index] if weights else 1.0
        for rank, row in enumerate(ranking, start=1):
            chunk_id = int(row["chunk_id"])
            ranking_score = float(row.get("ranking_score", 0.0))
            if chunk_id not in fused:
                fused[chunk_id] = {
                    key: value for key, value in row.items() if key != "ranking_score"
                }
            if ranking_index < len(score_fields):
                fused[chunk_id][score_fields[ranking_index]] = ranking_score
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (rrf_k + rank)

    ordered_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:top_k]
    return [
        {
            **fused[chunk_id],
            "score": scores[chunk_id],
            "rrf_score": scores[chunk_id],
            "relevance_score": _bounded_relevance(
                fused[chunk_id].get("vector_score"),
                fused[chunk_id].get("text_score"),
            ),
        }
        for chunk_id in ordered_ids
    ]


def _metadata_filters(request: RetrieveRequest) -> tuple[list[str], list[object]]:
    conditions: list[str] = []
    params: list[object] = []

    if request.corpus_scope == "PDF":
        conditions.extend([
            "dc.corpus_scope = %s",
            "dc.source_document_id IS NOT NULL",
            "sd.status = 'INDEXED'",
        ])
        params.append("PDF")
    elif request.corpus_scope == "MISSION":
        conditions.extend([
            "dc.corpus_scope = %s",
            "dc.mission_id IS NOT NULL",
        ])
        params.append("MISSION")
    else:
        conditions.append("dc.corpus_scope = %s")
        params.append(request.corpus_scope)

    if request.sector:
        conditions.append("dc.sector = %s")
        params.append(request.sector)
    if request.mission_type:
        conditions.append("dc.mission_type = %s")
        params.append(request.mission_type)
    if request.year:
        conditions.append("dc.year = %s")
        params.append(request.year)

    return conditions, params


def _rows_to_chunks(rows: list[dict], request: RetrieveRequest) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            mission_id=row["mission_id"],
            mission_title=row["mission_title"],
            document_id=row.get("document_id"),
            document_name=row.get("document_name"),
            page=row.get("page"),
            sector=row["sector"],
            mission_type=row["mission_type"],
            corpus_scope=row["corpus_scope"],
            request_id=request.request_id,
            content=row["content"],
            score=float(row["score"]),
            rrf_score=float(row["rrf_score"]),
            relevance_score=float(row["relevance_score"]),
            vector_score=(
                float(row["vector_score"])
                if row.get("vector_score") is not None
                else None
            ),
            text_score=(
                float(row["text_score"])
                if row.get("text_score") is not None
                else None
            ),
        )
        for row in rows
    ]


def vector_search_with_trace(request: RetrieveRequest) -> tuple[RetrieveResponse, dict[str, object]]:
    """Return production retrieval response plus deterministic trace data."""
    settings = get_settings()
    query_vector = list(_query_embedding(request.query))
    vector_literal = str(query_vector)
    conditions, filter_params = _metadata_filters(request)
    # A title in a user question is useful for ranking but not a safe database
    # predicate: query wording and original filenames routinely differ. Applying
    # a LIKE filter here created false no-evidence outcomes before reranking.
    candidate_limit = settings.retrieval_candidate_limit
    final_chunk_count = min(
        max(request.top_k, settings.retrieval_min_final_chunks),
        settings.retrieval_max_final_chunks,
    )

    vector_conditions = [
        "dc.embedding IS NOT NULL",
        *conditions,
    ]
    vector_where = " AND ".join(vector_conditions)
    vector_query = f"""
        SELECT
            dc.id AS chunk_id,
            dc.mission_id,
            m.title AS mission_title,
            dc.source_document_id AS document_id,
            sd.original_filename AS document_name,
            dc.source_page AS page,
            dc.chunk_index AS chunk_index,
            dc.sector,
            dc.mission_type,
            dc.corpus_scope,
            {_CONTENT_SELECT}
            1 - (dc.embedding <=> %s::vector) AS ranking_score
        FROM doc_chunk dc
        LEFT JOIN mission m ON m.id = dc.mission_id
        LEFT JOIN source_document sd ON sd.id = dc.source_document_id
        WHERE {vector_where}
        ORDER BY dc.embedding <=> %s::vector
        LIMIT %s
    """
    vector_params = (
        vector_literal,
        *filter_params,
        vector_literal,
        candidate_limit,
    )

    text_conditions = [*conditions, "dc.ts @@ lexical_query.value"]
    text_where = " AND ".join(text_conditions)
    text_query = f"""
        SELECT
            dc.id AS chunk_id,
            dc.mission_id,
            m.title AS mission_title,
            dc.source_document_id AS document_id,
            sd.original_filename AS document_name,
            dc.source_page AS page,
            dc.chunk_index AS chunk_index,
            dc.sector,
            dc.mission_type,
            dc.corpus_scope,
            {_CONTENT_SELECT}
            ts_rank_cd(dc.ts, lexical_query.value) AS ranking_score
        FROM doc_chunk dc
        LEFT JOIN mission m ON m.id = dc.mission_id
        LEFT JOIN source_document sd ON sd.id = dc.source_document_id
        CROSS JOIN LATERAL (
            SELECT to_tsquery(
                'french',
                array_to_string(
                    tsvector_to_array(to_tsvector('french', %s)),
                    ' | '
                )
            ) AS value
        ) lexical_query
        WHERE {text_where}
        ORDER BY ranking_score DESC, dc.id
        LIMIT %s
    """
    text_params = (
        _expanded_lexical_query(request.query),
        *filter_params,
        candidate_limit,
    )

    vector_started = time.perf_counter()
    text_started = time.perf_counter()
    vector_local_settings = {
        "hnsw.ef_search": str(settings.retrieval_hnsw_ef_search),
        "hnsw.iterative_scan": settings.retrieval_hnsw_iterative_scan,
    }
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="hybrid-search") as executor:
        vector_future = executor.submit(
            execute_query,
            vector_query,
            vector_params,
            local_settings=vector_local_settings,
        )
        text_future = executor.submit(execute_query, text_query, text_params)
        vector_rows = vector_future.result()
        vector_elapsed_ms = (time.perf_counter() - vector_started) * 1000
        text_rows = text_future.result()
        text_elapsed_ms = (time.perf_counter() - text_started) * 1000

    fusion_started = time.perf_counter()
    candidate_rows = reciprocal_rank_fusion(
        [vector_rows, text_rows],
        rrf_k=settings.retrieval_rrf_k,
        top_k=candidate_limit,
        weights=(settings.retrieval_vector_weight, settings.retrieval_text_weight),
    )
    fusion_elapsed_ms = (time.perf_counter() - fusion_started) * 1000

    rerank_started = time.perf_counter()
    rows = _rerank_candidates(
        request.query,
        candidate_rows,
        desired_count=final_chunk_count,
        rerank_limit=settings.retrieval_rerank_limit,
        lexical_bonus=settings.retrieval_rerank_lexical_bonus,
        lexical_evidence_reserve=settings.retrieval_lexical_evidence_reserve,
        evidence_rank_safeguard=settings.retrieval_evidence_rank_safeguard,
        min_final_chunks=settings.retrieval_min_final_chunks,
        max_final_chunks=settings.retrieval_max_final_chunks,
    )
    rerank_elapsed_ms = (time.perf_counter() - rerank_started) * 1000

    chunks = _rows_to_chunks(rows, request)

    logger.info(
        "Hybrid retrieval query=%r results=%s",
        request.query,
        [
            {
                "chunk_id": chunk.chunk_id,
                "page": chunk.page,
                "vector_score": chunk.vector_score,
                "text_score": chunk.text_score,
                "rrf_score": chunk.rrf_score,
                "relevance_score": chunk.relevance_score,
            }
            for chunk in chunks
        ],
    )

    response = RetrieveResponse(
        query=request.query,
        chunks=chunks,
        total_found=len(chunks),
    )
    trace: dict[str, object] = {
        "query": request.query,
        "request_id": request.request_id,
        "corpus_scope": request.corpus_scope,
        "top_k": request.top_k,
        "candidate_limit": candidate_limit,
        "metadata_filters": list(conditions),
        "metadata_filter_params": list(filter_params),
        "vector_elapsed_ms": round(vector_elapsed_ms, 3),
        "text_elapsed_ms": round(text_elapsed_ms, 3),
        "fusion_elapsed_ms": round(fusion_elapsed_ms, 3),
        "rerank_elapsed_ms": round(rerank_elapsed_ms, 3),
        "vector_rows": vector_rows,
        "text_rows": text_rows,
        "candidate_rows": candidate_rows,
        "final_rows": rows,
    }
    return response, trace


def vector_search(request: RetrieveRequest) -> RetrieveResponse:
    """Return chunks ranked by vector and full-text Reciprocal Rank Fusion."""
    response, _ = vector_search_with_trace(request)
    return response
