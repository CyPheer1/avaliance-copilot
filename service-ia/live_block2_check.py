"""Certify the exact-evidence contract against the configured live Ollama model."""

import json

from app.generation.service import generate_sourced_answer
from app.schemas import GenerateRequest, RetrievedChunk
from app.settings import get_settings


source_sentence = (
    "Le déploiement de la plateforme est automatisé avec Terraform et validé "
    "par une revue humaine avant chaque mise en production."
)
request = GenerateRequest(
    query="Comment le déploiement est-il automatisé et validé ?",
    chunks=[
        RetrievedChunk(
            chunk_id=1,
            mission_id=1,
            mission_title="Certification génération",
            content=source_sentence,
            score=0.03,
            rrf_score=0.03,
            relevance_score=0.91,
            vector_score=0.91,
            text_score=0.4,
        )
    ],
)

response = generate_sourced_answer(request, get_settings())
print(json.dumps(response.model_dump(), ensure_ascii=False, indent=2))

assert response.diagnostic is None, response.diagnostic
assert response.answer == f"{source_sentence} [1]"
assert len(response.citations) == 1
assert response.citations[0].chunk_id == 1
assert response.confidence == 0.91