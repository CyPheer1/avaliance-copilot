import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.generation.ollama import generate_text, generate_text_async
from app.settings import Settings


def _settings() -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
    )


def _sync_client(response_text: str) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"response": response_text}
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    return client


def test_generate_text_retries_read_timeout_then_succeeds():
    first_client = _sync_client("")
    first_client.post.side_effect = httpx.ReadTimeout("read timed out")
    second_client = _sync_client("Réponse après nouvelle tentative")

    with patch("app.generation.ollama.httpx.Client", side_effect=[first_client, second_client]), \
         patch("app.generation.ollama.time.sleep") as sleep:
        response = generate_text("prompt", _settings(), max_tokens=64)

    assert response == "Réponse après nouvelle tentative"
    assert first_client.post.call_count == 1
    assert second_client.post.call_count == 1
    sleep.assert_called_once()


def test_generate_text_does_not_retry_connection_error():
    client = _sync_client("")
    client.post.side_effect = httpx.ConnectError("connection reset")

    with patch("app.generation.ollama.httpx.Client", return_value=client), \
         patch("app.generation.ollama.time.sleep") as sleep:
        try:
            generate_text("prompt", _settings(), max_tokens=64)
        except Exception as exc:
            assert exc.__class__.__name__ == "OllamaUnavailableError"
        else:
            raise AssertionError("Expected OllamaUnavailableError")

    assert client.post.call_count == 1
    sleep.assert_not_called()


def test_generate_text_async_retries_transient_transport_error_then_succeeds():
    first_client = MagicMock()
    first_client.__aenter__ = AsyncMock(return_value=first_client)
    first_client.__aexit__ = AsyncMock(return_value=None)
    first_client.post = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))
    second_response = MagicMock()
    second_response.json.return_value = {"response": "Réponse asynchrone"}
    second_client = MagicMock()
    second_client.__aenter__ = AsyncMock(return_value=second_client)
    second_client.__aexit__ = AsyncMock(return_value=None)
    second_client.post = AsyncMock(return_value=second_response)

    with patch("app.generation.ollama.httpx.AsyncClient", side_effect=[first_client, second_client]), \
         patch("app.generation.ollama.asyncio.sleep", new_callable=AsyncMock) as sleep:
        response = asyncio.run(generate_text_async("prompt", _settings(), max_tokens=64))

    assert response == "Réponse asynchrone"
    assert first_client.post.await_count == 1
    assert second_client.post.await_count == 1
    sleep.assert_awaited_once()
