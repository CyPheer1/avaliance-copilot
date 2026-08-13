"""Tests for SQL-based similar mission retrieval and its endpoint."""

from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import SimilarRequest
from app.settings import Settings
from app.similar_missions.search import find_similar_missions

TOKEN = "test-internal-token-123456"


def test_find_similar_missions_uses_cosine_tags_and_filters():
    row = {
        "id": 7,
        "title": "Modernisation bancaire",
        "sector": "banque",
        "mission_type": "modernisation applicative",
        "technologies": ["Java", "Spring Boot"],
        "year": 2024,
        "summary": "Modernisation d'une plateforme bancaire.",
        "similarity_score": 0.91,
    }
    with (
        patch(
            "app.similar_missions.search.encode",
            return_value=np.ones((1, 1024), dtype=np.float32),
        ) as encode,
        patch("app.similar_missions.search.execute_query", return_value=[row]) as execute_query,
    ):
        response = find_similar_missions(
            SimilarRequest(
                description="Plateforme Java Spring Boot",
                sector="banque",
                mission_type="modernisation applicative",
                top_k=3,
            )
        )

    assert response.missions[0].id == 7
    assert response.missions[0].similarity_score == 0.91
    encode.assert_called_once_with(["Plateforme Java Spring Boot"])
    sql, params = execute_query.call_args.args
    assert "dc.embedding <=>" in sql
    assert "unnest(m.technologies)" in sql
    assert "m.sector = %s" in sql
    assert "m.mission_type = %s" in sql
    assert params[-1] == 3


def test_similar_endpoint_returns_missions():
    settings = Settings(
        internal_token=TOKEN,
        database_url="postgresql://test:test@localhost:5432/test",
    )
    app = create_app(settings)
    app.router.lifespan_context = None  # type: ignore[assignment]
    client = TestClient(app)

    with patch(
        "app.similar_missions.search.find_similar_missions",
        return_value={
            "missions": [
                {
                    "id": 7,
                    "title": "Modernisation bancaire",
                    "sector": "banque",
                    "mission_type": "modernisation applicative",
                    "technologies": ["Java"],
                    "year": 2024,
                    "summary": "Mission synthétique.",
                    "similarity_score": 0.91,
                }
            ]
        },
    ):
        response = client.post(
            "/similar",
            json={"description": "Modernisation Java", "top_k": 3},
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 200
    assert response.json()["missions"][0]["id"] == 7