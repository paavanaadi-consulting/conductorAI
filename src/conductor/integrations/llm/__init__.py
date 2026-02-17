"""
conductor.integrations.llm - Large Language Model Providers
=============================================================

This package provides the LLM abstraction layer. Agents call LLMs through
the LLMProvider interface, allowing the backend to be swapped without
changing agent code.

Available Providers:
    - BaseLLMProvider: Abstract base class defining the LLM contract.
    - MockLLMProvider: Returns configurable mock responses (for testing).

Future Providers (Day 9):
    - OpenAIProvider:    Calls OpenAI API (GPT-4, GPT-3.5-turbo, etc.)
    - AnthropicProvider: Calls Anthropic API (Claude models)

Usage:
    >>> from conductor.integrations.llm import MockLLMProvider, create_llm_provider
    >>> provider = create_llm_provider(config.llm)
    >>> response = await provider.generate("Write a Python function...")
"""

from conductor.integrations.llm.base import BaseLLMProvider, LLMResponse
from conductor.integrations.llm.mock import MockLLMProvider
from conductor.integrations.llm.factory import create_llm_provider

__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "MockLLMProvider",
    "create_llm_provider",
]
