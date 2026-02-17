"""
Tests for conductor.integrations.llm
======================================

These tests verify the LLM provider abstraction layer:
    - LLMResponse and LLMUsage models
    - MockLLMProvider (queue, smart defaults, call tracking, error simulation)
    - create_llm_provider factory function
    - BaseLLMProvider interface contract

All tests use the MockLLMProvider — no real API calls are made.
"""

import pytest

from conductor.core.config import LLMConfig
from conductor.integrations.llm.base import BaseLLMProvider, LLMResponse, LLMUsage
from conductor.integrations.llm.factory import create_llm_provider
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Tests: LLMUsage Model
# =============================================================================
class TestLLMUsage:
    """Tests for the LLMUsage Pydantic model."""

    def test_default_values(self) -> None:
        """Default usage should be all zeros."""
        usage = LLMUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_custom_values(self) -> None:
        """Usage should accept custom token counts."""
        usage = LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_serialization(self) -> None:
        """Usage should serialize to dict cleanly."""
        usage = LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        data = usage.model_dump()
        assert data["prompt_tokens"] == 10
        assert data["total_tokens"] == 30


# =============================================================================
# Tests: LLMResponse Model
# =============================================================================
class TestLLMResponse:
    """Tests for the LLMResponse Pydantic model."""

    def test_basic_response(self) -> None:
        """Response should store content, model, and defaults."""
        resp = LLMResponse(content="Hello world", model="gpt-4")
        assert resp.content == "Hello world"
        assert resp.model == "gpt-4"
        assert resp.finish_reason == "stop"
        assert resp.created_at is not None

    def test_with_usage(self) -> None:
        """Response should include token usage."""
        usage = LLMUsage(prompt_tokens=50, completion_tokens=30, total_tokens=80)
        resp = LLMResponse(content="test", model="mock", usage=usage)
        assert resp.usage.total_tokens == 80

    def test_with_metadata(self) -> None:
        """Response should carry arbitrary metadata."""
        resp = LLMResponse(
            content="test",
            model="mock",
            metadata={"request_id": "abc-123", "latency_ms": 150},
        )
        assert resp.metadata["request_id"] == "abc-123"

    def test_error_finish_reason(self) -> None:
        """Response can indicate generation error."""
        resp = LLMResponse(content="", model="mock", finish_reason="error")
        assert resp.finish_reason == "error"


# =============================================================================
# Tests: MockLLMProvider Initialization
# =============================================================================
class TestMockLLMProviderInit:
    """Tests for MockLLMProvider initialization."""

    def test_default_config(self) -> None:
        """MockLLMProvider should create with default config if None."""
        provider = MockLLMProvider()
        assert provider.provider_name == "mock"
        assert provider.model == "mock-model"

    def test_custom_config(self) -> None:
        """MockLLMProvider should respect custom config."""
        config = LLMConfig(provider="mock", model="custom-model", temperature=0.5)
        provider = MockLLMProvider(config)
        assert provider.model == "custom-model"
        assert provider.temperature == 0.5

    def test_initial_state(self) -> None:
        """Provider should start with empty queue and history."""
        provider = MockLLMProvider()
        assert provider.call_count == 0
        assert provider.queue_size == 0
        assert provider.call_history == []

    def test_repr(self) -> None:
        """repr should show provider and model."""
        provider = MockLLMProvider()
        assert "MockLLMProvider" in repr(provider)
        assert "mock" in repr(provider)


# =============================================================================
# Tests: MockLLMProvider Queue
# =============================================================================
class TestMockLLMProviderQueue:
    """Tests for the response queue mechanism."""

    async def test_queue_response_text(self) -> None:
        """Queued text response should be returned by generate()."""
        provider = MockLLMProvider()
        provider.queue_response("Hello from queue!")

        resp = await provider.generate("Say hello")
        assert resp.content == "Hello from queue!"

    async def test_queue_fifo_order(self) -> None:
        """Queued responses should be returned in FIFO order."""
        provider = MockLLMProvider()
        provider.queue_response("First")
        provider.queue_response("Second")
        provider.queue_response("Third")

        r1 = await provider.generate("p1")
        r2 = await provider.generate("p2")
        r3 = await provider.generate("p3")

        assert r1.content == "First"
        assert r2.content == "Second"
        assert r3.content == "Third"

    async def test_queue_llm_response(self) -> None:
        """Fully constructed LLMResponse should be returned from queue."""
        provider = MockLLMProvider()
        custom = LLMResponse(
            content="Custom",
            model="special-model",
            finish_reason="length",
        )
        provider.queue_llm_response(custom)

        resp = await provider.generate("test")
        assert resp.content == "Custom"
        assert resp.model == "special-model"
        assert resp.finish_reason == "length"

    async def test_clear_queue(self) -> None:
        """clear_queue should remove all queued responses."""
        provider = MockLLMProvider()
        provider.queue_response("A")
        provider.queue_response("B")
        assert provider.queue_size == 2

        provider.clear_queue()
        assert provider.queue_size == 0

    async def test_queue_with_metadata(self) -> None:
        """Queued responses should carry metadata."""
        provider = MockLLMProvider()
        provider.queue_response("test", metadata={"key": "value"})

        resp = await provider.generate("p")
        assert resp.metadata["key"] == "value"


