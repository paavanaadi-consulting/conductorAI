"""
conductor.integrations.llm.factory - LLM Provider Factory
============================================================

This module provides a factory function to create the correct LLM provider
based on configuration. It maps provider names to concrete implementations.

Usage:
    >>> from conductor.integrations.llm import create_llm_provider
    >>> from conductor.core.config import LLMConfig
    >>>
    >>> config = LLMConfig(provider="mock")
    >>> provider = create_llm_provider(config)
    >>> type(provider)  # MockLLMProvider
"""

from __future__ import annotations

from conductor.core.config import LLMConfig
from conductor.integrations.llm.base import BaseLLMProvider


def create_llm_provider(config: LLMConfig) -> BaseLLMProvider:
    """Create an LLM provider instance based on configuration.

    This factory function maps the config.provider string to a concrete
    BaseLLMProvider implementation:
        - "mock" → MockLLMProvider (for testing, no API key needed)
        - "openai" → (Future: OpenAIProvider)
        - "anthropic" → (Future: AnthropicProvider)

    Args:
        config: LLM configuration with provider name, model, API key, etc.

    Returns:
        A concrete BaseLLMProvider instance ready for generate() calls.

    Raises:
        ValueError: If the provider name is not recognized.

    Example:
        >>> provider = create_llm_provider(LLMConfig(provider="mock"))
        >>> response = await provider.generate("Hello")
    """
    provider_name = config.provider.lower()

    if provider_name == "mock":
        from conductor.integrations.llm.mock import MockLLMProvider
        return MockLLMProvider(config)

    # Future providers (Day 9):
    # elif provider_name == "openai":
    #     from conductor.integrations.llm.openai import OpenAIProvider
    #     return OpenAIProvider(config)
    # elif provider_name == "anthropic":
    #     from conductor.integrations.llm.anthropic import AnthropicProvider
    #     return AnthropicProvider(config)

    raise ValueError(
        f"Unknown LLM provider: '{provider_name}'. "
        f"Available providers: 'mock'. "
        f"OpenAI and Anthropic providers coming in Day 9."
    )
