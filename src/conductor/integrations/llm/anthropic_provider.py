"""
conductor.integrations.llm.anthropic_provider - Anthropic Claude Provider
==========================================================================

This module provides the Anthropic/Claude LLM provider for ConductorAI.
It uses the official ``anthropic`` Python SDK (AsyncAnthropic) for async
API calls to Claude models.

Architecture Context:
    This is a concrete implementation of BaseLLMProvider. Agents never import
    this directly — they receive it via dependency injection from the factory.

    ┌──────────────┐    generate()    ┌──────────────────────┐
    │  CodingAgent │ ───────────────→ │  AnthropicProvider   │
    │              │ ← LLMResponse ── │  (AsyncAnthropic)    │
    └──────────────┘                  └──────────┬───────────┘
                                                 │
                                      Anthropic Messages API
                                      (claude-3-opus, sonnet, haiku...)

Installation:
    pip install conductorai[anthropic]

Configuration:
    # conductor.yaml
    llm:
      provider: "anthropic"
      model: "claude-sonnet-4-20250514"
      api_key: "sk-ant-..."       # or set ANTHROPIC_API_KEY env var
      temperature: 0.7
      max_tokens: 4096
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from src.conductor.core.config import LLMConfig
from src.conductor.core.exceptions import LLMProviderError
from src.conductor.integrations.llm.base import BaseLLMProvider, LLMResponse, LLMUsage

logger = structlog.get_logger()


class AnthropicProvider(BaseLLMProvider):
    """LLM provider for Anthropic Claude models.

    Uses the official ``anthropic`` SDK with AsyncAnthropic for non-blocking
    API calls. Supports all Claude models available through the Messages API.

    Attributes:
        _client: The AsyncAnthropic client instance.
        _logger: Structured logger bound with provider context.
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialize the Anthropic provider.

        Args:
            config: LLM configuration with provider, model, api_key, etc.

        Raises:
            LLMProviderError: If the ``anthropic`` package is not installed.
        """
        super().__init__(config)
        self._logger = logger.bind(
            component="anthropic_provider",
            model=config.model,
        )
        self._client = self._create_client()

    def _create_client(self) -> Any:
        """Create the AsyncAnthropic client.

        Uses lazy import so the module can be loaded even without the
        ``anthropic`` package installed — the error only fires on instantiation.

        Returns:
            An AsyncAnthropic client instance.

        Raises:
            LLMProviderError: If the anthropic package is not installed.
        """
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise LLMProviderError(
                message=(
                    "The 'anthropic' package is required for AnthropicProvider. "
                    "Install it with: pip install conductorai[anthropic]"
                ),
                provider="anthropic",
                error_code="LLM_MISSING_DEPENDENCY",
            )

        kwargs: dict[str, Any] = {}
        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        if self._config.api_base_url:
            kwargs["base_url"] = self._config.api_base_url

        return AsyncAnthropic(**kwargs)

    # =========================================================================
    # Core LLM Interface Implementation
    # =========================================================================

    async def generate(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text using the Anthropic Messages API.

        Sends a single user message to the Claude model.

        Args:
            prompt: The input text prompt.
            temperature: Override default temperature for this call.
            max_tokens: Override default max_tokens for this call.
            stop_sequences: Strings that stop generation when encountered.
            **kwargs: Additional keyword arguments passed to the API.

        Returns:
            LLMResponse with generated content and usage stats.

        Raises:
            LLMProviderError: If the API call fails.
        """
        return await self._call_api(
            system_prompt=None,
            user_prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            **kwargs,
        )

    async def generate_with_system(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text with a system prompt using the Anthropic Messages API.

        Anthropic's Messages API accepts ``system`` as a top-level parameter
        (not a message role), so the system prompt is passed separately.

        Args:
            system_prompt: Instructions/context for the model.
            user_prompt: The actual task prompt.
            temperature: Override default temperature.
            max_tokens: Override default max_tokens.
            stop_sequences: Strings that stop generation.
            **kwargs: Additional keyword arguments passed to the API.

        Returns:
            LLMResponse with generated content and usage stats.

        Raises:
            LLMProviderError: If the API call fails.
        """
        return await self._call_api(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            **kwargs,
        )

    # =========================================================================
    # Internal API Call
    # =========================================================================

    async def _call_api(
        self,
        *,
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Make the actual Anthropic Messages API call.

        Handles request building, error mapping, and response conversion.
        """
        from anthropic import (
            APIConnectionError,
            APIStatusError,
            AuthenticationError,
            RateLimitError,
        )

        effective_temp = temperature if temperature is not None else self.temperature
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": effective_max_tokens,
        }

        if system_prompt:
            api_kwargs["system"] = system_prompt
        if effective_temp is not None:
            api_kwargs["temperature"] = effective_temp
        if stop_sequences:
            api_kwargs["stop_sequences"] = stop_sequences

        self._logger.debug(
            "anthropic_api_call",
            model=self.model,
            has_system_prompt=system_prompt is not None,
            max_tokens=effective_max_tokens,
        )

        start_time = time.monotonic()

        try:
            response = await self._client.messages.create(**api_kwargs)
        except AuthenticationError as e:
            raise LLMProviderError(
                message=f"Anthropic authentication failed: {e}",
                provider="anthropic",
                status_code=401,
                error_code="LLM_AUTH_ERROR",
            ) from e
        except RateLimitError as e:
            raise LLMProviderError(
                message=f"Anthropic rate limit exceeded: {e}",
                provider="anthropic",
                status_code=429,
                error_code="LLM_RATE_LIMIT",
            ) from e
        except APIConnectionError as e:
            raise LLMProviderError(
                message=f"Anthropic connection error: {e}",
                provider="anthropic",
                error_code="LLM_CONNECTION_ERROR",
            ) from e
        except APIStatusError as e:
            raise LLMProviderError(
                message=f"Anthropic API error: {e}",
                provider="anthropic",
                status_code=e.status_code,
                error_code="LLM_API_ERROR",
            ) from e

        elapsed_ms = round((time.monotonic() - start_time) * 1000)

        # Anthropic returns content as a list of content blocks.
        # Extract and join all text-type blocks.
        content = ""
        if response.content:
            content = "".join(
                block.text for block in response.content if block.type == "text"
            )

        finish_reason = self._map_stop_reason(response.stop_reason)

        usage = LLMUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

        self._logger.debug(
            "anthropic_api_response",
            model=response.model,
            finish_reason=finish_reason,
            total_tokens=usage.total_tokens,
            latency_ms=elapsed_ms,
        )

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage,
            finish_reason=finish_reason,
            metadata={
                "provider": "anthropic",
                "response_id": response.id,
                "latency_ms": elapsed_ms,
                "stop_reason": response.stop_reason,
            },
            created_at=datetime.now(timezone.utc),
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _map_stop_reason(stop_reason: Optional[str]) -> str:
        """Map Anthropic stop_reason to LLMResponse finish_reason.

        Anthropic uses:
            - "end_turn": Model finished naturally
            - "stop_sequence": Hit a stop sequence
            - "max_tokens": Hit the token limit

        We map these to our standard: "stop", "stop", "length".
        """
        mapping = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
        }
        return mapping.get(stop_reason or "", "stop")

    # =========================================================================
    # Validation & Model Listing
    # =========================================================================

    async def validate(self) -> bool:
        """Validate that the Anthropic provider is configured correctly.

        Checks that an API key is available (from config or environment).

        Returns:
            True if an API key is found, False otherwise.
        """
        if not self._config.api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            self._logger.warning("anthropic_no_api_key")
            return False
        return True

    def get_available_models(self) -> list[str]:
        """Return known Anthropic Claude models.

        Returns:
            List of model identifier strings.
        """
        return [
            "claude-opus-4-0-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]
