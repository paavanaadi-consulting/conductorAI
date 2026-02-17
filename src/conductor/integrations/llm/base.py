"""
conductor.integrations.llm.base - Abstract LLM Provider Interface
==================================================================

This module defines the contract that ALL LLM providers must implement.
It's the bridge between ConductorAI agents and external LLM services.

Architecture Context:
    Agents don't call OpenAI or Anthropic directly. Instead, they call
    the LLM through this abstract interface. This gives us:

    1. **Swappability**: Switch from OpenAI to Anthropic with one config change.
    2. **Testability**: Use MockLLMProvider in tests without API keys.
    3. **Consistency**: All providers return the same LLMResponse type.
    4. **Observability**: Centralized logging, metrics, and cost tracking.

    ┌───────────────┐      generate()      ┌──────────────────┐
    │   Agent       │ ────────────────────→ │  BaseLLMProvider  │
    │ (CodingAgent) │                       │  (abstract)       │
    │               │ ←── LLMResponse ───── │                   │
    └───────────────┘                       └──────────┬────────┘
                                                       │
                                            ┌──────────┴────────┐
                                            │                   │
                                       ┌────▼───┐    ┌─────────▼────┐
                                       │  Mock  │    │  OpenAI /    │
                                       │Provider│    │  Anthropic   │
                                       └────────┘    └──────────────┘

LLMResponse:
    Every provider returns an LLMResponse containing:
    - content: The generated text (the actual LLM output)
    - model: Which model produced the response
    - usage: Token counts (prompt, completion, total) for cost tracking
    - finish_reason: Why generation stopped ("stop", "length", "error")
    - metadata: Provider-specific extras (latency, request_id, etc.)

Usage:
    >>> class MyProvider(BaseLLMProvider):
    ...     async def generate(self, prompt, **kwargs):
    ...         text = await my_api_call(prompt)
    ...         return LLMResponse(content=text, model=self.model)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from conductor.core.config import LLMConfig


# =============================================================================
# LLM Response Model
# =============================================================================
# Every LLM provider returns this standardized response, regardless of the
# underlying API. This ensures agents can switch providers without code changes.
# =============================================================================
class LLMUsage(BaseModel):
    """Token usage tracking for an LLM call.

    Tracks how many tokens were consumed by a single LLM generation call.
    This is critical for:
        - Cost tracking (most LLM APIs charge per token)
        - Rate limit awareness
        - Performance monitoring

    Attributes:
        prompt_tokens: Number of tokens in the input prompt.
        completion_tokens: Number of tokens in the generated output.
        total_tokens: Sum of prompt + completion tokens.
    """

    prompt_tokens: int = Field(default=0, ge=0, description="Tokens in the input prompt")
    completion_tokens: int = Field(default=0, ge=0, description="Tokens in the output")
    total_tokens: int = Field(default=0, ge=0, description="Total tokens consumed")


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider.

    This is the universal return type for all LLM calls in ConductorAI.
    Regardless of whether the backend is OpenAI, Anthropic, or a mock,
    agents always receive this same structure.

    Attributes:
        content: The generated text content. This is the main output.
        model: The model identifier that produced this response.
        usage: Token counts for cost tracking and monitoring.
        finish_reason: Why generation stopped:
            - "stop": Natural completion (hit stop sequence)
            - "length": Hit max_tokens limit
            - "error": Generation failed
        metadata: Provider-specific extras (request_id, latency, etc.)
        created_at: When this response was generated (UTC).

    Example:
        >>> response = LLMResponse(
        ...     content="def hello():\\n    return 'Hello, World!'",
        ...     model="gpt-4",
        ...     usage=LLMUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70),
        ...     finish_reason="stop",
        ... )
    """

    content: str = Field(description="The generated text content from the LLM")
    model: str = Field(description="Model identifier that produced this response")
    usage: LLMUsage = Field(
        default_factory=LLMUsage,
        description="Token usage for cost tracking",
    )
    finish_reason: str = Field(
        default="stop",
        description="Why generation stopped: 'stop', 'length', or 'error'",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata (request_id, latency, etc.)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Response creation timestamp (UTC)",
    )


