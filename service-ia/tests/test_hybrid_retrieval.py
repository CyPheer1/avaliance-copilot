"""Focused tests for the Phase B hybrid retrieval pipeline."""

from unittest.mock import patch

import numpy as np
import pytest

from app.retrieval.vector_search import _RRF_K, reciprocal_rank_fusion, vector_search
from app.schemas import RetrieveRequest
from app.settings import Settings


@pytest.fixture(autouse=True)
def _mock_cuda_reranker():
    with patch(
        "app.retrieval.vector_search.rerank",
        side_effect=lambda _query, passages: [float(len(passages) - index) for index, _ in enumerate(passages)],
    ):
        yield


def _row(chunk_id: int) -> dict:
    return {
        "chunk_id": chunk_id,
        "mission_id": chunk_id,
        "mission_title": f"Mission {chunk_id}",
        "document_id": chunk_id,
        "document_name": f"doc-{chunk_id}.pdf",
        "page": chunk_id,
        "sector": "banque",
        "mission_type": "modernisation applicative",
        "corpus_scope": "PDF",
        "content": f"Chunk {chunk_id}",
        "ranking_score": 1.0,
    }


def test_reciprocal_rank_fusion_rewards_results_in_both_rankings():
    fused = reciprocal_rank_fusion(
        [[_row(1), _row(2)], [_row(2), _row(3)]],
        top_k=3,
    )

    assert [row["chunk_id"] for row in fused] == [2, 1, 3]
    assert fused[0]["score"] > fused[1]["score"]
    assert fused[0]["rrf_score"] == fused[0]["score"]
    assert 0.0 <= fused[0]["relevance_score"] <= 1.0


def test_reciprocal_rank_fusion_uses_approved_default_configuration():
    settings = Settings()

    assert _RRF_K == 60
    assert settings.retrieval_rrf_k == 60
    assert (settings.retrieval_vector_weight, settings.retrieval_text_weight) == (1.0, 1.0)
    assert settings.retrieval_hnsw_ef_search == 100
    assert settings.retrieval_hnsw_iterative_scan == "strict_order"
    assert settings.retrieval_rerank_lexical_bonus == 0.0
    assert settings.retrieval_lexical_evidence_reserve == 5
    assert settings.retrieval_evidence_rank_safeguard == 10


def test_reciprocal_rank_fusion_can_prioritize_lexical_matches():
    fused = reciprocal_rank_fusion(
        [[_row(1)], [_row(947)]],
        top_k=2,
        weights=(1.0, 2.0),
    )

    assert [row["chunk_id"] for row in fused] == [947, 1]


def test_reciprocal_rank_fusion_keeps_text_score():
    fused = reciprocal_rank_fusion(
        [[], [{**_row(947), "ranking_score": 0.8}]],
        top_k=1,
        weights=(1.0, 1.0),
    )

    assert fused[0]["text_score"] == 0.8
    assert fused[0]["relevance_score"] == 0.0


def test_reciprocal_rank_fusion_does_not_force_branch_leaders_into_top_k():
    fused = reciprocal_rank_fusion(
        [[_row(99)], [_row(1), _row(2)]],
        top_k=2,
        weights=(1.0, 2.0),
    )

    assert [row["chunk_id"] for row in fused] == [1, 2]


