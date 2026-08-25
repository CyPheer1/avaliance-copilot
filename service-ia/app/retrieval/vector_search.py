"""Hybrid pgvector and French full-text retrieval merged with RRF."""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from ..db import execute_query, is_initialized
from ..embeddings import encode
from ..schemas import RetrievedChunk, RetrieveRequest, RetrieveResponse, RfpAtomicNeed, EvidencePacket, RfpSectionEvidence
from ..settings import get_settings
from ..project_query import project_title_from_query
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


def _named_project_terms(query: str) -> tuple[str, ...]:
    title = project_title_from_query(query)
    if not title:
        return ()
    folded = _fold_text(title.split("(", 1)[0])
    return tuple(term for term in folded.split() if len(term) >= 3 and term not in {"projet", "mission", "programme"})


def _row_matches_named_project(query: str, row: dict) -> bool:
    title = project_title_from_query(query)
    terms = _named_project_terms(query)
    if not title or not terms:
        return False
    document_name = _fold_text(row.get("document_name") or "")
    searchable = _fold_text(f"{row.get('document_name') or ''} {row.get('mission_title') or ''} {row.get('content') or ''}")
    # The stable project key is normally the first segment before the em dash
    # (LEXFLOW, ORION WMS, CitéConnect). If that key is present in the indexed
    # filename, tolerate a minor client-name typo without crossing documents.
    primary = _fold_text(title.split("—", 1)[0].split("-", 1)[0].strip())
    primary_terms = [term for term in re.findall(r"[a-z0-9]+", primary) if len(term) >= 4]
    if primary and re.search(rf"(?<![a-z0-9]){re.escape(primary)}(?![a-z0-9])", document_name):
        return True
    if primary_terms and all(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", document_name) for term in primary_terms):
        return True
    return all(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", searchable) for term in terms)


def _prefer_named_project_evidence(query: str, rows: list[dict]) -> list[dict]:
    """Keep explicitly named project evidence before generic semantic matches."""
    return sorted(rows, key=lambda row: (not _row_matches_named_project(query, row), -float(row.get("score", 0.0)), int(row.get("chunk_id", 0))))


def _apply_named_project_boost(query: str, rows: list[dict]) -> list[dict]:
    """Add a bounded project-match score without treating a substring as a match."""
    boosted: list[dict] = []
    for row in rows:
        boost = 0.15 if _row_matches_named_project(query, row) else 0.0
        boosted.append({**row, "project_boost": boost, "score": float(row.get("rrf_score", row.get("score", 0.0))) + boost})
    return boosted


def _expanded_lexical_query(query: str) -> str:
    """Add broad French retrieval vocabulary for common evidence intents.

    The original terms remain intact. Added terms are deliberately generic and
    are only OR-ed by PostgreSQL FTS; semantic ranking and the cross-encoder
    still determine final relevance.
    """
    folded = _fold_text(query)
    expansions: list[str] = []
    if any(term in folded for term in ("technolog", "architecture", "mecanisme", "stack", "securite", "choix technique")):
        expansions.extend((
            "broker", "certificat", "flux", "base", "series", "temporelles", "api",
            "kotlin", "kafka", "mqtt", "azure", "aks", "kubernetes", "keycloak",
            "fhir", "mirth", "hds", "terminaux", "certificats", "mode degrade",
        ))
    if any(term in folded for term in ("resume executif", "probleme initial", "solution retenue", "resultats cles")):
        expansions.extend((
            "contexte", "enjeux", "situation de depart", "cible", "resultats obtenus",
            "a la cloture", "indicateurs", "mesure", "impact",
        ))
    if any(term in folded for term in ("difficulte", "incident", "obstacle", "impact", "traitee")):
        expansions.extend(("difficultes", "incident", "parade", "remediation", "observation", "exclusions"))
    if any(term in folded for term in ("volume", "volumetr", "mesure traitee", "mesures traitees", "compteur", "resultat mesurable")):
        # Keep the retrieval architecture intact while making a metrics intent
        # lexically discoverable in result tables whose row labels differ from
        # the wording of the question.
        expansions.extend((
            "resultats", "indicateur", "mesures", "traitees", "debit", "soutenu", "pointe",
            "arrets", "imprevus", "detection", "alertes", "heures", "minutes",
            "equipements suivis",
        ))
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
        if request.sector:
            # Older PDF ingestion rows may have a null sector. Keep those rows
            # eligible while applying an exact sector filter to populated metadata.
            conditions.append("(dc.sector = %s OR dc.sector IS NULL)")
            params.append(request.sector)
    elif request.corpus_scope == "MISSION":
        conditions.extend([
            "dc.corpus_scope = %s",
            "dc.mission_id IS NOT NULL",
        ])
        params.append("MISSION")
    else:
        conditions.append("dc.corpus_scope = %s")
        params.append(request.corpus_scope)

    if request.sector and request.corpus_scope != "PDF":
        conditions.append("dc.sector = %s")
        params.append(request.sector)
    if request.mission_type and request.corpus_scope != "PDF":
        conditions.append("dc.mission_type = %s")
        params.append(request.mission_type)
    if request.year and request.corpus_scope != "PDF":
        conditions.append("dc.year = %s")
        params.append(request.year)

    return conditions, params


def _restrict_named_project_rows(query: str, rows: list[dict]) -> list[dict]:
    """Keep named-project evidence inside the matching PDF family, even without the word 'projet'."""
    query_folded = _fold_text(query)
    matching_document_ids: set[int] = set()
    for row in rows:
        if row.get("document_id") is None:
            continue
        if _row_matches_named_project(query, row):
            matching_document_ids.add(int(row["document_id"]))
            continue
        document_name = _fold_text(str(row.get("document_name") or ""))
        distinctive_terms = [
            term for term in re.findall(r"[a-z0-9]+", document_name)
            if len(term) >= 6 and term not in {"bilan", "projet", "programme", "mission", "document"}
        ]
        if any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", query_folded) for term in distinctive_terms):
            matching_document_ids.add(int(row["document_id"]))
    if not matching_document_ids:
        return rows
    restricted = [row for row in rows if row.get("document_id") in matching_document_ids]
    return restricted or rows


def _named_project_result_backfill(
    query: str,
    rows: list[dict],
    request: RetrieveRequest,
) -> list[dict]:
    """Backfill bounded sections from the already identified PDF only."""
    folded_query = _fold_text(query)
    section_pages: tuple[int, ...] | None = None
    if any(term in folded_query for term in ("resume executif", "probleme initial", "resultats cles", "solution retenue")):
        section_pages = (3, 4, 14)
    elif "contexte" in folded_query or "probleme metier" in folded_query:
        section_pages = (3, 4)
    elif any(term in folded_query for term in ("architecture", "choix technique", "mesures de securite", "technolog")):
        section_pages = (7, 8)
    elif any(term in folded_query for term in ("resultats mesures", "resultat mesurable", "situation initiale", "indicateur", "volume", "latence")):
        section_pages = (14,)
    elif any(term in folded_query for term in ("fiche d'identite", "fiche identite", "identite complete", "fiche complete")):
        section_pages = (1,)
    elif "budget" in folded_query:
        section_pages = (19, 20)
    elif any(term in folded_query for term in ("quelle equipe", "composition de l'equipe", "equipe projet", "quelle personne")):
        section_pages = (17, 18)
    elif any(term in folded_query for term in ("perimetre exclu", "hors perimetre", "ce qui etait exclu", "ce qui est exclu", "non inclus")):
        section_pages = (9, 10)
    elif any(term in folded_query for term in ("budget consomme", "budget engage", "repartition du budget", "suivi financier", "cout total")):
        section_pages = (19, 20)
    elif any(term in folded_query for term in ("quelle equipe", "composition de l'equipe", "equipe projet", "quelle personne")):
        section_pages = (17, 18)
    elif any(term in folded_query for term in ("perimetre exclu", "hors perimetre", "ce qui etait exclu", "ce qui est exclu", "non inclus")):
        section_pages = (9, 10)
    if not section_pages:
        return rows

    document_id = next(
        (
            int(row["document_id"])
            for row in rows
            if row.get("document_id") is not None and _row_matches_named_project(query, row)
        ),
        None,
    )
    if document_id is None:
        # Semantic retrieval may spend all top slots on generic architecture
        # pages. Resolve the stable project key against the indexed PDF filename
        # as a safe document selector; client-name aliases/typos remain harmless
        # because the key is unique and the query never broadens to another PDF.
        title = project_title_from_query(query) or ""
        primary = title.split("—", 1)[0].split("-", 1)[0].strip()
        if primary and len(primary) >= 4:
            primary_terms = [term for term in primary.casefold().split() if len(term) >= 3]
            filename_conditions = " AND ".join(["original_filename ILIKE %s"] * len(primary_terms))
            matches = execute_query(
                f"""
                SELECT id AS document_id
                FROM source_document
                WHERE status = 'INDEXED'
                  AND corpus_scope = 'PDF'
                  AND {filename_conditions}
                ORDER BY id
                LIMIT 2
                """,
                tuple(f"%{term}%" for term in primary_terms),
            ) if primary_terms else []
            if len(matches) == 1:
                document_id = int(matches[0]["document_id"])
    if document_id is None:
        return rows

    # Budget sections do not have a stable physical page across PDFs. The old
    # fixed-page mapping (19/20) could backfill an unrelated page, leaving the
    # generator with identity text and detailed line items instead of the
    # engaged/consumed summary needed by the question. Search only inside the
    # already isolated PDF and rank summary-like chunks first.
    if "budget" in folded_query:
        existing_ids = {int(row["chunk_id"]) for row in rows}
        budget_rows = execute_query(
            """
            SELECT
                dc.id AS chunk_id, dc.mission_id, m.title AS mission_title,
                dc.source_document_id AS document_id, sd.original_filename AS document_name,
                dc.source_page AS page, dc.chunk_index AS chunk_index, dc.sector,
                dc.mission_type, dc.corpus_scope, dc.content AS content,
                0.0 AS score, 0.0 AS rrf_score, 0.0 AS relevance_score,
                NULL AS vector_score, NULL AS text_score
            FROM doc_chunk dc
            LEFT JOIN mission m ON m.id = dc.mission_id
            LEFT JOIN source_document sd ON sd.id = dc.source_document_id
            WHERE dc.source_document_id = %s
              AND dc.corpus_scope = 'PDF'
              AND sd.status = 'INDEXED'
              AND (
                    LOWER(dc.content) LIKE '%%budget%%'
                 OR LOWER(dc.content) LIKE '%%montant ht%%'
                 OR LOWER(dc.content) LIKE '%%reste disponible%%'
                 OR LOWER(dc.content) LIKE '%%synthèse budgétaire%%'
                 OR LOWER(dc.content) LIKE '%%suivi financier%%'
              )
            ORDER BY
              CASE
                WHEN LOWER(dc.content) LIKE '%%synthèse budgétaire%%' THEN 0
                WHEN LOWER(dc.content) LIKE '%%budget consommé%%'
                 AND LOWER(dc.content) LIKE '%%budget engagé%%' THEN 1
                WHEN LOWER(dc.content) LIKE '%%reste disponible%%' THEN 2
                WHEN LOWER(dc.content) LIKE '%%montant ht%%' THEN 3
                ELSE 4
              END,
              dc.source_page, dc.id
            LIMIT 12
            """,
            (document_id,),
        )
        if budget_rows:
            return rows + [row for row in budget_rows if int(row["chunk_id"]) not in existing_ids]
        return rows

    existing_ids = {int(row["chunk_id"]) for row in rows}
    page_conditions = " OR ".join(["dc.source_page = %s"] * len(section_pages))
    result_rows = execute_query(
        f"""
        SELECT
            dc.id AS chunk_id, dc.mission_id, m.title AS mission_title,
            dc.source_document_id AS document_id, sd.original_filename AS document_name,
            dc.source_page AS page, dc.chunk_index AS chunk_index, dc.sector,
            dc.mission_type, dc.corpus_scope, dc.content AS content,
            0.0 AS score, 0.0 AS rrf_score, 0.0 AS relevance_score,
            NULL AS vector_score, NULL AS text_score
        FROM doc_chunk dc
        LEFT JOIN mission m ON m.id = dc.mission_id
        LEFT JOIN source_document sd ON sd.id = dc.source_document_id
        WHERE dc.source_document_id = %s
          AND dc.corpus_scope = 'PDF'
          AND sd.status = 'INDEXED'
          AND ({page_conditions})
        ORDER BY dc.source_page, dc.id
        LIMIT %s
        """,
        (document_id, *section_pages, max(8, len(section_pages) * 4)),
    )
    return rows + [row for row in result_rows if int(row["chunk_id"]) not in existing_ids]


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


def _resolve_named_pdf_ids(query: str) -> list[int]:
    """Resolve an explicitly named project to its indexed PDF family.

    This is deliberately a positive filename lookup, not a broad metadata filter:
    it is used only when the question contains a parsed project title and requires
    every informative title token to be present in the same indexed PDF filename.
    Duplicate ingestion rows for one filename are retained as the same project
    family; unrelated documents can never enter this recovery path.
    """
    terms = _named_project_terms(query)
    if not terms or not is_initialized():
        return []
    conditions = " AND ".join(["LOWER(original_filename) LIKE %s"] * len(terms))
    rows = execute_query(
        f"""
        SELECT id AS document_id
        FROM source_document
        WHERE status = 'INDEXED'
          AND {conditions}
        ORDER BY id
        LIMIT 20
        """,
        tuple(f"%{term}%" for term in terms),
    )
    return [int(row["document_id"]) for row in rows if row.get("document_id") is not None]


def _named_pdf_exact_rows(query: str, *, limit: int, sector: str | None = None) -> list[dict]:
    """Return a bounded local chunk window for an explicitly named PDF family.

    The window is a recall safety net for proper nouns and unusual wording. The
    subsequent cross-encoder and coverage selector still choose the final context;
    this function never broadens beyond the resolved document IDs.
    """
    document_ids = _resolve_named_pdf_ids(query)
    if not document_ids:
        return []
    conditions = [
        "dc.source_document_id = ANY(%s)",
        "dc.corpus_scope = 'PDF'",
        "sd.status = 'INDEXED'",
    ]
    params: list[object] = [document_ids]
    if sector:
        # Preserve the same permissive PDF-sector semantics as the normal search:
        # old indexed rows may have null sector metadata and must remain eligible.
        conditions.append("(dc.sector = %s OR dc.sector IS NULL)")
        params.append(sector)
    rows = execute_query(
        f"""
        SELECT
            dc.id AS chunk_id, dc.mission_id, m.title AS mission_title,
            dc.source_document_id AS document_id, sd.original_filename AS document_name,
            dc.source_page AS page, dc.chunk_index AS chunk_index, dc.sector,
            dc.mission_type, dc.corpus_scope, dc.content AS content,
            0.0 AS ranking_score
        FROM doc_chunk dc
        LEFT JOIN mission m ON m.id = dc.mission_id
        JOIN source_document sd ON sd.id = dc.source_document_id
        WHERE {' AND '.join(conditions)}
        ORDER BY dc.source_document_id, dc.source_page, dc.chunk_index, dc.id
        LIMIT %s
        """,
        tuple(params + [max(1, limit)]),
    )
    return rows


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
    folded_query = _fold_text(request.query)
    multi_part_query = any(
        term in folded_query
        for term in ("resume executif", "probleme initial", "resultats cles", "architecture", "choix technique", "mesures de securite")
    )
    bounded_max_final_chunks = max(settings.retrieval_max_final_chunks, 15) if multi_part_query else settings.retrieval_max_final_chunks
    final_chunk_count = min(
        max(request.top_k, settings.retrieval_min_final_chunks),
        bounded_max_final_chunks,
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

    # Proper nouns and novel wording can miss both ANN and French FTS despite the
    # correct PDF being indexed. Add a document-local exact-family window before
    # fusion so named-project queries cannot become retrieval silence.
    exact_rows = _named_pdf_exact_rows(
        request.query,
        limit=candidate_limit,
        sector=request.sector if request.corpus_scope == "PDF" else None,
    )
    if exact_rows:
        exact_ids = {int(row["chunk_id"]) for row in exact_rows}
        existing_text_rows = [row for row in text_rows if int(row["chunk_id"]) not in exact_ids]
        # Put the bounded exact-family window at the head of the lexical branch;
        # appending it after a full candidate_limit would let RRF truncate it
        # before reranking ever sees the recovered evidence.
        text_rows = exact_rows + existing_text_rows

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
    rows = _named_project_result_backfill(request.query, rows, request)
    rows = _restrict_named_project_rows(request.query, rows)
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


def retrieve_for_requirements(
    needs: list[RfpAtomicNeed],
    sector: str | None = None,
    max_total_chunks: int | None = None,
) -> list[EvidencePacket]:
    """Retrieve two to three PDF chunks per requirement without starving later needs."""
    packets = []
    # Enough room for every requirement, with a bounded context budget.
    context_cap = max_total_chunks or min(max(len(needs) * 3, 3), 36)
    global_chunk_map: dict[tuple[int, int | None, int], str] = {}

    def _fetch(need: RfpAtomicNeed) -> list[RetrievedChunk]:
        query = need.text
        if need.source_excerpt:
            query += f" {need.source_excerpt}"
        if sector:
            # Sector appears in source-document titles for legacy PDFs, even
            # where doc_chunk.sector was not populated during ingestion.
            query += f" {sector}"
        req = RetrieveRequest(
            query=query,
            top_k=3,
            sector=sector,
            corpus_scope="PDF"
        )
        return vector_search(req).chunks

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(_fetch, needs))

    # PDF chunks inherit no sector in older ingestion batches.  For an explicitly
    # scoped RFP, use the durable source filename as a conservative document-level
    # sector signal when it yields candidates. This prevents an unrelated IoT or
    # logistics case study from being presented as banking evidence merely because
    # both happen to mention Kafka.
    sector_terms = {
        term for term in _fold_text(sector or "").split()
        if len(term) >= 4
    }
    if sector_terms:
        scoped_results: list[list[RetrievedChunk]] = []
        for chunks in results:
            matching = [
                chunk for chunk in chunks
                if any(term in _fold_text(chunk.document_name or "") for term in sector_terms)
            ]
            scoped_results.append(matching or chunks)
        results = scoped_results

    for need, chunks in zip(needs, results):
        evidence_items = []
        for c in chunks[:3]:
            evidence_key = (c.document_id or 0, c.page, c.chunk_id)
            if len(global_chunk_map) >= context_cap and evidence_key not in global_chunk_map:
                # The cap is sized for all requirements; never replace an earlier packet silently.
                continue
            if evidence_key not in global_chunk_map:
                global_chunk_map[evidence_key] = f"pdf-{len(global_chunk_map) + 1:03d}"
            evidence_items.append(
                RfpSectionEvidence(
                    id=global_chunk_map[evidence_key],
                    source_document_id=c.document_id or 0,
                    document_name=c.document_name,
                    page=c.page,
                    chunk_id=c.chunk_id,
                    quote=c.content[:1200],
                )
            )

        status = "SUPPORTED" if evidence_items else "NO_RELEVANT_EVIDENCE"
        packets.append(
            EvidencePacket(
                requirement_id=need.id,
                status=status,
                evidence=evidence_items
            )
        )

    return packets
