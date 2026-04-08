"""
conductor.integrations.llm.openai_provider - OpenAI Provider
===============================================================

This module provides the OpenAI LLM provider for ConductorAI.
It uses the official ``openai`` Python SDK (AsyncOpenAI) for async
API calls to GPT models.

Architecture Context:
    This is a concrete implementation of BaseLLMProvider. Agents never import
    this directly — they receive it via dependency injection from the factory.

    ┌──────────────┐    generate()    ┌──────────────────────┐
    │  CodingAgent │ ───────────────→ │  OpenAIProvider      │
    │              │ ← LLMResponse ── │  (AsyncOpenAI)       │
    └──────────────┘                  └──────────┬───────────┘
                                                 │
                                      OpenAI Chat Completions API
                                      (gpt-4o, gpt-4, gpt-3.5-turbo...)

Installation:
    pip install conductorai[openai]

Configuration:
    # conductor.yaml
    llm:
      provider: "openai"
      model: "gpt-4o"
      api_key: "sk-..."          # or set OPENAI_API_KEY env var
      temperature: 0.7
      max_tokens: 4096
      # api_base_url: "https://your-proxy.example.com/v1"  # optional
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


class OpenAIProvider(BaseLLMProvider):
    """LLM provider for OpenAI models (GPT-4o, GPT-4, GPT-3.5-turbo, etc.).

    Uses the official ``openai`` SDK with AsyncOpenAI for non-blocking
    API calls via the Chat Completions endpoint.

    Attributes:
        _client: The AsyncOpenAI client instance.
        _logger: Structured logger bound with provider context.
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialize the OpenAI provider.

        Args:
            config: LLM configuration with provider, model, api_key, etc.

        Raises:
            LLMProviderError: If the ``openai`` package is not installed.
        """
        super().__init__(config)
        self._logger = logger.bind(
            component="openai_provider",
            model=config.model,
        )
        self._client = self._create_client()

    def _create_client(self) -> Any:
        """Create the AsyncOpenAI client.

        Uses lazy import so the module can be loaded even without the
        ``openai`` package installed — the error only fires on instantiation.

        Returns:
            An AsyncOpenAI client instance.

        Raises:
            LLMProviderError: If the openai package is not installed.
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise LLMProviderError(
                message=(
                    "The 'openai' package is required for OpenAIProvider. "
                    "Install it with: pip install conductorai[openai]"
                ),
                provider="openai",
                error_code="LLM_MISSING_DEPENDENCY",
            )

        kwargs: dict[str, Any] = {}
        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        if self._config.api_base_url:
            kwargs["base_url"] = self._config.api_base_url

        return AsyncOpenAI(**kwargs)

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
        """Generate text using the OpenAI Chat Completions API.

        Sends a single user message to the model.

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
        messages = [{"role": "user", "content": prompt}]
        return await self._call_api(
            messages=messages,
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
        """Generate text with a system prompt using the Chat Completions API.

        OpenAI uses the ``system`` message role for system prompts,
        passed as the first message in the conversation.

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
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self._call_api(
            messages=messages,
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
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Make the actual OpenAI Chat Completions API call.

        Handles request building, error mapping, and response conversion.
        """
        from openai import (
            APIConnectionError,
            APIStatusError,
            AuthenticationError,
            RateLimitError,
        )

        effective_temp = temperature if temperature is not None else self.temperature
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": effective_max_tokens,
        }

        if effective_temp is not None:
            api_kwargs["temperature"] = effective_temp
        # OpenAI uses "stop" parameter, not "stop_sequences"
        if stop_sequences:
            api_kwargs["stop"] = stop_sequences

        self._logger.debug(
            "openai_api_call",
            model=self.model,
            message_count=len(messages),
            max_tokens=effective_max_tokens,
        )

        start_time = time.monotonic()

        try:
            response = await self._client.chat.completions.create(**api_kwargs)
        except AuthenticationError as e:
            raise LLMProviderError(
                message=f"OpenAI authentication failed: {e}",
                provider="openai",
                status_code=401,
                error_code="LLM_AUTH_ERROR",
            ) from e
        except RateLimitError as e:
            raise LLMProviderError(
                message=f"OpenAI rate limit exceeded: {e}",
                provider="openai",
                status_code=429,
                error_code="LLM_RATE_LIMIT",
            ) from e
        except APIConnectionError as e:
            raise LLMProviderError(
                message=f"OpenAI connection error: {e}",
                provider="openai",
                error_code="LLM_CONNECTION_ERROR",
            ) from e
        except APIStatusError as e:
            raise LLMProviderError(
                message=f"OpenAI API error: {e}",
                provider="openai",
                status_code=e.status_code,
                error_code="LLM_API_ERROR",
            ) from e

        elapsed_ms = round((time.monotonic() - start_time) * 1000)

        choice = response.choices[0]
        content = choice.message.content or ""

        finish_reason = self._map_finish_reason(choice.finish_reason)

        usage = LLMUsage(
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
        )

        self._logger.debug(
            "openai_api_response",
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
                "provider": "openai",
                "response_id": response.id,
                "latency_ms": elapsed_ms,
                "finish_reason_raw": choice.finish_reason,
                "system_fingerprint": getattr(response, "system_fingerprint", None),
            },
            created_at=datetime.now(timezone.utc),
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _map_finish_reason(finish_reason: Optional[str]) -> str:
        """Map OpenAI finish_reason to LLMResponse finish_reason.

        OpenAI uses:
            - "stop": Natural completion
            - "length": Hit max_tokens
            - "content_filter": Blocked by safety filter
            - "function_call" / "tool_calls": Function/tool use

        We map these to our standard: "stop", "length", "error", "stop".
        """
        mapping = {
            "stop": "stop",
            "length": "length",
            "content_filter": "error",
            "function_call": "stop",
            "tool_calls": "stop",
        }
        return mapping.get(finish_reason or "", "stop")

    # =========================================================================
    # Validation & Model Listing
    # =========================================================================

    async def validate(self) -> bool:
        """Validate that the OpenAI provider is configured correctly.

        Checks that an API key is available (from config or environment).

        Returns:
            True if an API key is found, False otherwise.
        """
        if not self._config.api_key and not os.environ.get("OPENAI_API_KEY"):
            self._logger.warning("openai_no_api_key")
            return False
        return True

    def get_available_models(self) -> list[str]:
        """Return commonly used OpenAI models.

        Returns:
            List of model identifier strings.
        """
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
        ]
