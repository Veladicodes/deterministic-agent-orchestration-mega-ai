"""Tests for RealWebSearchTool.

All tests here use a mocked httpx transport so the default test suite
never makes a real network call. A separate `integration` test (excluded
from the default run, see pyproject.toml addopts) exercises the tool
against the live Tavily API when SEARCH_API_KEY is present in the
environment.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from tools.real_web_search_tool import RealWebSearchTool, TAVILY_ENDPOINT


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


def test_empty_query_returns_empty_failure_mode():
    tool = RealWebSearchTool(api_key="fake-key")
    result = run_async(tool.run({"query": ""}))
    assert result.success is False
    assert result.failure_mode.value == "empty"


def test_missing_api_key_returns_internal_failure():
    tool = RealWebSearchTool(api_key=None)
    result = run_async(tool.run({"query": "deterministic orchestration"}))
    assert result.success is False
    assert result.failure_mode.value == "internal"
    assert "search_api_key" in (result.error_message or "")


def test_successful_search_maps_results_into_expected_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == TAVILY_ENDPOINT
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Result 1", "url": "https://example.com/1", "content": "snippet 1", "score": 0.91},
                    {"title": "Result 2", "url": "https://example.com/2", "content": "snippet 2", "score": 0.5},
                ]
            },
        )

    client = _client_with_handler(handler)
    tool = RealWebSearchTool(api_key="fake-key", client=client)
    result = run_async(tool.run({"query": "deterministic orchestration"}))

    assert result.success is True
    assert result.failure_mode.value == "none"
    assert result.result["tokens"] == 0
    hits = result.result["results"]
    assert len(hits) == 2
    assert hits[0] == {
        "title": "Result 1",
        "url": "https://example.com/1",
        "snippet": "snippet 1",
        "relevance_score": 0.91,
    }


def test_non_200_response_returns_internal_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"})

    client = _client_with_handler(handler)
    tool = RealWebSearchTool(api_key="fake-key", client=client)
    result = run_async(tool.run({"query": "deterministic orchestration"}))

    assert result.success is False
    assert result.failure_mode.value == "internal"


def test_malformed_response_returns_malformed_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": "not-a-list"})

    client = _client_with_handler(handler)
    tool = RealWebSearchTool(api_key="fake-key", client=client)
    result = run_async(tool.run({"query": "deterministic orchestration"}))

    assert result.success is False
    assert result.failure_mode.value == "malformed"


def test_timeout_returns_timeout_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = _client_with_handler(handler)
    tool = RealWebSearchTool(api_key="fake-key", client=client)
    result = run_async(tool.run({"query": "deterministic orchestration"}, timeout_seconds=0.01))

    assert result.success is False
    assert result.failure_mode.value == "timeout"


@pytest.mark.integration
def test_live_tavily_search_returns_results():
    """Opt-in integration test — requires a real SEARCH_API_KEY env var.

    Excluded from the default `pytest` run via the `integration` marker
    (see pyproject.toml addopts = "-m 'not integration'"). Run explicitly
    with: pytest -m integration tests/tools/test_real_web_search_tool.py
    """
    api_key = os.getenv("SEARCH_API_KEY")
    if not api_key:
        pytest.skip("SEARCH_API_KEY not set; skipping live integration test")

    tool = RealWebSearchTool(api_key=api_key)
    result = run_async(tool.run({"query": "deterministic orchestration systems"}))

    assert result.success is True
    assert len(result.result["results"]) > 0
