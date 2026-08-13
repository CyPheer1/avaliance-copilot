from unittest.mock import MagicMock, patch

from app.generation.ollama import _visible_tokens, generate_text, generate_text_stream
from app.settings import Settings


def _settings() -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
    )


def _client(response_text: str = "{}") -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"response": response_text}
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    return client


def test_generate_text_sends_requested_json_schema_to_ollama():
    schema = {
        "type": "object",
        "required": ["status", "evidence"],
    }
    client = _client()

    with patch("app.generation.ollama.httpx.Client", return_value=client):
        generate_text("prompt", _settings(), max_tokens=64, output_schema=schema)

    payload = client.post.call_args.kwargs["json"]
    assert payload["format"] == schema
    assert payload["model"] == "qwen3:8b"
    assert payload["think"] is False


def test_generate_text_keeps_free_text_requests_unconstrained():
    client = _client("Réponse libre")

    with patch("app.generation.ollama.httpx.Client", return_value=client):
        generate_text("prompt", _settings(), max_tokens=64)

    payload = client.post.call_args.kwargs["json"]
    assert "format" not in payload
    assert payload["model"] == "qwen3:8b"
    assert payload["think"] is False


def test_visible_tokens_excludes_split_thinking_block():
    tokens = iter(["Bonjour ", "<thi", "nk>analyse", " privée</th", "ink>", "monde"])

    assert "".join(_visible_tokens(tokens)) == "Bonjour monde"


def test_generate_text_stream_uses_configured_non_thinking_model():
    response = MagicMock()
    response.iter_lines.return_value = [
        '{"response":"Bonjour","done":false}',
        '{"response":" monde","done":true}',
    ]
    response.__enter__.return_value = response
    client = MagicMock()
    client.__enter__.return_value = client
    client.stream.return_value = response

    with patch("app.generation.ollama.httpx.Client", return_value=client):
        assert "".join(generate_text_stream("prompt", _settings(), max_tokens=64)) == "Bonjour monde"

    payload = client.stream.call_args.kwargs["json"]
    assert payload["model"] == "qwen3:8b"
    assert payload["think"] is False
    assert payload["options"]["num_ctx"] == 8192