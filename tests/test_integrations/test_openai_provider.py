"""
Tests for conductor.integrations.llm.openai_provider
=======================================================

Tests the OpenAIProvider without making real API calls.
All OpenAI SDK interactions are mocked with unittest.mock.
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
    """Create an LLMConfig for OpenAI with sensible test defaults."""
    defaults = {
        "provider": "openai",
        "model": "gpt-4",
        "api_key": "sk-test-key",
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    defaults.update(overrides)
    return LLMConfig(**defaults)


def _mock_openai_response(
    content_text: str = "Generated code here",
    model: str = "gpt-4",
    finish_reason: str = "stop",
    prompt_tokens: int = 50,
    completion_tokens: int = 100,
    total_tokens: int = 150,
    response_id: str = "chatcmpl-test123",
) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response."""
    mock_message = MagicMock()
    mock_message.content = content_text

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = finish_reason

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = prompt_tokens
    mock_usage.completion_tokens = completion_tokens
    mock_usage.total_tokens = total_tokens

    mock_response = MagicMock()
    mock_response.id = response_id
    mock_response.model = model
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    mock_response.system_fingerprint = "fp_test123"

    return mock_response


def _create_provider(config: LLMConfig | None = None) -> object:
    """Create an OpenAIProvider with a mocked client."""
    from conductor.integrations.llm.openai_provider import OpenAIProvider

    with patch.object(OpenAIProvider, "_create_client", return_value=MagicMock()):
        provider = OpenAIProvider(config or _make_config())
    return provider


# =============================================================================
# Initialization Tests
# =============================================================================

class TestOpenAIProviderInit:
    """Tests for OpenAIProvider initialization."""

    def test_creates_with_config(self) -> None:
        """Provider should store config and set properties."""
        provider = _create_provider()
        assert provider.provider_name == "openai"
        assert provider.model == "gpt-4"
        assert provider.temperature == 0.7
        assert provider.max_tokens == 1024

    def test_creates_with_custom_model(self) -> None:
        """Provider should accept any model name."""
        config = _make_config(model="gpt-4o")
        provider = _create_provider(config)
        assert provider.model == "gpt-4o"

    def test_missing_sdk_raises_error(self) -> None:
        """Instantiation without openai SDK should raise LLMProviderError."""
        config = _make_config()
        with patch.dict("sys.modules", {"openai": None}):
            with patch(
                "conductor.integrations.llm.openai_provider.OpenAIProvider._create_client",
                side_effect=LLMProviderError(
                    message="The 'openai' package is required",
                    provider="openai",
                    error_code="LLM_MISSING_DEPENDENCY",
                ),
            ):
                with pytest.raises(LLMProviderError) as exc_info:
                    from conductor.integrations.llm.openai_provider import OpenAIProvider
                    OpenAIProvider(config)
                assert exc_info.value.error_code == "LLM_MISSING_DEPENDENCY"

    def test_repr(self) -> None:
        """repr should show provider and model."""
        provider = _create_provider()
        r = repr(provider)
        assert "OpenAIProvider" in r
        assert "openai" in r


# =============================================================================
# Generate Tests
# =============================================================================

class TestOpenAIProviderGenerate:
    """Tests for generate() method."""

    async def test_generate_basic(self) -> None:
        """generate() should call chat.completions.create and return LLMResponse."""
        provider = _create_provider()
        mock_resp = _mock_openai_response(content_text="Hello world")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("Say hello")

        assert isinstance(response, LLMResponse)
        assert response.content == "Hello world"
        assert response.model == "gpt-4"
        assert response.finish_reason == "stop"

        # Verify API was called with correct structure
        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["messages"] == [{"role": "user", "content": "Say hello"}]

    async def test_generate_with_temperature_override(self) -> None:
        """Temperature override should be passed to the API."""
        provider = _create_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response()
        )

        await provider.generate("test", temperature=0.2)

        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.2

    async def test_generate_with_max_tokens_override(self) -> None:
        """Max tokens override should be passed to the API."""
        provider = _create_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response()
        )

        await provider.generate("test", max_tokens=2048)

        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 2048

    async def test_generate_with_stop_sequences(self) -> None:
        """Stop sequences should be passed as 'stop' parameter."""
        provider = _create_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response()
        )

        await provider.generate("test", stop_sequences=["```", "END"])

        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["stop"] == ["```", "END"]

    async def test_generate_uses_config_defaults(self) -> None:
        """When no overrides, config temperature/max_tokens should be used."""
        provider = _create_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response()
        )

        await provider.generate("test")

        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 1024


# =============================================================================
# Generate With System Tests
# =============================================================================

class TestOpenAIProviderGenerateWithSystem:
    """Tests for generate_with_system() method."""

    async def test_system_prompt_as_message_role(self) -> None:
        """System prompt should be sent as a system role message."""
        provider = _create_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response()
        )

        await provider.generate_with_system(
            system_prompt="You are a Python expert.",
            user_prompt="Write a function.",
        )

        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["messages"] == [
            {"role": "system", "content": "You are a Python expert."},
            {"role": "user", "content": "Write a function."},
        ]


# =============================================================================
# Response Mapping Tests
# =============================================================================

