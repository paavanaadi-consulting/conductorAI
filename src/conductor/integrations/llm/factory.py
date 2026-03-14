"""
conductor.integrations.llm.factory - LLM Provider Factory
============================================================

This module provides a factory function to create the correct LLM provider
based on configuration. It maps provider names to concrete implementations.

Usage:
    >>> from conductor.integrations.llm import create_llm_provider
    >>> from conductor.core.config import LLMConfig
    >>>
    >>> config = LLMConfig(provider="anthropic", api_key="sk-ant-...")
    >>> provider = create_llm_provider(config)
    >>> type(provider)  # AnthropicProvider
"""

from __future__ import annotations

from conductor.core.config import LLMConfig
from conductor.integrations.llm.base import BaseLLMProvider


def create_llm_provider(config: LLMConfig) -> BaseLLMProvider:
    """Create an LLM provider instance based on configuration.

    This factory function maps the config.provider string to a concrete
    BaseLLMProvider implementation:
        - "mock"      → MockLLMProvider (for testing, no API key needed)
        - "openai"    → OpenAIProvider (GPT-4o, GPT-4, GPT-3.5-turbo, etc.)
        - "anthropic" → AnthropicProvider (Claude models)

    All imports are lazy — the openai/anthropic packages are only imported
    when the corresponding provider is requested. This means users who only
    use ``"mock"`` never need those packages installed.

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

    elif provider_name == "openai":
        from conductor.integrations.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(config)

    elif provider_name == "anthropic":
        from conductor.integrations.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(config)

    raise ValueError(
        f"Unknown LLM provider: '{provider_name}'. "
        f"Available providers: 'mock', 'openai', 'anthropic'."
    )
