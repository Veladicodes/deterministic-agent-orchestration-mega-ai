"""Tests for LLMTool.

All tests here use a mocked httpx transport so the default test suite
never makes a real network call. A separate `integration` test (excluded
from the default run, see pyproject.toml addopts) exercises the tool
against the live Anthropic API when ANTHROPIC_API_KEY is present.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from tools.llm_tool import LLMTool, ANTHROPIC_ENDPOINT


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _client_with_handler(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def test_empty_prompt_returns_empty_failure_mode():
    tool = LLMTool(api_key="fake-key")
    result = run_async(tool.run({"prompt": ""}))
    assert result.success is False
    assert result.failure_mode.value == "empty"


def test_missing_api_key_returns_internal_failure():
    tool = LLMTool(api_key=None)
    result = run_async(tool.run({"prompt": "summarize this"}))
    assert result.success is False
    assert result.failure_mode.value == "internal"
    assert "anthropic_api_key" in (result.error_message or "")


def test_successful_completion_maps_text_and_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == ANTHROPIC_ENDPOINT
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "The synthesized answer."}],
                "usage": {"input_tokens": 120, "output_tokens": 40},
            },
        )

    client = _client_with_handler(handler)
    tool = LLMTool(api_key="fake-key", client=client)
    result = run_async(tool.run({"prompt": "summarize this"}))

    assert result.success is True
    assert result.result["text"] == "The synthesized answer."
    assert result.result["tokens"] == 160
    assert result.result["input_tokens"] == 120
    assert result.result["output_tokens"] == 40
    assert result.result["cost_usd"] > 0


def test_non_200_response_returns_internal_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = _client_with_handler(handler)
    tool = LLMTool(api_key="bad-key", client=client)
    result = run_async(tool.run({"prompt": "summarize this"}))

    assert result.success is False
    assert result.failure_mode.value == "internal"


def test_malformed_response_returns_malformed_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": []})

    client = _client_with_handler(handler)
    tool = LLMTool(api_key="fake-key", client=client)
    result = run_async(tool.run({"prompt": "summarize this"}))

    assert result.success is False
    assert result.failure_mode.value == "malformed"


def test_timeout_returns_timeout_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = _client_with_handler(handler)
    tool = LLMTool(api_key="fake-key", client=client)
    result = run_async(tool.run({"prompt": "summarize this"}, timeout_seconds=0.01))

    assert result.success is False
    assert result.failure_mode.value == "timeout"


@pytest.mark.integration
def test_live_anthropic_completion():
    """Opt-in integration test — requires a real ANTHROPIC_API_KEY env var.

    Excluded from the default `pytest` run via the `integration` marker
    (see pyproject.toml addopts = "-m 'not integration'").
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set; skipping live integration test")

    tool = LLMTool(api_key=api_key)
    result = run_async(tool.run({"prompt": "Say hello in one short sentence."}))

    assert result.success is True
    assert len(result.result["text"]) > 0
