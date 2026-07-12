from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.assistant.llm_client import LlmUnavailable, OpenAiLlmClient

_DUMMY_REQUEST = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")


def _make_client() -> OpenAiLlmClient:
    return OpenAiLlmClient(base_url="http://localhost:8080/v1", model="test-model")


def _json_response(data: object, status_code: int = 200) -> httpx.Response:
    content = json.dumps(data).encode()
    resp = httpx.Response(
        status_code=status_code,
        headers={"content-type": "application/json"},
        content=content,
        request=_DUMMY_REQUEST,
    )
    return resp


def test_complete_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Normal response: choices[0].message.content is returned as-is."""
    response_data = {"choices": [{"message": {"content": "hi", "reasoning_content": ""}}]}

    async def fake_post(self_client, url, **kwargs):  # noqa: ANN001
        return _json_response(response_data)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = _make_client()
    result = asyncio.run(client.complete([{"role": "user", "content": "hello"}], role=None))
    assert result == "hi"


def test_empty_content_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace-only content triggers LlmUnavailable."""
    response_data = {
        "choices": [{"message": {"content": "   ", "reasoning_content": "some thinking"}}]
    }

    async def fake_post(self_client, url, **kwargs):  # noqa: ANN001
        return _json_response(response_data)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = _make_client()
    with pytest.raises(LlmUnavailable, match="empty content"):
        asyncio.run(client.complete([{"role": "user", "content": "hello"}], role=None))


def test_none_content_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """None content (key missing) triggers LlmUnavailable."""
    response_data = {"choices": [{"message": {"reasoning_content": "some thinking"}}]}

    async def fake_post(self_client, url, **kwargs):  # noqa: ANN001
        return _json_response(response_data)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = _make_client()
    with pytest.raises(LlmUnavailable, match="empty content"):
        asyncio.run(client.complete([{"role": "user", "content": "hello"}], role=None))


def test_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An HTTP connection error is wrapped in LlmUnavailable."""

    async def fake_post(self_client, url, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = _make_client()
    with pytest.raises(LlmUnavailable, match="LLM endpoint unavailable"):
        asyncio.run(client.complete([{"role": "user", "content": "hello"}], role=None))


def test_bad_response_shape_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected JSON shape raises LlmUnavailable."""
    response_data = {"result": "unexpected"}

    async def fake_post(self_client, url, **kwargs):  # noqa: ANN001
        return _json_response(response_data)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = _make_client()
    with pytest.raises(LlmUnavailable, match="unexpected response shape"):
        asyncio.run(client.complete([{"role": "user", "content": "hello"}], role=None))


def test_http_status_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-2xx HTTP status is wrapped in LlmUnavailable."""

    async def fake_post(self_client, url, **kwargs):  # noqa: ANN001
        return _json_response({"error": "not found"}, status_code=404)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = _make_client()
    with pytest.raises(LlmUnavailable, match="LLM endpoint unavailable"):
        asyncio.run(client.complete([{"role": "user", "content": "hello"}], role=None))


def test_extra_body_is_merged_into_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """extra_body (e.g. chat_template_kwargs) is merged into the request payload."""
    captured: dict[str, object] = {}

    async def fake_post(self_client, url, **kwargs):  # noqa: ANN001
        captured.update(kwargs.get("json") or {})
        return _json_response({"choices": [{"message": {"content": "hi"}}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = OpenAiLlmClient(
        base_url="http://localhost:8080/v1",
        model="test-model",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    result = asyncio.run(client.complete([{"role": "user", "content": "hello"}], role=None))

    assert result == "hi"
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["model"] == "test-model"  # base payload still intact


# ---------- stream() ----------

class _FakeStreamResponse:
    """Stands in for the async-context response of httpx.AsyncClient.stream()."""

    def __init__(
        self,
        lines: list[str],
        status_code: int = 200,
        error_after: int | None = None,
        error_exc: Exception | None = None,
    ) -> None:
        self._lines = lines
        self.status_code = status_code
        self._error_after = error_after
        self._error_exc = error_exc or httpx.ReadError("connection dropped")
        self.request = _DUMMY_REQUEST

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=_DUMMY_REQUEST,
                response=httpx.Response(self.status_code, request=_DUMMY_REQUEST),
            )

    async def aiter_lines(self):
        for index, line in enumerate(self._lines):
            if self._error_after is not None and index == self._error_after:
                raise self._error_exc
            yield line


def _patch_stream(monkeypatch: pytest.MonkeyPatch, response: _FakeStreamResponse) -> None:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_stream(self_client, method, url, **kwargs):  # noqa: ANN001
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)


def _sse_line(content: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": content}}]})


async def _collect_stream(client: OpenAiLlmClient) -> list[str]:
    return [d async for d in client.stream([{"role": "user", "content": "hi"}], role=None)]


def test_stream_yields_deltas_and_stops_on_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(
        monkeypatch,
        _FakeStreamResponse(
            [
                _sse_line("Hel"),
                "",
                _sse_line("lo"),
                "data: [DONE]",
                _sse_line("NEVER"),
            ]
        ),
    )
    assert asyncio.run(_collect_stream(_make_client())) == ["Hel", "lo"]


def test_stream_skips_malformed_and_empty_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(
        monkeypatch,
        _FakeStreamResponse(
            [
                "data: {not json",
                'data: {"choices":[]}',
                'data: {"choices":[{"delta":{}}]}',
                _sse_line("ok"),
                "data: [DONE]",
            ]
        ),
    )
    assert asyncio.run(_collect_stream(_make_client())) == ["ok"]


def test_stream_empty_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(monkeypatch, _FakeStreamResponse(["data: [DONE]"]))
    with pytest.raises(LlmUnavailable, match="empty stream"):
        asyncio.run(_collect_stream(_make_client()))


def test_stream_pre_delta_http_error_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(monkeypatch, _FakeStreamResponse([], status_code=503))
    with pytest.raises(LlmUnavailable, match="unavailable"):
        asyncio.run(_collect_stream(_make_client()))


def test_stream_mid_stream_death_raises_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.assistant.llm_client import LlmStreamInterrupted

    _patch_stream(
        monkeypatch,
        _FakeStreamResponse([_sse_line("partial"), _sse_line("x")], error_after=1),
    )

    async def run() -> list[str]:
        got: list[str] = []
        async for delta in _make_client().stream([{"role": "user", "content": "hi"}], role=None):
            got.append(delta)
        return got

    with pytest.raises(LlmStreamInterrupted):
        asyncio.run(run())


def test_stream_mid_stream_non_http_error_raises_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.assistant.llm_client import LlmStreamInterrupted

    _patch_stream(
        monkeypatch,
        _FakeStreamResponse(
            [_sse_line("partial"), _sse_line("x")],
            error_after=1,
            error_exc=httpx.StreamClosed(),
        ),
    )

    async def run() -> None:
        async for _delta in _make_client().stream([{"role": "user", "content": "hi"}], role=None):
            pass

    with pytest.raises(LlmStreamInterrupted):
        asyncio.run(run())


def test_stream_sets_stream_true_and_merges_extra_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    response = _FakeStreamResponse([_sse_line("hi"), "data: [DONE]"])
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_stream(self_client, method, url, **kwargs):  # noqa: ANN001
        captured.update(kwargs.get("json") or {})
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    client = OpenAiLlmClient(
        base_url="http://localhost:8080/v1",
        model="test-model",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    asyncio.run(
        _collect_stream(client)
    )
    assert captured["stream"] is True
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
