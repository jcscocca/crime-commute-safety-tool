from __future__ import annotations

from app.assistant.llm_client import OpenAiLlmClient


def test_no_key_no_auth_header() -> None:
    client = OpenAiLlmClient(base_url="http://x/v1", model="m")
    assert client.request_headers() == {}


def test_key_becomes_bearer_header() -> None:
    client = OpenAiLlmClient(base_url="http://x/v1", model="m", api_key="gsk_abc")
    assert client.request_headers() == {"Authorization": "Bearer gsk_abc"}
