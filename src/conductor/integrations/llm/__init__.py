"""
conductor.integrations.llm - Large Language Model Providers
=============================================================

This package provides the LLM abstraction layer. Agents call LLMs through
the LLMProvider interface, allowing the backend to be swapped without
changing agent code.

Available Providers:
    - BaseLLMProvider:   Abstract base class defining the LLM contract.
    - MockLLMProvider:   Returns configurable mock responses (for testing).
    - OpenAIProvider:    Calls OpenAI API (GPT-4o, GPT-4, GPT-3.5-turbo, etc.)
    - AnthropicProvider: Calls Anthropic API (Claude models)

Usage:
    >>> from conductor.integrations.llm import create_llm_provider
    >>> provider = create_llm_provider(config.llm)
    >>> response = await provider.generate("Write a Python function...")
"""

from conductor.integrations.llm.base import BaseLLMProvider, LLMResponse, LLMUsage
from conductor.integrations.llm.mock import MockLLMProvider
from conductor.integrations.llm.factory import create_llm_provider


# Lazy imports for optional providers (PEP 562).
# Avoids ImportError when the anthropic/openai SDKs are not installed.
# The error only fires when the provider class is actually accessed.
def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "OpenAIProvider":
        from conductor.integrations.llm.openai_provider import OpenAIProvider
        return OpenAIProvider
    if name == "AnthropicProvider":
        from conductor.integrations.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "LLMUsage",
    "MockLLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "create_llm_provider",
]