def test_vector_search_runs_vector_and_text_queries_with_shared_filters():
    def query_results(sql: str, _params: tuple, **_kwargs: object) -> list[dict]:
        if "dc.embedding <=>" in sql:
            return [_row(1), _row(2)]
        return [_row(2), _row(3)]

    with (
        patch(
            "app.retrieval.vector_search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ),
        patch(
            "app.retrieval.vector_search.execute_query",
            side_effect=query_results,
        ) as execute_query,
    ):
        response = vector_search(
            RetrieveRequest(query="modernisation Java", sector="banque", top_k=2)
        )

    assert [chunk.chunk_id for chunk in response.chunks] == [2, 3, 1]
    assert execute_query.call_count == 2
    assert all(call.args[1][-1] == 50 for call in execute_query.call_args_list)
    vector_call = next(call for call in execute_query.call_args_list if "dc.embedding <=>" in call.args[0])
    assert vector_call.kwargs["local_settings"] == {
        "hnsw.ef_search": "100",
        "hnsw.iterative_scan": "strict_order",
    }
    queries = [call.args[0] for call in execute_query.call_args_list]
    assert any("dc.embedding <=>" in query for query in queries)
    assert any("tsvector_to_array(to_tsvector('french', %s))" in query for query in queries)
    assert all("Question de test|Réponse attendue|Question négative" not in query for query in queries)
    assert all("dc.sector = %s" in query for query in queries)
    assert all("dc.content AS content" in query for query in queries)
    assert all("next_chunk" not in query for query in queries)
    assert all("Difficultés rencontrées" not in query for query in queries)
    assert all("Architecture cible" not in query for query in queries)
    text_call = next(call for call in execute_query.call_args_list if "lexical_query" in call.args[0])
    assert text_call.args[1][0] == "modernisation Java"


def test_vector_search_keeps_quoted_project_candidates_for_score_boost():
    query = "Dans le projet « Atlas Finance », quelle difficulté ?"
    with (
        patch(
            "app.retrieval.vector_search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ),
        patch(
            "app.retrieval.vector_search.execute_query",
            return_value=[_row(1)],
        ) as execute_query,
    ):
        vector_search(
            RetrieveRequest(query=query, top_k=1)
        )

    text_call = next(call for call in execute_query.call_args_list if "lexical_query" in call.args[0])
    assert text_call.args[1][0].startswith(query)
    assert "difficultes" in text_call.args[1][0]
    vector_call = next(
        call
        for call in execute_query.call_args_list
        if "dc.embedding <=>" in call.args[0]
    )
    assert "dc.ts @@" not in vector_call.args[0]
    assert "LOWER(sd.original_filename) LIKE %s" not in vector_call.args[0]
    assert vector_call.args[1][1:] == ("PDF", vector_call.args[1][0], 50)


def test_vector_search_keeps_unquoted_project_candidates_for_score_boost():
    query = (
        "Dans le projet Référentiel client unique et qualité des données, "
        "quels sont au moins deux résultats mesurables obtenus à la fin de la mission ?"
    )
    with (
        patch(
            "app.retrieval.vector_search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ),
        patch(
            "app.retrieval.vector_search.execute_query",
            return_value=[_row(1)],
        ) as execute_query,
    ):
        vector_search(RetrieveRequest(query=query, top_k=1))

    vector_call = next(
        call for call in execute_query.call_args_list if "dc.embedding <=>" in call.args[0]
    )
    assert "LOWER(sd.original_filename) LIKE %s" not in vector_call.args[0]
    assert vector_call.args[1][1:] == ("PDF", vector_call.args[1][0], 50)


def test_vector_search_keeps_suffix_position_unquoted_project_candidates_for_score_boost():
    query = "Qui a pris en charge la partie flux temps réel dans le projet Novacom Télécom (programme HORIZON DATA) ?"
    with (
        patch(
            "app.retrieval.vector_search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ),
        patch(
            "app.retrieval.vector_search.execute_query",
            return_value=[_row(1)],
        ) as execute_query,
    ):
        vector_search(RetrieveRequest(query=query, top_k=1))

    vector_call = next(
        call for call in execute_query.call_args_list if "dc.embedding <=>" in call.args[0]
    )
    assert "LOWER(sd.original_filename) LIKE %s" not in vector_call.args[0]
    assert vector_call.args[1][1:] == ("PDF", vector_call.args[1][0], 50)


def test_vector_search_keeps_project_reference_candidates_for_score_boost():
    query = (
        "Comment l'équipe du projet AVA-012 a-t-elle évité le risque de fusionner "
        "par erreur des clients portant exactement le même nom ?"
    )
    with (
        patch(
            "app.retrieval.vector_search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ),
        patch(
            "app.retrieval.vector_search.execute_query",
            return_value=[_row(1)],
        ) as execute_query,
    ):
        vector_search(RetrieveRequest(query=query, top_k=1))

    vector_call = next(
        call for call in execute_query.call_args_list if "dc.embedding <=>" in call.args[0]
    )
    assert "LOWER(sd.original_filename) LIKE %s" not in vector_call.args[0]
    assert vector_call.args[1][1:] == ("PDF", vector_call.args[1][0], 50)


def test_vector_search_reranks_only_the_configured_rrf_candidates(monkeypatch):
    from app.settings import get_settings

    rows = [_row(chunk_id) for chunk_id in range(1, 51)]
    monkeypatch.setenv("RETRIEVAL_RERANK_LIMIT", "20")
    get_settings.cache_clear()
    try:
        with (
            patch("app.retrieval.vector_search.encode", return_value=np.ones((1, 1024), dtype=np.float32)),
            patch("app.retrieval.vector_search.execute_query", return_value=rows),
            patch("app.retrieval.vector_search.rerank", return_value=[float(index) for index in range(20)] ) as rerank,
        ):
            response = vector_search(RetrieveRequest(query="modernisation Java", top_k=6))
    finally:
        get_settings.cache_clear()

    assert rerank.call_count == 1
    assert len(rerank.call_args.args[1]) == 20
    assert len(response.chunks) == Settings().retrieval_min_final_chunks
    # The lexical reserve keeps independently strong exact matches available to
    # final evidence selection ahead of synthetic cross-encoder-only ordering.
    assert response.chunks[0].chunk_id == 5


def test_vector_search_retains_complementary_chunks_from_the_same_page():
    rows = [_row(chunk_id) for chunk_id in range(1, 13)]
    for row in rows[:3]:
        row["page"] = 1
    with (
        patch("app.retrieval.vector_search.encode", return_value=np.ones((1, 1024), dtype=np.float32)),
        patch("app.retrieval.vector_search.execute_query", return_value=rows),
    ):
        response = vector_search(RetrieveRequest(query="modernisation Java", top_k=5))

    assert len(response.chunks) == Settings().retrieval_min_final_chunks
    assert [chunk.chunk_id for chunk in response.chunks[:3]] == [1, 2, 3]
    assert {chunk.page for chunk in response.chunks[:3]} == {1}


def test_page_sibling_window_replaces_unrelated_tail_with_same_page_companion():
    from app.retrieval.vector_search import _with_page_sibling_windows

    selected = [_row(1), _row(2), _row(3)]
    selected[0].update({"document_id": 10, "page": 9, "score": 0.9, "chunk_index": 20})
    for row in selected[1:]:
        row.update({"score": 0.5})
    sibling = _row(4)
    # Database identifiers need not reflect physical source order after a reindex.
    sibling.update({"document_id": 10, "page": 9, "score": 0.1, "chunk_index": 21})

    windowed = _with_page_sibling_windows(selected + [sibling], selected)

    assert len(windowed) == len(selected)
    assert {row["chunk_id"] for row in windowed} >= {1, 4}
    assert [row["chunk_id"] for row in windowed if row["document_id"] == 10] == [1, 4]


def test_page_window_adds_bounded_following_page_continuation():
    from app.retrieval.vector_search import _with_page_sibling_windows

    selected = [_row(1), _row(2), _row(3)]
    selected[0].update({"document_id": 10, "page": 13, "score": 0.9, "chunk_index": 40})
    for row in selected[1:]:
        row.update({"score": 0.5})
    continuation = _row(99)
    continuation.update({"document_id": 10, "page": 14, "score": 0.2, "chunk_index": 42})

    windowed = _with_page_sibling_windows(selected + [continuation], selected)

    assert len(windowed) == len(selected)
    assert {row["chunk_id"] for row in windowed} >= {1, 99}
    assert any(row["page"] == 14 for row in windowed)


def test_lexical_expansion_adds_general_architecture_and_remediation_terms():
    from app.retrieval.vector_search import _expanded_lexical_query

    architecture = _expanded_lexical_query("Quelle architecture et quels mécanismes ?")
    remediation = _expanded_lexical_query("Quelle difficulté a été rencontrée et traitée ?")

    assert "broker" in architecture and "certificat" in architecture and "api" in architecture
    assert "observation" in remediation and "exclusions" in remediation


def test_lexical_expansion_adds_metrics_table_terms():
    from app.retrieval.vector_search import _expanded_lexical_query

    metrics = _expanded_lexical_query("Quelles volumétries la plateforme traite-t-elle ?")

    assert "indicateur" in metrics and "debit" in metrics and "pointe" in metrics


def test_evidence_rank_safeguard_preserves_strong_lexical_evidence():
    from app.retrieval.vector_search import _with_evidence_rank_safeguard

    cross_encoder_winner = _row(1)
    cross_encoder_winner.update({"score": 0.9, "text_score": 0.1, "rrf_score": 0.1})
    lexical_winner = _row(2)
    lexical_winner.update({"score": 0.1, "text_score": 0.9, "rrf_score": 0.2})

    ordered = _with_evidence_rank_safeguard([cross_encoder_winner, lexical_winner], 1)

    assert [row["chunk_id"] for row in ordered] == [2, 1]


def test_lexical_reserve_keeps_distinct_exact_evidence_in_final_selection():
    from app.retrieval.vector_search import _coverage_aware_selection, _lexical_reserve_ids

    rows = [_row(1), _row(2), _row(3)]
    rows[0].update({"document_id": 1, "page": 1, "text_score": 1.0})
    rows[1].update({"document_id": 1, "page": 1, "text_score": 0.9})
    rows[2].update({"document_id": 1, "page": 4, "text_score": 0.8})

    reserved_ids = _lexical_reserve_ids(rows, reserve_count=2)
    selected = _coverage_aware_selection(
        rows,
        desired_count=2,
        min_final_chunks=2,
        max_final_chunks=2,
        reserved_chunk_ids=reserved_ids,
    )

    assert reserved_ids == {1, 3}
    assert [row["chunk_id"] for row in selected] == [1, 3]


def test_named_project_reranking_keeps_matching_project_evidence_first():
    from app.retrieval.vector_search import _prefer_named_project_evidence

    matching = _row(1)
    matching["document_name"] = "Volteris_Energies.pdf"
    matching["content"] = "Volteris Énergies traite les mesures par flux."
    matching["score"] = 0.1
    unrelated = _row(2)
    unrelated["document_name"] = "Helvia.pdf"
    unrelated["content"] = "Architecture de services sur AWS."
    unrelated["score"] = 0.9

    ordered = _prefer_named_project_evidence(
        "Dans le projet Volteris Énergies, quelles technologies ?",
        [unrelated, matching],
    )

    assert [row["chunk_id"] for row in ordered] == [1, 2]


def test_named_project_boost_marks_matching_document_content():
    from app.retrieval.vector_search import _apply_named_project_boost

    rows = [_row(1), _row(2)]
    for row in rows:
        row["score"] = 0.1
        row["rrf_score"] = 0.1
    rows[1]["document_name"] = "Atlas Finance - bilan.pdf"
    rows[1]["content"] = "Atlas Finance : modernisation et couverture des tests."

    boosted = _apply_named_project_boost(
        "Dans le projet Atlas Finance, quelle évolution ?", rows
    )

    matching = next(row for row in boosted if row["chunk_id"] == 2)
    assert matching["project_boost"] == 0.15
    assert matching["score"] > matching["rrf_score"]


def test_vector_search_keeps_global_search_without_quoted_project():
    query = "Quelles technologies sont utilisées pour l'observabilité ?"
    with (
        patch(
            "app.retrieval.vector_search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ),
        patch(
            "app.retrieval.vector_search.execute_query",
            return_value=[_row(1)],
        ) as execute_query,
    ):
        vector_search(RetrieveRequest(query=query, top_k=1))

    assert all(
        "candidate.source_document_id" not in call.args[0]
        for call in execute_query.call_args_list
    )


def test_vector_search_applies_pdf_scope_before_ranking():
    with (
        patch(
            "app.retrieval.vector_search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ),
        patch(
            "app.retrieval.vector_search.execute_query",
            return_value=[_row(1)],
        ) as execute_query,
    ):
        response = vector_search(
            RetrieveRequest(query="Novacom", top_k=1, corpus_scope="PDF", request_id="req-1")
        )

    assert response.chunks[0].corpus_scope == "PDF"
    assert response.chunks[0].request_id == "req-1"
    assert all("dc.corpus_scope = %s" in call.args[0] for call in execute_query.call_args_list)
    assert all("sd.status = 'INDEXED'" in call.args[0] for call in execute_query.call_args_list)


def test_vector_search_applies_mission_scope_before_ranking():
    mission_row = {
        **_row(1),
        "document_id": None,
        "document_name": None,
        "page": None,
        "corpus_scope": "MISSION",
    }
    with (
        patch(
            "app.retrieval.vector_search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ),
        patch(
            "app.retrieval.vector_search.execute_query",
            return_value=[mission_row],
        ) as execute_query,
    ):
        response = vector_search(
            RetrieveRequest(query="mission similaire", top_k=1, corpus_scope="MISSION", request_id="req-2")
        )

    assert response.chunks[0].corpus_scope == "MISSION"
    assert response.chunks[0].request_id == "req-2"
    assert all("dc.corpus_scope = %s" in call.args[0] for call in execute_query.call_args_list)
    assert all("dc.mission_id IS NOT NULL" in call.args[0] for call in execute_query.call_args_list)