"""
Tests for conductor.integrations.llm.anthropic_provider
=========================================================

Tests the AnthropicProvider without making real API calls.
All Anthropic SDK interactions are mocked with unittest.mock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.core.config import LLMConfig
from conductor.core.exceptions import LLMProviderError
from conductor.integrations.llm.base import LLMResponse, LLMUsage


# =============================================================================
# Helpers
# =============================================================================

def _make_config(**overrides: object) -> LLMConfig:
    """Create an LLMConfig for Anthropic with sensible test defaults."""
    defaults = {
        "provider": "anthropic",
        "model": "claude-3-sonnet-20240229",
        "api_key": "sk-ant-test-key",
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    defaults.update(overrides)
    return LLMConfig(**defaults)


def _mock_anthropic_response(
    content_text: str = "Generated code here",
    model: str = "claude-3-sonnet-20240229",
    stop_reason: str = "end_turn",
    input_tokens: int = 50,
    output_tokens: int = 100,
    response_id: str = "msg_test123",
) -> MagicMock:
    """Build a mock Anthropic Message response."""
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = content_text

    mock_usage = MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens

    mock_response = MagicMock()
    mock_response.id = response_id
    mock_response.model = model
    mock_response.content = [mock_block]
    mock_response.usage = mock_usage
    mock_response.stop_reason = stop_reason

    return mock_response


def _create_provider(config: LLMConfig | None = None) -> object:
    """Create an AnthropicProvider with a mocked client."""
    from conductor.integrations.llm.anthropic_provider import AnthropicProvider

    with patch.object(AnthropicProvider, "_create_client", return_value=MagicMock()):
        provider = AnthropicProvider(config or _make_config())
    return provider


# =============================================================================
# Initialization Tests
# =============================================================================

class TestAnthropicProviderInit:
    """Tests for AnthropicProvider initialization."""

    def test_creates_with_config(self) -> None:
        """Provider should store config and set properties."""
        provider = _create_provider()
        assert provider.provider_name == "anthropic"
        assert provider.model == "claude-3-sonnet-20240229"
        assert provider.temperature == 0.7
        assert provider.max_tokens == 1024

    def test_creates_with_custom_model(self) -> None:
        """Provider should accept any model name."""
        config = _make_config(model="claude-3-opus-20240229")
        provider = _create_provider(config)
        assert provider.model == "claude-3-opus-20240229"

    def test_missing_sdk_raises_error(self) -> None:
        """Instantiation without anthropic SDK should raise LLMProviderError."""
        config = _make_config()
        with patch.dict("sys.modules", {"anthropic": None}):
            with patch(
                "conductor.integrations.llm.anthropic_provider.AnthropicProvider._create_client",
                side_effect=LLMProviderError(
                    message="The 'anthropic' package is required",
                    provider="anthropic",
                    error_code="LLM_MISSING_DEPENDENCY",
                ),
            ):
                with pytest.raises(LLMProviderError) as exc_info:
                    from conductor.integrations.llm.anthropic_provider import AnthropicProvider
                    AnthropicProvider(config)
                assert exc_info.value.error_code == "LLM_MISSING_DEPENDENCY"

    def test_repr(self) -> None:
        """repr should show provider and model."""
        provider = _create_provider()
        r = repr(provider)
        assert "AnthropicProvider" in r
        assert "anthropic" in r


# =============================================================================
# Generate Tests
# =============================================================================

class TestAnthropicProviderGenerate:
    """Tests for generate() method."""

    async def test_generate_basic(self) -> None:
        """generate() should call messages.create and return LLMResponse."""
        provider = _create_provider()
        mock_resp = _mock_anthropic_response(content_text="Hello world")
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("Say hello")

        assert isinstance(response, LLMResponse)
        assert response.content == "Hello world"
        assert response.model == "claude-3-sonnet-20240229"
        assert response.finish_reason == "stop"

        # Verify API was called with correct structure
        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-sonnet-20240229"
        assert call_kwargs["messages"] == [{"role": "user", "content": "Say hello"}]
        assert "system" not in call_kwargs

    async def test_generate_with_temperature_override(self) -> None:
        """Temperature override should be passed to the API."""
        provider = _create_provider()
        provider._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response()
        )

        await provider.generate("test", temperature=0.2)

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.2

    async def test_generate_with_max_tokens_override(self) -> None:
        """Max tokens override should be passed to the API."""
        provider = _create_provider()
        provider._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response()
        )

        await provider.generate("test", max_tokens=2048)

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 2048

    async def test_generate_with_stop_sequences(self) -> None:
        """Stop sequences should be passed to the API."""
        provider = _create_provider()
        provider._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response()
        )

        await provider.generate("test", stop_sequences=["```", "END"])

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["stop_sequences"] == ["```", "END"]

    async def test_generate_uses_config_defaults(self) -> None:
        """When no overrides, config temperature/max_tokens should be used."""
        provider = _create_provider()
        provider._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response()
        )

        await provider.generate("test")

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 1024


# =============================================================================
# Generate With System Tests
# =============================================================================

class TestAnthropicProviderGenerateWithSystem:
    """Tests for generate_with_system() method."""

    async def test_system_prompt_as_top_level_param(self) -> None:
        """System prompt should be passed as system= parameter (not a message)."""
        provider = _create_provider()
        provider._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response()
        )

        await provider.generate_with_system(
            system_prompt="You are a Python expert.",
            user_prompt="Write a function.",
        )

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a Python expert."
        assert call_kwargs["messages"] == [
            {"role": "user", "content": "Write a function."}
        ]


# =============================================================================
# Response Mapping Tests
# =============================================================================

class TestAnthropicProviderResponseMapping:
    """Tests for SDK response → LLMResponse mapping."""

    async def test_usage_mapping(self) -> None:
        """Anthropic input_tokens/output_tokens should map to LLMUsage."""
        provider = _create_provider()
        mock_resp = _mock_anthropic_response(input_tokens=30, output_tokens=70)
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")

        assert response.usage.prompt_tokens == 30
        assert response.usage.completion_tokens == 70
        assert response.usage.total_tokens == 100

    async def test_stop_reason_end_turn(self) -> None:
        """Anthropic 'end_turn' should map to 'stop'."""
        provider = _create_provider()
        mock_resp = _mock_anthropic_response(stop_reason="end_turn")
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.finish_reason == "stop"

    async def test_stop_reason_max_tokens(self) -> None:
        """Anthropic 'max_tokens' should map to 'length'."""
        provider = _create_provider()
        mock_resp = _mock_anthropic_response(stop_reason="max_tokens")
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.finish_reason == "length"

    async def test_stop_reason_stop_sequence(self) -> None:
        """Anthropic 'stop_sequence' should map to 'stop'."""
        provider = _create_provider()
        mock_resp = _mock_anthropic_response(stop_reason="stop_sequence")
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.finish_reason == "stop"

    async def test_metadata_includes_provider(self) -> None:
        """Metadata should include provider, response_id, and latency."""
        provider = _create_provider()
        mock_resp = _mock_anthropic_response(response_id="msg_abc")
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")

        assert response.metadata["provider"] == "anthropic"
        assert response.metadata["response_id"] == "msg_abc"
        assert "latency_ms" in response.metadata

    async def test_model_from_response(self) -> None:
        """Model should come from the API response, not config."""
        provider = _create_provider()
        mock_resp = _mock_anthropic_response(model="claude-3-opus-20240229")
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.model == "claude-3-opus-20240229"

    async def test_multiple_content_blocks(self) -> None:
        """Multiple text content blocks should be joined."""
        provider = _create_provider()

        block1 = MagicMock()
        block1.type = "text"
        block1.text = "Part 1. "

        block2 = MagicMock()
        block2.type = "text"
        block2.text = "Part 2."

        mock_resp = _mock_anthropic_response()
        mock_resp.content = [block1, block2]
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.content == "Part 1. Part 2."

    async def test_empty_content(self) -> None:
        """Empty content list should return empty string."""
        provider = _create_provider()
        mock_resp = _mock_anthropic_response()
        mock_resp.content = []
        provider._client.messages.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.content == ""


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestAnthropicProviderErrorHandling:
    """Tests for error handling."""

    async def test_auth_error(self) -> None:
        """AuthenticationError should raise LLMProviderError with LLM_AUTH_ERROR."""
        from anthropic import AuthenticationError

        provider = _create_provider()
        mock_error = AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )
        provider._client.messages.create = AsyncMock(side_effect=mock_error)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate("test")

        assert exc_info.value.error_code == "LLM_AUTH_ERROR"
        assert exc_info.value.status_code == 401
        assert exc_info.value.provider == "anthropic"

    async def test_rate_limit_error(self) -> None:
        """RateLimitError should raise LLMProviderError with LLM_RATE_LIMIT."""
        from anthropic import RateLimitError

        provider = _create_provider()
        mock_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body=None,
        )
        provider._client.messages.create = AsyncMock(side_effect=mock_error)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate("test")

        assert exc_info.value.error_code == "LLM_RATE_LIMIT"
        assert exc_info.value.status_code == 429

    async def test_connection_error(self) -> None:
        """APIConnectionError should raise LLMProviderError with LLM_CONNECTION_ERROR."""
        from anthropic import APIConnectionError

        provider = _create_provider()
        mock_error = APIConnectionError(request=MagicMock())
        provider._client.messages.create = AsyncMock(side_effect=mock_error)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate("test")

        assert exc_info.value.error_code == "LLM_CONNECTION_ERROR"

    async def test_api_status_error(self) -> None:
        """APIStatusError should raise LLMProviderError with LLM_API_ERROR."""
        from anthropic import APIStatusError

        provider = _create_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_error = APIStatusError(
            message="Internal server error",
            response=mock_resp,
            body=None,
        )
        provider._client.messages.create = AsyncMock(side_effect=mock_error)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate("test")

        assert exc_info.value.error_code == "LLM_API_ERROR"
        assert exc_info.value.status_code == 500


# =============================================================================
# Validation Tests
# =============================================================================

class TestAnthropicProviderValidation:
    """Tests for validate() method."""

    async def test_validate_with_api_key(self) -> None:
        """validate() should return True when API key is in config."""
        provider = _create_provider()
        assert await provider.validate() is True

    async def test_validate_without_api_key_and_no_env(self) -> None:
        """validate() should return False when no key available."""
        config = _make_config(api_key=None)
        provider = _create_provider(config)
        with patch.dict("os.environ", {}, clear=True):
            assert await provider.validate() is False

    async def test_validate_with_env_var(self) -> None:
        """validate() should return True when ANTHROPIC_API_KEY is set."""
        config = _make_config(api_key=None)
        provider = _create_provider(config)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-env"}):
            assert await provider.validate() is True

    def test_get_available_models(self) -> None:
        """get_available_models() should return known Claude models."""
        provider = _create_provider()
        models = provider.get_available_models()
        assert len(models) > 0
        assert any("claude" in m for m in models)


# =============================================================================
# Factory Integration Tests
# =============================================================================

class TestAnthropicProviderFactory:
    """Tests for factory integration."""

    def test_factory_creates_anthropic_provider(self) -> None:
        """create_llm_provider with 'anthropic' should create AnthropicProvider."""
        from conductor.integrations.llm.anthropic_provider import AnthropicProvider
        from conductor.integrations.llm.factory import create_llm_provider

        config = _make_config()
        with patch.object(AnthropicProvider, "_create_client", return_value=MagicMock()):
            provider = create_llm_provider(config)

        assert isinstance(provider, AnthropicProvider)

    def test_factory_case_insensitive(self) -> None:
        """Factory should handle case-insensitive provider names."""
        from conductor.integrations.llm.anthropic_provider import AnthropicProvider
        from conductor.integrations.llm.factory import create_llm_provider

        config = _make_config(provider="Anthropic")
        with patch.object(AnthropicProvider, "_create_client", return_value=MagicMock()):
            provider = create_llm_provider(config)

        assert isinstance(provider, AnthropicProvider)
