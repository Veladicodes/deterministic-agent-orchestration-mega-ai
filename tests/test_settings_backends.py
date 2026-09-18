"""Tests for pluggable real-backend selection.

Verifies that PipelineRunner defaults to the deterministic stub tool and
only selects RealWebSearchTool when explicitly opted in via settings,
per the determinism-preserving design in orchestration/pipeline.py.
"""

from __future__ import annotations

import os

import pytest

from shared.agent_base import AgentConfig
from shared.settings import get_settings
from tools.real_web_search_tool import RealWebSearchTool
from agents.synthesizer import SynthesizerAgent
from agents.llm_synthesizer import LLMSynthesizerAgent
from orchestration.pipeline import PipelineRunner


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _reset_backend_env():
    for key in ("USE_REAL_BACKENDS", "SEARCH_BACKEND", "SEARCH_API_KEY", "SYNTHESIZER_BACKEND", "ANTHROPIC_API_KEY"):
        os.environ.pop(key, None)


def test_default_settings_use_stub_backend():
    _reset_backend_env()
    settings = get_settings()
    assert settings.use_real_backends is False
    assert settings.search_backend == "stub"


def test_pipeline_defaults_to_stub_web_search_tool():
    _reset_backend_env()
    runner = PipelineRunner()
    assert runner._build_web_search_tool() is None


def test_pipeline_selects_real_web_search_tool_when_opted_in():
    _reset_backend_env()
    os.environ["USE_REAL_BACKENDS"] = "true"
    os.environ["SEARCH_BACKEND"] = "tavily"
    os.environ["SEARCH_API_KEY"] = "fake-key"
    get_settings.cache_clear()

    runner = PipelineRunner()
    tool = runner._build_web_search_tool()

    assert isinstance(tool, RealWebSearchTool)
    _reset_backend_env()


def test_pipeline_stays_on_stub_when_flag_off_even_with_backend_set():
    _reset_backend_env()
    os.environ["SEARCH_BACKEND"] = "tavily"
    os.environ["SEARCH_API_KEY"] = "fake-key"
    get_settings.cache_clear()

    runner = PipelineRunner()
    assert runner._build_web_search_tool() is None
    _reset_backend_env()


def test_pipeline_defaults_to_deterministic_synthesizer():
    _reset_backend_env()
    get_settings.cache_clear()
    runner = PipelineRunner()
    config = AgentConfig(agent_id="synthesizer_test")

    agent = runner._build_synthesizer_agent(config)

    assert type(agent) is SynthesizerAgent


def test_pipeline_selects_llm_synthesizer_when_opted_in():
    _reset_backend_env()
    os.environ["USE_REAL_BACKENDS"] = "true"
    os.environ["SYNTHESIZER_BACKEND"] = "llm"
    os.environ["ANTHROPIC_API_KEY"] = "fake-key"
    get_settings.cache_clear()

    runner = PipelineRunner()
    config = AgentConfig(agent_id="synthesizer_test")
    agent = runner._build_synthesizer_agent(config)

    assert isinstance(agent, LLMSynthesizerAgent)
    _reset_backend_env()


def test_pipeline_stays_on_deterministic_synthesizer_when_flag_off():
    _reset_backend_env()
    os.environ["SYNTHESIZER_BACKEND"] = "llm"
    os.environ["ANTHROPIC_API_KEY"] = "fake-key"
    get_settings.cache_clear()

    runner = PipelineRunner()
    config = AgentConfig(agent_id="synthesizer_test")
    agent = runner._build_synthesizer_agent(config)

    assert type(agent) is SynthesizerAgent
    _reset_backend_env()
