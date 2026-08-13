"""Regression tests for criterion-level evidence validation."""

import json
from unittest.mock import patch

from app.generation.prompts import INSUFFICIENT_INFORMATION
from app.generation.service import generate_sourced_answer
from app.schemas import GenerateRequest, RetrievedChunk
from app.settings import Settings


def _settings() -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
        llm_model="qwen3:8b",
        generation_cache_max_entries=0,
    )


def _chunk(content: str, *, chunk_id: int = 1, page: int = 8) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        document_name="novacom.pdf",
        page=page,
        sector="telecom",
        mission_type="data",
        corpus_scope="PDF",
        content=content,
        score=0.1,
        rrf_score=0.1,
        relevance_score=0.9,
        vector_score=0.9,
        text_score=0.8,
    )


def _coverage(*items: tuple[str, int, str]) -> str:
    return json.dumps(
        {
            "status": "SUPPORTED",
            "coverage": [
                {
                    "criterion": criterion,
                    "evidence": [{"source": source, "quote": quote}],
                }
                for criterion, source, quote in items
            ],
        },
        ensure_ascii=False,
    )


def test_generation_accepts_each_atomic_criterion_with_direct_evidence():
    content = (
        "Le modèle LightGBM a été retenu. "
        "Son aire sous la courbe ROC atteint 0,86. "
        "La précision est de 37 % sur les 5 % de clients les plus à risque."
    )
    request = GenerateRequest(query="Quel modèle et quelle performance ?", chunks=[_chunk(content)])
    model_output = _coverage(
        ("Le modèle retenu est LightGBM", 1, "Le modèle LightGBM a été retenu."),
        ("L'aire sous la courbe ROC atteint 0,86", 1, "Son aire sous la courbe ROC atteint 0,86."),
        ("La précision est de 37 %", 1, "La précision est de 37 % sur les 5 % de clients les plus à risque."),
    )

    with patch("app.generation.service.generate_text", return_value=model_output):
        response = generate_sourced_answer(request, _settings())

    assert response.validation_passed is True
    assert "LightGBM" in response.answer
    assert "0,86" in response.answer
    assert "37 %" in response.answer
    assert response.citations[0].page == 8


def test_generation_rejects_related_attribute_as_market_share_evidence():
    request = GenerateRequest(
        query="Quelle est la part de marché de Novacom ?",
        chunks=[_chunk("Novacom compte 4,7 millions d'abonnés mobiles.")],
    )
    model_output = _coverage(
        ("La part de marché de Novacom est de 4,7 millions d'abonnés", 1, "Novacom compte 4,7 millions d'abonnés mobiles."),
    )

    with patch("app.generation.service.generate_text", return_value=model_output):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "UNSUPPORTED_ANSWER"
    assert response.citations == []


def test_generation_rejects_a_vague_criterion_even_with_exact_quote():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk("La plateforme utilise Azure et Kubernetes.")])
    model_output = _coverage(
        ("Réponse", 1, "La plateforme utilise Azure et Kubernetes."),
    )

    with patch("app.generation.service.generate_text", return_value=model_output):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "UNSUPPORTED_ANSWER"
