from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agents import llm_provider  # noqa: E402


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _settings() -> llm_provider.GeminiGemmaSettings:
    return llm_provider.GeminiGemmaSettings(
        enabled=True,
        api_key="test-key",
        model="gemini-3.6-flash",
        fallback_models=("gemini-3.5-flash", "gemini-3.5-flash-lite"),
        timeout_seconds=1.0,
        thinking_level="high",
    )


def test_rate_limit_advances_to_fallback() -> None:
    original = llm_provider.urlopen
    urls: list[str] = []

    def fake_urlopen(request, timeout):
        del timeout
        urls.append(request.full_url)
        if "gemini-3.6-flash" in request.full_url:
            raise HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                {},
                io.BytesIO(b'{"error":{"status":"RESOURCE_EXHAUSTED"}}'),
            )
        return _Response({
            "candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]
        })

    try:
        llm_provider.urlopen = fake_urlopen
        provider = llm_provider.GeminiGemmaProvider(_settings())
        assert provider.complete(system_prompt="system", user_prompt="user") == '{"ok":true}'
        assert "gemini-3.6-flash" in urls[0]
        assert "gemini-3.5-flash" in urls[1]
        assert len(urls) == 2
        assert provider.last_model_used == "gemini-3.5-flash"

        # The same Analyst/Critic cycle reuses this provider. Once the primary
        # returns a retryable failure, later calls go directly to the healthy
        # fallback instead of consuming another failed primary request.
        assert provider.complete(system_prompt="critic", user_prompt="user") == '{"ok":true}'
        assert len(urls) == 3
        assert "gemini-3.5-flash" in urls[2]
    finally:
        llm_provider.urlopen = original


def test_authentication_error_does_not_fallback() -> None:
    original = llm_provider.urlopen
    calls = 0

    def fake_urlopen(request, timeout):
        nonlocal calls
        del timeout
        calls += 1
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":{"status":"UNAUTHENTICATED"}}'),
        )

    try:
        llm_provider.urlopen = fake_urlopen
        provider = llm_provider.GeminiGemmaProvider(_settings())
        try:
            provider.complete(system_prompt="system", user_prompt="user")
        except llm_provider.LlmProviderError as exc:
            assert "gemini-3.6-flash" in str(exc)
        else:
            raise AssertionError("Expected authentication failure.")
        assert calls == 1
    finally:
        llm_provider.urlopen = original


def test_schema_is_sent_and_malformed_json_advances_to_fallback() -> None:
    original = llm_provider.urlopen
    requests: list[dict] = []
    calls = 0
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    user_prompt = json.dumps({
        "required_output_schema": schema,
        "input": {"symbol": "#BTCUSD"},
    })

    def fake_urlopen(request, timeout):
        nonlocal calls
        del timeout
        calls += 1
        requests.append(json.loads(request.data.decode("utf-8")))
        text = '{"ok": true "reason": "missing comma"}' if calls == 1 else '{"ok":true}'
        return _Response({
            "candidates": [{"content": {"parts": [{"text": text}]}}]
        })

    try:
        llm_provider.urlopen = fake_urlopen
        provider = llm_provider.GeminiGemmaProvider(_settings())
        result = provider.complete(system_prompt="system", user_prompt=user_prompt)
        assert result == '{"ok":true}'
        assert calls == 2
        assert provider.last_model_used == "gemini-3.5-flash"
        response_format = requests[0]["generationConfig"]["responseFormat"]
        assert response_format["text"]["mimeType"] == "application/json"
        assert response_format["text"]["schema"] == schema
        assert "responseMimeType" not in requests[0]["generationConfig"]
    finally:
        llm_provider.urlopen = original


def main() -> None:
    test_rate_limit_advances_to_fallback()
    test_authentication_error_does_not_fallback()
    test_schema_is_sent_and_malformed_json_advances_to_fallback()
    status = _settings().public_status()
    assert status["model_chain"] == [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    ]
    print("P3.15 Gemini model fallback checks passed.")


if __name__ == "__main__":
    main()