# =============================================================================
# Abstract Base LLM Provider
# =============================================================================
class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers.

    Every LLM integration must implement this interface. The base class
    handles common concerns (config, logging) while subclasses implement
    the actual API calls.

    What the base class provides:
        - Configuration storage (model, temperature, max_tokens)
        - Common property accessors
        - Abstract method contracts

    What subclasses must implement:
        - generate(): Make the actual LLM API call
        - generate_with_system(): LLM call with system prompt

    What subclasses can optionally implement:
        - validate(): Check if the provider is properly configured
        - get_available_models(): List supported models

    Attributes:
        _config: The LLM configuration (provider, model, api_key, etc.)

    Example:
        >>> class OpenAIProvider(BaseLLMProvider):
        ...     async def generate(self, prompt, **kwargs):
        ...         response = await openai.ChatCompletion.acreate(
        ...             model=self.model,
        ...             messages=[{"role": "user", "content": prompt}],
        ...         )
        ...         return LLMResponse(content=response.choices[0].message.content, ...)
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialize the LLM provider with configuration.

        Args:
            config: LLM configuration containing provider name, model,
                API key, temperature, max_tokens, and optional base URL.
        """
        self._config = config

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def provider_name(self) -> str:
        """The name of this LLM provider (e.g., 'openai', 'anthropic', 'mock').

        Returns:
            The provider identifier string.
        """
        return self._config.provider

    @property
    def model(self) -> str:
        """The specific model identifier (e.g., 'gpt-4', 'claude-3-opus').

        Returns:
            The model identifier string.
        """
        return self._config.model

    @property
    def temperature(self) -> float:
        """The temperature setting for generation randomness.

        Returns:
            Float between 0.0 (deterministic) and 2.0 (maximum randomness).
        """
        return self._config.temperature

    @property
    def max_tokens(self) -> int:
        """The maximum number of tokens the LLM can generate per call.

        Returns:
            Maximum token count.
        """
        return self._config.max_tokens

    @property
    def config(self) -> LLMConfig:
        """Access the full LLM configuration.

        Returns:
            The LLMConfig instance.
        """
        return self._config

    # =========================================================================
    # Abstract Methods (Subclasses MUST implement)
    # =========================================================================

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text from a prompt using the LLM.

        This is the primary generation method. Agents call this to get
        LLM outputs for code generation, reviews, test creation, etc.

        Args:
            prompt: The input text prompt for the LLM.
            temperature: Override the default temperature for this call.
                None means use the config default.
            max_tokens: Override the default max_tokens for this call.
                None means use the config default.
            stop_sequences: Optional list of strings that stop generation
                when encountered.
            **kwargs: Provider-specific keyword arguments.

        Returns:
            LLMResponse with generated content, usage stats, and metadata.

        Raises:
            Exception: If the LLM API call fails (provider-specific).
        """
        ...

    @abstractmethod
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
        """Generate text with a system prompt and user prompt.

        This is used when agents need to set up context (system prompt)
        before the actual task (user prompt). For example:

            system: "You are a senior Python developer who writes clean code."
            user: "Generate a REST API endpoint for user creation."

        Args:
            system_prompt: Instructions/context for the LLM (role, rules).
            user_prompt: The actual task prompt.
            temperature: Override default temperature. None = config default.
            max_tokens: Override default max_tokens. None = config default.
            stop_sequences: Strings that stop generation when encountered.
            **kwargs: Provider-specific keyword arguments.

        Returns:
            LLMResponse with generated content, usage stats, and metadata.
        """
        ...

    # =========================================================================
    # Optional Methods (Subclasses CAN override)
    # =========================================================================

    async def validate(self) -> bool:
        """Validate that the provider is properly configured.

        Checks that the API key is set, the model is valid, and the
        service is reachable. Override this in concrete providers.

        Returns:
            True if the provider is ready, False otherwise.
        """
        return True

    def get_available_models(self) -> list[str]:
        """List the models supported by this provider.

        Override this in concrete providers to return actual model lists.

        Returns:
            List of model identifier strings.
        """
        return [self.model]

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"provider={self.provider_name!r}, "
            f"model={self.model!r})"
        )