class TestOpenAIProviderResponseMapping:
    """Tests for SDK response → LLMResponse mapping."""

    async def test_usage_mapping(self) -> None:
        """OpenAI usage fields should map to LLMUsage."""
        provider = _create_provider()
        mock_resp = _mock_openai_response(
            prompt_tokens=30, completion_tokens=70, total_tokens=100
        )
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")

        assert response.usage.prompt_tokens == 30
        assert response.usage.completion_tokens == 70
        assert response.usage.total_tokens == 100

    async def test_finish_reason_stop(self) -> None:
        """OpenAI 'stop' should map to 'stop'."""
        provider = _create_provider()
        mock_resp = _mock_openai_response(finish_reason="stop")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.finish_reason == "stop"

    async def test_finish_reason_length(self) -> None:
        """OpenAI 'length' should map to 'length'."""
        provider = _create_provider()
        mock_resp = _mock_openai_response(finish_reason="length")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.finish_reason == "length"

    async def test_finish_reason_content_filter(self) -> None:
        """OpenAI 'content_filter' should map to 'error'."""
        provider = _create_provider()
        mock_resp = _mock_openai_response(finish_reason="content_filter")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.finish_reason == "error"

    async def test_metadata_includes_provider(self) -> None:
        """Metadata should include provider, response_id, and latency."""
        provider = _create_provider()
        mock_resp = _mock_openai_response(response_id="chatcmpl-abc")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")

        assert response.metadata["provider"] == "openai"
        assert response.metadata["response_id"] == "chatcmpl-abc"
        assert "latency_ms" in response.metadata
        assert response.metadata["system_fingerprint"] == "fp_test123"

    async def test_model_from_response(self) -> None:
        """Model should come from the API response, not config."""
        provider = _create_provider()
        mock_resp = _mock_openai_response(model="gpt-4-0125-preview")
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.model == "gpt-4-0125-preview"

    async def test_none_content_returns_empty_string(self) -> None:
        """None content from API should return empty string."""
        provider = _create_provider()
        mock_resp = _mock_openai_response()
        mock_resp.choices[0].message.content = None
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.content == ""

    async def test_none_usage_returns_zeros(self) -> None:
        """None usage from API should return zero token counts."""
        provider = _create_provider()
        mock_resp = _mock_openai_response()
        mock_resp.usage = None
        provider._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        response = await provider.generate("test")
        assert response.usage.prompt_tokens == 0
        assert response.usage.completion_tokens == 0
        assert response.usage.total_tokens == 0


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestOpenAIProviderErrorHandling:
    """Tests for error handling."""

    async def test_auth_error(self) -> None:
        """AuthenticationError should raise LLMProviderError with LLM_AUTH_ERROR."""
        from openai import AuthenticationError

        provider = _create_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_error = AuthenticationError(
            message="Invalid API key",
            response=mock_resp,
            body=None,
        )
        provider._client.chat.completions.create = AsyncMock(side_effect=mock_error)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate("test")

        assert exc_info.value.error_code == "LLM_AUTH_ERROR"
        assert exc_info.value.status_code == 401
        assert exc_info.value.provider == "openai"

    async def test_rate_limit_error(self) -> None:
        """RateLimitError should raise LLMProviderError with LLM_RATE_LIMIT."""
        from openai import RateLimitError

        provider = _create_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_error = RateLimitError(
            message="Rate limit exceeded",
            response=mock_resp,
            body=None,
        )
        provider._client.chat.completions.create = AsyncMock(side_effect=mock_error)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate("test")

        assert exc_info.value.error_code == "LLM_RATE_LIMIT"
        assert exc_info.value.status_code == 429

    async def test_connection_error(self) -> None:
        """APIConnectionError should raise LLMProviderError with LLM_CONNECTION_ERROR."""
        from openai import APIConnectionError

        provider = _create_provider()
        mock_error = APIConnectionError(request=MagicMock())
        provider._client.chat.completions.create = AsyncMock(side_effect=mock_error)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate("test")

        assert exc_info.value.error_code == "LLM_CONNECTION_ERROR"

    async def test_api_status_error(self) -> None:
        """APIStatusError should raise LLMProviderError with LLM_API_ERROR."""
        from openai import APIStatusError

        provider = _create_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_error = APIStatusError(
            message="Internal server error",
            response=mock_resp,
            body=None,
        )
        provider._client.chat.completions.create = AsyncMock(side_effect=mock_error)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate("test")

        assert exc_info.value.error_code == "LLM_API_ERROR"
        assert exc_info.value.status_code == 500


# =============================================================================
# Validation Tests
# =============================================================================

class TestOpenAIProviderValidation:
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
        """validate() should return True when OPENAI_API_KEY is set."""
        config = _make_config(api_key=None)
        provider = _create_provider(config)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-env"}):
            assert await provider.validate() is True

    def test_get_available_models(self) -> None:
        """get_available_models() should return known OpenAI models."""
        provider = _create_provider()
        models = provider.get_available_models()
        assert len(models) > 0
        assert "gpt-4o" in models


# =============================================================================
# Factory Integration Tests
# =============================================================================

class TestOpenAIProviderFactory:
    """Tests for factory integration."""

    def test_factory_creates_openai_provider(self) -> None:
        """create_llm_provider with 'openai' should create OpenAIProvider."""
        from conductor.integrations.llm.openai_provider import OpenAIProvider
        from conductor.integrations.llm.factory import create_llm_provider

        config = _make_config()
        with patch.object(OpenAIProvider, "_create_client", return_value=MagicMock()):
            provider = create_llm_provider(config)

        assert isinstance(provider, OpenAIProvider)

    def test_factory_case_insensitive(self) -> None:
        """Factory should handle case-insensitive provider names."""
        from conductor.integrations.llm.openai_provider import OpenAIProvider
        from conductor.integrations.llm.factory import create_llm_provider

        config = _make_config(provider="OpenAI")
        with patch.object(OpenAIProvider, "_create_client", return_value=MagicMock()):
            provider = create_llm_provider(config)

        assert isinstance(provider, OpenAIProvider)
