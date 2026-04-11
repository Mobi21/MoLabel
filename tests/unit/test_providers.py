"""Tests for provider adapters (Steps 2.B.2–2.B.5).

Verifies:
- Each adapter satisfies the ModelProviderPlugin protocol.
- Adapters can be constructed and return correct metadata.
- Health checks, model listing, cost estimation work correctly.
- Structured output enforcement handles JSON extraction and validation.
- Cost tracking computes running totals and budget alerts.
- Provider auto-detection discovers env-var-based providers.
- HuggingFace auth resolves tokens from environment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from molabel.core.plugins.protocols import ModelProviderPlugin
from molabel.core.providers.anthropic_adapter import AnthropicAdapter
from molabel.core.providers.base import (
    ProviderError,
    build_headers,
    build_openai_request_body,
    compute_cost,
    messages_to_dicts,
    parse_openai_response,
    resolve_api_key,
)
from molabel.core.providers.cost_tracking import CostTracker
from molabel.core.providers.custom_adapter import CustomAdapter
from molabel.core.providers.detection import ProviderDetector
from molabel.core.providers.hf_auth import HuggingFaceAuth
from molabel.core.providers.ollama_adapter import OllamaAdapter
from molabel.core.providers.openai_adapter import OpenAIAdapter
from molabel.core.providers.openrouter_adapter import OpenRouterAdapter
from molabel.core.providers.structured_output import (
    OfflineDegradationError,
    StructuredOutputEnforcer,
)
from molabel.core.types import (
    CompletionChunk,
    CompletionResult,
    CostEstimate,
    HealthStatus,
    Message,
    ModelInfo,
    PluginMetadata,
)

# ---------------------------------------------------------------------------
# Helper: fake provider for structured output tests
# ---------------------------------------------------------------------------


class _FakeProvider:
    """Minimal provider for unit tests (no network calls)."""

    def __init__(
        self,
        *,
        structured: bool = False,
        response_content: str = "",
        parsed: dict[str, Any] | None = None,
    ) -> None:
        self._structured = structured
        self._response_content = response_content
        self._parsed = parsed

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="test.fake",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Fake provider for tests",
        )

    @property
    def provider_type(self) -> str:
        return "custom"

    def check_health(self) -> HealthStatus:
        return HealthStatus(is_healthy=True)

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(model_id="fake-model", display_name="Fake")]

    def supports_structured_output(self) -> bool:
        return self._structured

    def supports_logprobs(self) -> bool:
        return False

    def complete(
        self,
        messages: list[Message],
        model: str,
        *,
        output_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        logprobs: bool = False,
        top_logprobs: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CompletionResult:
        return CompletionResult(
            content=self._response_content,
            parsed=self._parsed,
            tokens_input=10,
            tokens_output=5,
        )

    async def stream_complete(
        self,
        messages: list[Message],
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[CompletionChunk]:
        yield CompletionChunk(delta="test")

    def estimate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> CostEstimate:
        return CostEstimate(input_cost=0.001, output_cost=0.002, total_cost=0.003)


# ===================================================================
# Base utility tests
# ===================================================================


class TestBaseUtilities:
    def test_resolve_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_API_KEY", "sk-test-123")
        assert resolve_api_key("TEST_API_KEY") == "sk-test-123"

    def test_resolve_api_key_missing(self) -> None:
        assert resolve_api_key("NONEXISTENT_KEY_12345") is None

    def test_resolve_api_key_none(self) -> None:
        assert resolve_api_key(None) is None

    def test_build_headers_with_key(self) -> None:
        headers = build_headers("sk-test")
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_no_key(self) -> None:
        headers = build_headers(None)
        assert "Authorization" not in headers

    def test_build_headers_extra(self) -> None:
        headers = build_headers("sk-test", extra_headers={"X-Custom": "value"})
        assert headers["X-Custom"] == "value"

    def test_messages_to_dicts(self) -> None:
        msgs = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
        ]
        result = messages_to_dicts(msgs)
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["content"] == "Hello"

    def test_messages_to_dicts_with_name(self) -> None:
        msgs = [Message(role="user", content="hi", name="alice")]
        result = messages_to_dicts(msgs)
        assert result[0]["name"] == "alice"

    def test_build_openai_request_body_basic(self) -> None:
        msgs = [Message(role="user", content="hello")]
        body = build_openai_request_body(msgs, "gpt-4o")
        assert body["model"] == "gpt-4o"
        assert len(body["messages"]) == 1
        assert body["temperature"] == 0.0
        assert body["stream"] is False

    def test_build_openai_request_body_with_schema(self) -> None:
        msgs = [Message(role="user", content="hello")]
        schema = {"type": "object", "title": "MyOutput", "properties": {}}
        body = build_openai_request_body(msgs, "gpt-4o", output_schema=schema)
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["name"] == "MyOutput"

    def test_build_openai_request_body_with_logprobs(self) -> None:
        msgs = [Message(role="user", content="hello")]
        body = build_openai_request_body(msgs, "gpt-4o", logprobs=True, top_logprobs=5)
        assert body["logprobs"] is True
        assert body["top_logprobs"] == 5

    def test_parse_openai_response(self) -> None:
        import time

        data = {
            "choices": [
                {
                    "message": {"content": "Hello there!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "model": "gpt-4o",
        }
        result = parse_openai_response(data, time.monotonic())
        assert result.content == "Hello there!"
        assert result.finish_reason == "stop"
        assert result.tokens_input == 10
        assert result.tokens_output == 5
        assert result.model_id == "gpt-4o"

    def test_parse_openai_response_empty_choices(self) -> None:
        import time

        data = {"choices": [], "model": "gpt-4o"}
        result = parse_openai_response(data, time.monotonic())
        assert result.content == ""
        assert result.finish_reason == "error"

    def test_compute_cost(self) -> None:
        est = compute_cost(1000, 500, 0.01, 0.03)
        assert est.input_cost == pytest.approx(10.0)
        assert est.output_cost == pytest.approx(15.0)
        assert est.total_cost == pytest.approx(25.0)

    def test_compute_cost_none_pricing(self) -> None:
        est = compute_cost(1000, 500, None, None)
        assert est.total_cost == 0.0

    def test_provider_error_attributes(self) -> None:
        err = ProviderError(
            "test error",
            status_code=429,
            provider="openai",
            retriable=True,
        )
        assert err.status_code == 429
        assert err.provider == "openai"
        assert err.retriable is True
        assert "test error" in str(err)


# ===================================================================
# OpenAI adapter tests
# ===================================================================


class TestOpenAIAdapter:
    def test_isinstance_protocol(self) -> None:
        adapter = OpenAIAdapter()
        assert isinstance(adapter, ModelProviderPlugin)

    def test_metadata(self) -> None:
        adapter = OpenAIAdapter()
        assert adapter.metadata.plugin_id == "molabel.providers.openai"
        assert adapter.metadata.compatible_core == ">=0.1,<1.0"

    def test_provider_type(self) -> None:
        adapter = OpenAIAdapter()
        assert adapter.provider_type == "openai_compatible"

    def test_supports_structured_output(self) -> None:
        adapter = OpenAIAdapter()
        assert adapter.supports_structured_output() is True

    def test_supports_logprobs(self) -> None:
        adapter = OpenAIAdapter()
        assert adapter.supports_logprobs() is True

    def test_list_models(self) -> None:
        adapter = OpenAIAdapter()
        models = adapter.list_models()
        assert len(models) > 0
        model_ids = [m.model_id for m in models]
        assert "gpt-4o" in model_ids
        assert "gpt-4o-mini" in model_ids

    def test_list_models_have_pricing(self) -> None:
        adapter = OpenAIAdapter()
        models = adapter.list_models()
        gpt4o = next(m for m in models if m.model_id == "gpt-4o")
        assert gpt4o.cost_per_input_token is not None
        assert gpt4o.cost_per_input_token > 0

    def test_estimate_cost_known_model(self) -> None:
        adapter = OpenAIAdapter()
        est = adapter.estimate_cost(1000, 500, "gpt-4o")
        assert est.total_cost > 0
        assert est.currency == "USD"

    def test_estimate_cost_unknown_model(self) -> None:
        adapter = OpenAIAdapter()
        est = adapter.estimate_cost(1000, 500, "unknown-model")
        assert est.total_cost == 0.0

    def test_estimate_cost_with_override(self) -> None:
        adapter = OpenAIAdapter(
            cost_per_input_token=0.01,
            cost_per_output_token=0.03,
        )
        est = adapter.estimate_cost(100, 50, "any-model")
        assert est.input_cost == pytest.approx(1.0)
        assert est.output_cost == pytest.approx(1.5)

    def test_custom_base_url(self) -> None:
        adapter = OpenAIAdapter(base_url="http://localhost:8000/v1")
        assert adapter._base_url == "http://localhost:8000/v1"


# ===================================================================
# OpenRouter adapter tests
# ===================================================================


class TestOpenRouterAdapter:
    def test_isinstance_protocol(self) -> None:
        adapter = OpenRouterAdapter()
        assert isinstance(adapter, ModelProviderPlugin)

    def test_metadata(self) -> None:
        adapter = OpenRouterAdapter()
        assert adapter.metadata.plugin_id == "molabel.providers.openrouter"

    def test_provider_type(self) -> None:
        adapter = OpenRouterAdapter()
        assert adapter.provider_type == "openrouter"

    def test_list_models(self) -> None:
        adapter = OpenRouterAdapter()
        models = adapter.list_models()
        assert len(models) > 0
        model_ids = [m.model_id for m in models]
        assert "openai/gpt-4o" in model_ids

    def test_estimate_cost_cached(self) -> None:
        adapter = OpenRouterAdapter()
        adapter.list_models()  # Populate pricing cache
        est = adapter.estimate_cost(1000, 500, "openai/gpt-4o")
        assert est.total_cost > 0

    def test_extra_headers(self) -> None:
        adapter = OpenRouterAdapter(
            site_url="https://example.com",
            site_name="TestApp",
        )
        headers = adapter._extra_headers()
        assert headers["HTTP-Referer"] == "https://example.com"
        assert headers["X-Title"] == "TestApp"


# ===================================================================
# Ollama adapter tests
# ===================================================================


class TestOllamaAdapter:
    def test_isinstance_protocol(self) -> None:
        adapter = OllamaAdapter()
        assert isinstance(adapter, ModelProviderPlugin)

    def test_metadata(self) -> None:
        adapter = OllamaAdapter()
        assert adapter.metadata.plugin_id == "molabel.providers.ollama"

    def test_provider_type(self) -> None:
        adapter = OllamaAdapter()
        assert adapter.provider_type == "ollama"

    def test_supports_structured_output(self) -> None:
        adapter = OllamaAdapter()
        assert adapter.supports_structured_output() is True

    def test_supports_logprobs(self) -> None:
        adapter = OllamaAdapter()
        assert adapter.supports_logprobs() is False

    def test_estimate_cost_zero(self) -> None:
        adapter = OllamaAdapter()
        est = adapter.estimate_cost(1000, 500, "llama3.1")
        assert est.total_cost == 0.0

    def test_custom_base_url(self) -> None:
        adapter = OllamaAdapter(base_url="http://gpu-server:11434")
        assert adapter._base_url == "http://gpu-server:11434"


# ===================================================================
# Anthropic adapter tests
# ===================================================================


class TestAnthropicAdapter:
    def test_isinstance_protocol(self) -> None:
        adapter = AnthropicAdapter()
        assert isinstance(adapter, ModelProviderPlugin)

    def test_metadata(self) -> None:
        adapter = AnthropicAdapter()
        assert adapter.metadata.plugin_id == "molabel.providers.anthropic"

    def test_provider_type(self) -> None:
        adapter = AnthropicAdapter()
        assert adapter.provider_type == "anthropic"

    def test_supports_structured_output(self) -> None:
        adapter = AnthropicAdapter()
        assert adapter.supports_structured_output() is True

    def test_base_url_override(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.minimax.chat/v1/")
        assert adapter._base_url == "https://api.minimax.chat/v1"

    def test_messages_url_supports_minimax_anthropic_base(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.minimax.io/anthropic")
        assert adapter._messages_url() == "https://api.minimax.io/anthropic/v1/messages"

    def test_supports_logprobs(self) -> None:
        adapter = AnthropicAdapter()
        assert adapter.supports_logprobs() is False

    def test_list_models(self) -> None:
        adapter = AnthropicAdapter()
        models = adapter.list_models()
        assert len(models) > 0
        model_ids = [m.model_id for m in models]
        assert "claude-sonnet-4-20250514" in model_ids

    def test_list_models_have_pricing(self) -> None:
        adapter = AnthropicAdapter()
        models = adapter.list_models()
        claude = next(m for m in models if m.model_id == "claude-sonnet-4-20250514")
        assert claude.cost_per_input_token is not None
        assert claude.cost_per_output_token is not None
        assert claude.context_window == 200000

    def test_estimate_cost_known_model(self) -> None:
        adapter = AnthropicAdapter()
        est = adapter.estimate_cost(1000, 500, "claude-sonnet-4-20250514")
        assert est.total_cost > 0

    def test_parse_response_text(self) -> None:
        import time

        adapter = AnthropicAdapter()
        data = {
            "content": [{"type": "text", "text": "Hello!"}],
            "usage": {"input_tokens": 10, "output_tokens": 3},
            "stop_reason": "end_turn",
            "model": "claude-sonnet-4-20250514",
        }
        result = adapter._parse_response(data, time.monotonic(), False)
        assert result.content == "Hello!"
        assert result.finish_reason == "stop"
        assert result.tokens_input == 10

    def test_parse_response_tool_use(self) -> None:
        import time

        adapter = AnthropicAdapter()
        data = {
            "content": [
                {
                    "type": "tool_use",
                    "input": {"label": "positive", "confidence": 0.9},
                }
            ],
            "usage": {"input_tokens": 50, "output_tokens": 20},
            "stop_reason": "tool_use",
            "model": "claude-sonnet-4-20250514",
        }
        result = adapter._parse_response(data, time.monotonic(), True)
        assert result.parsed is not None
        assert result.parsed["label"] == "positive"
        assert result.finish_reason == "tool_calls"


# ===================================================================
# Custom adapter tests
# ===================================================================


class TestCustomAdapter:
    def test_isinstance_protocol(self) -> None:
        adapter = CustomAdapter()
        assert isinstance(adapter, ModelProviderPlugin)

    def test_metadata(self) -> None:
        adapter = CustomAdapter(
            plugin_id="my.custom.provider",
            description="My custom LLM",
        )
        assert adapter.metadata.plugin_id == "my.custom.provider"

    def test_provider_type(self) -> None:
        adapter = CustomAdapter()
        assert adapter.provider_type == "custom"

    def test_defaults(self) -> None:
        adapter = CustomAdapter()
        assert adapter.supports_structured_output() is False
        assert adapter.supports_logprobs() is False
        assert adapter.check_health().is_healthy is True
        assert adapter.list_models() == []

    def test_complete_raises_by_default(self) -> None:
        adapter = CustomAdapter()
        with pytest.raises(ProviderError, match="must be overridden"):
            adapter.complete(
                [Message(role="user", content="hi")],
                "model",
            )

    def test_estimate_cost_with_pricing(self) -> None:
        adapter = CustomAdapter(
            cost_per_input_token=0.001,
            cost_per_output_token=0.002,
        )
        est = adapter.estimate_cost(100, 50, "model")
        assert est.input_cost == pytest.approx(0.1)
        assert est.output_cost == pytest.approx(0.1)

    def test_subclass_override(self) -> None:
        class MyProvider(CustomAdapter):
            def complete(
                self,
                messages: list[Message],
                model: str,
                **kwargs: Any,
            ) -> CompletionResult:
                return CompletionResult(content="custom response")

        provider = MyProvider(plugin_id="my.provider")
        result = provider.complete(
            [Message(role="user", content="hi")],
            "model",
        )
        assert result.content == "custom response"
        assert isinstance(provider, ModelProviderPlugin)


# ===================================================================
# Provider detection tests
# ===================================================================


class TestProviderDetection:
    def test_detect_env_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        detector = ProviderDetector()
        providers = detector._detect_env_only()

        assert len(providers) >= 1
        openai_providers = [
            p for p in providers if p.provider_type == "openai_compatible"
        ]
        assert len(openai_providers) == 1
        assert openai_providers[0].auth_ref == "OPENAI_API_KEY"
        assert openai_providers[0].health.is_healthy is True

    def test_detect_no_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        detector = ProviderDetector()
        providers = detector._detect_env_only()
        assert len(providers) == 0

    def test_detect_multiple_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        detector = ProviderDetector()
        providers = detector._detect_env_only()

        types = {p.provider_type for p in providers}
        assert "openai_compatible" in types
        assert "anthropic" in types

    def test_discovered_provider_has_suggested_models(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        detector = ProviderDetector()
        providers = detector._detect_env_only()
        openai = next(p for p in providers if p.provider_type == "openai_compatible")
        assert len(openai.suggested_models) > 0
        assert "gpt-4o" in openai.suggested_models


# ===================================================================
# Structured output enforcer tests
# ===================================================================


class TestStructuredOutputEnforcer:
    def test_native_structured_output(self) -> None:
        provider = _FakeProvider(
            structured=True,
            parsed={"label": "positive", "confidence": 0.9},
            response_content='{"label": "positive", "confidence": 0.9}',
        )
        schema = {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["label", "confidence"],
        }
        enforcer = StructuredOutputEnforcer()
        result = enforcer.enforce(
            provider,
            [Message(role="user", content="label this")],
            "fake-model",
            schema,
        )
        assert result.is_valid is True
        assert result.parsed is not None
        assert result.parsed["label"] == "positive"
        assert result.used_native is True
        assert result.attempts == 1

    def test_prompt_based_fallback(self) -> None:
        provider = _FakeProvider(
            structured=False,
            response_content='{"label": "negative", "confidence": 0.7}',
        )
        schema = {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["label", "confidence"],
        }
        enforcer = StructuredOutputEnforcer()
        result = enforcer.enforce(
            provider,
            [Message(role="user", content="label this")],
            "fake-model",
            schema,
        )
        assert result.is_valid is True
        assert result.parsed is not None
        assert result.parsed["label"] == "negative"
        assert result.used_native is False

    def test_json_in_code_block(self) -> None:
        provider = _FakeProvider(
            structured=False,
            response_content='Here is the result:\n```json\n{"label": "neutral"}\n```',
        )
        schema = {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        }
        enforcer = StructuredOutputEnforcer()
        result = enforcer.enforce(
            provider,
            [Message(role="user", content="label")],
            "fake-model",
            schema,
        )
        assert result.is_valid is True
        assert result.parsed["label"] == "neutral"

    def test_validation_failure_missing_field(self) -> None:
        provider = _FakeProvider(
            structured=False,
            response_content='{"label": "positive"}',
        )
        schema = {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["label", "confidence"],
        }
        enforcer = StructuredOutputEnforcer(max_retries=1)
        result = enforcer.enforce(
            provider,
            [Message(role="user", content="label")],
            "fake-model",
            schema,
        )
        assert result.is_valid is False
        assert any("confidence" in e for e in result.validation_errors)

    def test_validation_failure_wrong_type(self) -> None:
        provider = _FakeProvider(
            structured=False,
            response_content='{"label": 123}',
        )
        schema = {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        }
        enforcer = StructuredOutputEnforcer(max_retries=1)
        result = enforcer.enforce(
            provider,
            [Message(role="user", content="label")],
            "fake-model",
            schema,
        )
        assert result.is_valid is False

    def test_enum_validation(self) -> None:
        provider = _FakeProvider(
            structured=False,
            response_content='{"label": "positive"}',
        )
        schema = {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral"],
                }
            },
            "required": ["label"],
        }
        enforcer = StructuredOutputEnforcer()
        result = enforcer.enforce(
            provider,
            [Message(role="user", content="label")],
            "fake-model",
            schema,
        )
        assert result.is_valid is True

    def test_enum_validation_failure(self) -> None:
        provider = _FakeProvider(
            structured=False,
            response_content='{"label": "invalid_value"}',
        )
        schema = {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "enum": ["positive", "negative"],
                }
            },
            "required": ["label"],
        }
        enforcer = StructuredOutputEnforcer(max_retries=1)
        result = enforcer.enforce(
            provider,
            [Message(role="user", content="label")],
            "fake-model",
            schema,
        )
        assert result.is_valid is False

    def test_unparseable_response(self) -> None:
        provider = _FakeProvider(
            structured=False,
            response_content="I cannot produce JSON output.",
        )
        schema = {
            "type": "object",
            "properties": {"label": {"type": "string"}},
        }
        enforcer = StructuredOutputEnforcer(max_retries=1)
        result = enforcer.enforce(
            provider,
            [Message(role="user", content="label")],
            "fake-model",
            schema,
        )
        assert result.is_valid is False
        assert result.parsed is None


# ===================================================================
# Cost tracking tests
# ===================================================================


class TestCostTracker:
    def test_estimate(self) -> None:
        provider = _FakeProvider()
        tracker = CostTracker()
        est = tracker.estimate(provider, 100, 50, "fake-model")
        assert est.total_cost == pytest.approx(0.003)

    def test_estimate_batch(self) -> None:
        provider = _FakeProvider()
        tracker = CostTracker()
        est = tracker.estimate_batch(provider, 10, 100, 50, "fake-model")
        assert est.total_cost > 0

    def test_record_and_summary(self) -> None:
        tracker = CostTracker()
        est = CostEstimate(input_cost=0.01, output_cost=0.02, total_cost=0.03)
        actual = CostEstimate(input_cost=0.012, output_cost=0.018, total_cost=0.03)

        tracker.record(
            model_id="gpt-4o",
            tokens_input=100,
            tokens_output=50,
            actual_cost=actual,
            estimated_cost=est,
        )

        summary = tracker.get_summary()
        assert summary.entry_count == 1
        assert summary.total_input_tokens == 100
        assert summary.total_output_tokens == 50
        assert summary.total_actual_cost == pytest.approx(0.03)

    def test_running_total(self) -> None:
        tracker = CostTracker()
        for _i in range(3):
            tracker.record(
                model_id="gpt-4o",
                tokens_input=100,
                tokens_output=50,
                actual_cost=CostEstimate(
                    input_cost=0.01, output_cost=0.02, total_cost=0.03
                ),
            )
        assert tracker.running_total() == pytest.approx(0.09)

    def test_budget_alert_warning(self) -> None:
        tracker = CostTracker(budget_limit=0.10, warning_threshold=0.8)
        tracker.record(
            model_id="gpt-4o",
            tokens_input=100,
            tokens_output=50,
            actual_cost=CostEstimate(
                input_cost=0.04, output_cost=0.05, total_cost=0.09
            ),
        )
        alert = tracker.check_budget()
        assert alert is not None
        assert alert.alert_type == "warning"
        assert alert.percentage_used == pytest.approx(0.9)

    def test_budget_alert_exceeded(self) -> None:
        tracker = CostTracker(budget_limit=0.05)
        tracker.record(
            model_id="gpt-4o",
            tokens_input=100,
            tokens_output=50,
            actual_cost=CostEstimate(
                input_cost=0.03, output_cost=0.03, total_cost=0.06
            ),
        )
        alert = tracker.check_budget()
        assert alert is not None
        assert alert.alert_type == "limit_exceeded"

    def test_no_budget_no_alert(self) -> None:
        tracker = CostTracker()
        tracker.record(
            model_id="gpt-4o",
            tokens_input=100,
            tokens_output=50,
            actual_cost=CostEstimate(
                input_cost=100.0, output_cost=100.0, total_cost=200.0
            ),
        )
        assert tracker.check_budget() is None

    def test_cost_delta(self) -> None:
        tracker = CostTracker()
        est = CostEstimate(input_cost=0.01, output_cost=0.02, total_cost=0.03)
        actual = CostEstimate(input_cost=0.015, output_cost=0.025, total_cost=0.04)
        entry = tracker.record(
            model_id="gpt-4o",
            tokens_input=100,
            tokens_output=50,
            actual_cost=actual,
            estimated_cost=est,
        )
        assert entry.delta == pytest.approx(0.01)

    def test_entries_property(self) -> None:
        tracker = CostTracker()
        tracker.record(
            model_id="gpt-4o",
            tokens_input=100,
            tokens_output=50,
            actual_cost=CostEstimate(
                input_cost=0.01, output_cost=0.02, total_cost=0.03
            ),
        )
        assert len(tracker.entries) == 1
        assert tracker.entries[0].model_id == "gpt-4o"


# ===================================================================
# HuggingFace auth tests
# ===================================================================


class TestHuggingFaceAuth:
    def test_resolve_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_TOKEN", "hf_test_token")
        hf = HuggingFaceAuth()
        token, source = hf.resolve_token()
        assert token == "hf_test_token"
        assert source == "HF_TOKEN"

    def test_resolve_token_alt_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.setenv("HUGGING_FACE_HUB_TOKEN", "hf_alt_token")
        hf = HuggingFaceAuth()
        token, source = hf.resolve_token()
        assert token == "hf_alt_token"
        assert source == "HUGGING_FACE_HUB_TOKEN"

    def test_resolve_token_explicit(self) -> None:
        hf = HuggingFaceAuth(token="hf_explicit")
        token, source = hf.resolve_token()
        assert token == "hf_explicit"
        assert source == "explicit"

    def test_resolve_token_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
        hf = HuggingFaceAuth()
        token, source = hf.resolve_token()
        assert token is None
        assert source is None


# ===================================================================
# Offline degradation tests
# ===================================================================


class TestOfflineDegradation:
    def test_offline_error(self) -> None:
        err = OfflineDegradationError("OpenAI")
        assert "OpenAI" in str(err)
        assert "Local features" in str(err)
        assert err.retriable is True

    def test_offline_error_is_provider_error(self) -> None:
        err = OfflineDegradationError("test")
        assert isinstance(err, ProviderError)