# =============================================================================
# Tests: MockLLMProvider Smart Defaults
# =============================================================================
class TestMockLLMProviderSmartDefaults:
    """Tests for context-aware default responses."""

    async def test_code_keyword_returns_code(self) -> None:
        """Prompt with 'code' or 'generate' should return mock code."""
        provider = MockLLMProvider()
        resp = await provider.generate("Generate code for a REST API")
        assert "def " in resp.content or "function" in resp.content

    async def test_review_keyword_returns_review(self) -> None:
        """Prompt with 'review' should return mock review.

        Note: keyword detection is order-dependent — 'code' keywords
        are checked before 'review'. So we use a prompt that does NOT
        also contain code keywords like 'code', 'generate', etc.
        """
        provider = MockLLMProvider()
        resp = await provider.generate("Please review this for quality issues")
        assert "Review" in resp.content or "Score" in resp.content

    async def test_test_keyword_returns_tests(self) -> None:
        """Prompt with 'test' should return mock test results.

        Note: keyword detection checks 'code' keywords first, so
        we avoid using words like 'function' or 'class' in the prompt.
        """
        provider = MockLLMProvider()
        resp = await provider.generate("Run the test suite and verify results")
        assert "Test" in resp.content

    async def test_unknown_prompt_returns_default(self) -> None:
        """Unknown prompt should return the default response text."""
        provider = MockLLMProvider(default_response="Custom default")
        resp = await provider.generate("Something unrelated")
        assert resp.content == "Custom default"

    async def test_smart_default_has_metadata(self) -> None:
        """Smart default responses should have source metadata."""
        provider = MockLLMProvider()
        resp = await provider.generate("Generate a function")
        assert resp.metadata.get("source") == "smart_default"


# =============================================================================
# Tests: MockLLMProvider Call Tracking
# =============================================================================
class TestMockLLMProviderCallTracking:
    """Tests for call history tracking."""

    async def test_call_recorded(self) -> None:
        """Every generate() call should be recorded in history."""
        provider = MockLLMProvider()
        await provider.generate("First prompt")
        await provider.generate("Second prompt")

        assert provider.call_count == 2
        assert provider.call_history[0]["prompt"] == "First prompt"
        assert provider.call_history[1]["prompt"] == "Second prompt"

    async def test_system_prompt_recorded(self) -> None:
        """generate_with_system() should record system prompt too."""
        provider = MockLLMProvider()
        await provider.generate_with_system("Be a coder", "Write code")

        assert provider.call_count == 1
        assert provider.call_history[0]["system_prompt"] == "Be a coder"
        assert provider.call_history[0]["prompt"] == "Write code"

    async def test_clear_history(self) -> None:
        """clear_history should reset call records."""
        provider = MockLLMProvider()
        await provider.generate("test")
        assert provider.call_count == 1

        provider.clear_history()
        assert provider.call_count == 0

    async def test_kwargs_recorded(self) -> None:
        """Extra kwargs should be recorded in call history."""
        provider = MockLLMProvider()
        await provider.generate("test", temperature=0.5, max_tokens=100)

        record = provider.call_history[0]
        assert record["temperature"] == 0.5
        assert record["max_tokens"] == 100


# =============================================================================
# Tests: MockLLMProvider Error Simulation
# =============================================================================
class TestMockLLMProviderErrors:
    """Tests for error simulation."""

    async def test_should_fail_raises(self) -> None:
        """When _should_fail is True, generate() should raise RuntimeError."""
        provider = MockLLMProvider()
        provider.set_should_fail(True, "API overloaded")

        with pytest.raises(RuntimeError, match="API overloaded"):
            await provider.generate("test")

    async def test_should_fail_records_call(self) -> None:
        """Even when failing, the call should be recorded."""
        provider = MockLLMProvider()
        provider.set_should_fail(True)

        with pytest.raises(RuntimeError):
            await provider.generate("test")

        assert provider.call_count == 1

    async def test_disable_failure(self) -> None:
        """set_should_fail(False) should restore normal operation."""
        provider = MockLLMProvider()
        provider.set_should_fail(True)
        provider.set_should_fail(False)

        resp = await provider.generate("test")
        assert resp.content is not None

    async def test_system_prompt_failure(self) -> None:
        """generate_with_system should also fail when _should_fail is True."""
        provider = MockLLMProvider()
        provider.set_should_fail(True, "Connection timeout")

        with pytest.raises(RuntimeError, match="Connection timeout"):
            await provider.generate_with_system("system", "user")


# =============================================================================
# Tests: MockLLMProvider Validation
# =============================================================================
class TestMockLLMProviderValidation:
    """Tests for validation and model listing."""

    async def test_validate_always_true(self) -> None:
        """Mock provider validation always succeeds."""
        provider = MockLLMProvider()
        assert await provider.validate() is True

    def test_available_models(self) -> None:
        """Mock provider should list mock models."""
        provider = MockLLMProvider()
        models = provider.get_available_models()
        assert len(models) >= 1
        assert "mock-model" in models


# =============================================================================
# Tests: create_llm_provider Factory
# =============================================================================
class TestCreateLLMProvider:
    """Tests for the factory function."""

    def test_create_mock_provider(self) -> None:
        """Factory should create MockLLMProvider for 'mock'."""
        config = LLMConfig(provider="mock")
        provider = create_llm_provider(config)
        assert isinstance(provider, MockLLMProvider)

    def test_create_mock_case_insensitive(self) -> None:
        """Factory should be case-insensitive."""
        config = LLMConfig(provider="Mock")
        provider = create_llm_provider(config)
        assert isinstance(provider, MockLLMProvider)

    def test_unknown_provider_raises(self) -> None:
        """Factory should raise ValueError for unknown providers."""
        config = LLMConfig(provider="unknown-provider")
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_provider(config)

    def test_factory_passes_config(self) -> None:
        """Factory should pass config to provider."""
        config = LLMConfig(provider="mock", model="custom-test", temperature=0.3)
        provider = create_llm_provider(config)
        assert provider.model == "custom-test"
        assert provider.temperature == 0.3
