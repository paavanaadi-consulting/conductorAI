"""
conductor.integrations.llm.mock - Mock LLM Provider for Testing
=================================================================

This module provides a mock LLM provider that returns configurable responses
without making any real API calls. It is the default provider for testing
and development.

Why a Mock Provider?
    1. **No API key required**: Tests run without OpenAI/Anthropic credentials.
    2. **Deterministic output**: Same input always produces the same output.
    3. **Configurable responses**: Tests can inject specific responses.
    4. **Call tracking**: Records all calls for assertion in tests.
    5. **Fast**: No network latency.

How It Works:
    The mock provider maintains a response queue. When generate() is called:
    1. If there are queued responses, return the next one.
    2. Otherwise, return a default response based on the prompt content.

    For coding tasks, the default response contains a simple Python function.
    For review tasks, a review report. This makes tests readable without
    needing to manually queue responses for every call.

Usage:
    >>> from conductor.integrations.llm import MockLLMProvider
    >>> from conductor.core.config import LLMConfig
    >>>
    >>> provider = MockLLMProvider(LLMConfig(provider="mock"))
    >>>
    >>> # Queue specific response
    >>> provider.queue_response("def hello(): return 'world'")
    >>>
    >>> # Generate uses queued response first
    >>> response = await provider.generate("Write a function")
    >>> response.content  # "def hello(): return 'world'"
    >>>
    >>> # After queue is empty, uses smart defaults
    >>> response = await provider.generate("Generate code for...")
    >>> response.content  # Contains generated mock code
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from conductor.core.config import LLMConfig
from conductor.integrations.llm.base import BaseLLMProvider, LLMResponse, LLMUsage


# =============================================================================
# Logger
# =============================================================================
logger = structlog.get_logger()


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider for testing and development.

    Returns configurable mock responses without making real API calls.
    Supports response queueing, call tracking, and intelligent defaults.

    Features:
        - **Response Queue**: Queue specific responses for controlled testing.
        - **Smart Defaults**: Generates contextually appropriate mock responses.
        - **Call History**: Records every generate() call for test assertions.
        - **Token Simulation**: Estimates token usage based on text length.
        - **Error Simulation**: Can be configured to simulate API failures.

    Attributes:
        _response_queue: FIFO queue of pre-configured LLMResponse objects.
        _call_history: List of all prompts passed to generate().
        _default_response: Fallback response when queue is empty.
        _should_fail: If True, generate() raises an exception.
        _failure_message: Error message when _should_fail is True.

    Example:
        >>> provider = MockLLMProvider(LLMConfig(provider="mock"))
        >>> provider.queue_response("Hello, World!")
        >>> response = await provider.generate("Say hello")
        >>> assert response.content == "Hello, World!"
        >>> assert len(provider.call_history) == 1
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        default_response: str = "Mock LLM response",
    ) -> None:
        """Initialize the mock LLM provider.

        Args:
            config: LLM configuration. Defaults to a mock config if None.
            default_response: The fallback response text when the response
                queue is empty and no smart default applies.
        """
        if config is None:
            config = LLMConfig(provider="mock", model="mock-model")
        super().__init__(config)

        # --- Response Queue ---
        # Pre-configured responses are returned in FIFO order.
        # When the queue is empty, _generate_smart_default() is used.
        self._response_queue: deque[LLMResponse] = deque()

        # --- Call Tracking ---
        # Every call to generate() is recorded here for test assertions.
        # Each entry is a dict with "prompt", "system_prompt", and "kwargs".
        self._call_history: list[dict[str, Any]] = []

        # --- Default Behavior ---
        self._default_response = default_response

        # --- Error Simulation ---
        # Set _should_fail = True to simulate API errors in tests.
        self._should_fail: bool = False
        self._failure_message: str = "Mock LLM API error"

        # --- Logger ---
        self._logger = logger.bind(component="mock_llm_provider")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def call_history(self) -> list[dict[str, Any]]:
        """All recorded generate() calls.

        Each entry contains:
            - "prompt": The user prompt text
            - "system_prompt": System prompt (if generate_with_system was used)
            - "kwargs": Any additional keyword arguments

        Returns:
            List of call records.
        """
        return self._call_history

    @property
    def call_count(self) -> int:
        """Number of generate() calls made.

        Returns:
            Total call count.
        """
        return len(self._call_history)

    @property
    def queue_size(self) -> int:
        """Number of responses remaining in the queue.

        Returns:
            Queue length.
        """
        return len(self._response_queue)

    # =========================================================================
    # Queue Management
    # =========================================================================

    def queue_response(
        self,
        content: str,
        *,
        model: Optional[str] = None,
        finish_reason: str = "stop",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add a response to the queue.

        The next call to generate() will return this response (FIFO order).
        Multiple calls to queue_response() stack responses.

        Args:
            content: The text content of the response.
            model: Model identifier (defaults to config model).
            finish_reason: Completion reason ("stop", "length", "error").
            metadata: Optional provider-specific metadata.

        Example:
            >>> provider.queue_response("def add(a, b): return a + b")
            >>> provider.queue_response("All tests pass!")
            >>> # First generate() returns "def add(a, b): return a + b"
            >>> # Second generate() returns "All tests pass!"
        """
        response = LLMResponse(
            content=content,
            model=model or self.model,
            usage=self._estimate_usage(content),
            finish_reason=finish_reason,
            metadata=metadata or {},
        )
        self._response_queue.append(response)

    def queue_llm_response(self, response: LLMResponse) -> None:
        """Add a fully constructed LLMResponse to the queue.

        Use this when you need fine-grained control over usage stats,
        metadata, or finish_reason.

        Args:
            response: A pre-built LLMResponse object.
        """
        self._response_queue.append(response)

    def clear_queue(self) -> None:
        """Remove all queued responses."""
        self._response_queue.clear()

    def clear_history(self) -> None:
        """Clear the call history."""
        self._call_history.clear()

    # =========================================================================
    # Error Simulation
    # =========================================================================

    def set_should_fail(self, should_fail: bool, message: str = "Mock LLM API error") -> None:
        """Configure the mock to simulate API failures.

        When enabled, all generate() calls will raise a RuntimeError.
        Useful for testing error handling paths in agents.

        Args:
            should_fail: True to simulate failures, False for normal operation.
            message: The error message for the simulated failure.
        """
        self._should_fail = should_fail
        self._failure_message = message

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
        """Generate a mock response for the given prompt.

        Response selection order:
        1. If _should_fail is True → raise RuntimeError.
        2. If the response queue has entries → return the next queued response.
        3. Otherwise → generate a smart default based on prompt content.

        All calls are recorded in call_history regardless of response source.

        Args:
            prompt: The input prompt text.
            temperature: Ignored (mock doesn't use temperature).
            max_tokens: Ignored (mock returns full response).
            stop_sequences: Ignored (mock doesn't stop on sequences).
            **kwargs: Ignored additional arguments.

        Returns:
            LLMResponse with mock content.

        Raises:
            RuntimeError: If _should_fail is True (simulated API error).
        """
        # Record the call
        self._call_history.append({
            "prompt": prompt,
            "system_prompt": None,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "kwargs": kwargs,
        })

        self._logger.debug(
            "mock_generate_called",
            prompt_length=len(prompt),
            queue_size=len(self._response_queue),
        )

        # Check for simulated failure
        if self._should_fail:
            raise RuntimeError(self._failure_message)

        # Return queued response if available
        if self._response_queue:
            return self._response_queue.popleft()

        # Generate smart default based on prompt content
        return self._generate_smart_default(prompt)

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
        """Generate a mock response with system and user prompts.

        Combines both prompts for context-aware mock responses.
        The system prompt influences the smart default generation.

        Args:
            system_prompt: The system/context prompt.
            user_prompt: The user/task prompt.
            temperature: Ignored.
            max_tokens: Ignored.
            stop_sequences: Ignored.
            **kwargs: Ignored.

        Returns:
            LLMResponse with mock content.

        Raises:
            RuntimeError: If _should_fail is True.
        """
        # Record the call (with system prompt)
        self._call_history.append({
            "prompt": user_prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "kwargs": kwargs,
        })

        self._logger.debug(
            "mock_generate_with_system_called",
            system_prompt_length=len(system_prompt),
            user_prompt_length=len(user_prompt),
            queue_size=len(self._response_queue),
        )

        # Check for simulated failure
        if self._should_fail:
            raise RuntimeError(self._failure_message)

        # Return queued response if available
        if self._response_queue:
            return self._response_queue.popleft()

        # Generate smart default combining both prompts
        combined = f"{system_prompt}\n\n{user_prompt}"
        return self._generate_smart_default(combined)

    # =========================================================================
    # Validation
    # =========================================================================

    async def validate(self) -> bool:
        """Mock validation always succeeds (no real API to check).

        Returns:
            True (mock provider is always ready).
        """
        return True

    def get_available_models(self) -> list[str]:
        """Return available mock models.

        Returns:
            List of mock model identifiers.
        """
        return ["mock-model", "mock-fast", "mock-slow"]

    # =========================================================================
    # Smart Default Generation
    # =========================================================================

    def _generate_smart_default(self, prompt: str) -> LLMResponse:
        """Generate a context-appropriate mock response.

        Analyzes the prompt text to determine what kind of response to
        generate. This makes tests more readable because mock responses
        are contextually relevant without needing manual queue setup.

        Keyword-based detection:
            - "code" or "generate" → Mock Python code
            - "review" or "analyze" → Mock review report
            - "test" → Mock test results
            - Otherwise → Default response text

        Args:
            prompt: The prompt to analyze for context.

        Returns:
            LLMResponse with contextually appropriate mock content.
        """
        prompt_lower = prompt.lower()

        # Detect coding prompts
        if any(kw in prompt_lower for kw in ("code", "generate", "implement", "function", "class")):
            content = self._mock_code_response()
        # Detect review prompts
        elif any(kw in prompt_lower for kw in ("review", "analyze", "check", "quality")):
            content = self._mock_review_response()
        # Detect test prompts
        elif any(kw in prompt_lower for kw in ("test", "assert", "verify")):
            content = self._mock_test_response()
        # Default
        else:
            content = self._default_response

        return LLMResponse(
            content=content,
            model=self.model,
            usage=self._estimate_usage(content),
            finish_reason="stop",
            metadata={"source": "smart_default"},
        )

    # =========================================================================
    # Mock Response Templates
    # =========================================================================

    @staticmethod
    def _mock_code_response() -> str:
        """Generate a mock code response.

        Returns a simple but valid Python function that agents can
        parse and process.
        """
        return (
            'def process_data(data: list[dict]) -> dict:\n'
            '    """Process input data and return aggregated results.\n'
            '    \n'
            '    Args:\n'
            '        data: List of data dictionaries to process.\n'
            '    \n'
            '    Returns:\n'
            '        Aggregated result dictionary.\n'
            '    """\n'
            '    if not data:\n'
            '        return {"count": 0, "items": []}\n'
            '    \n'
            '    processed = []\n'
            '    for item in data:\n'
            '        processed.append({\n'
            '            "id": item.get("id"),\n'
            '            "status": "processed",\n'
            '        })\n'
            '    \n'
            '    return {\n'
            '        "count": len(processed),\n'
            '        "items": processed,\n'
            '    }\n'
        )

    @staticmethod
    def _mock_review_response() -> str:
        """Generate a mock code review response.

        Returns a structured review that the ReviewAgent can parse.
        """
        return (
            "## Code Review Summary\n\n"
            "**Overall Quality**: Good\n"
            "**Score**: 8/10\n\n"
            "### Findings\n\n"
            "1. **Style**: Code follows PEP 8 conventions.\n"
            "2. **Documentation**: Docstrings are present and descriptive.\n"
            "3. **Error Handling**: Consider adding input validation.\n"
            "4. **Performance**: No issues detected for current scale.\n\n"
            "### Recommendations\n\n"
            "- Add type hints to all function parameters.\n"
            "- Consider adding logging for debugging.\n"
            "- Add unit tests for edge cases.\n\n"
            "**Verdict**: APPROVED with minor suggestions.\n"
        )

    @staticmethod
    def _mock_test_response() -> str:
        """Generate a mock test results response."""
        return (
            "## Test Results\n\n"
            "- **Total**: 5 tests\n"
            "- **Passed**: 5\n"
            "- **Failed**: 0\n"
            "- **Coverage**: 85%\n\n"
            "All tests passing.\n"
        )

    # =========================================================================
    # Token Estimation
    # =========================================================================

    @staticmethod
    def _estimate_usage(text: str) -> LLMUsage:
        """Estimate token usage from text length.

        Uses a rough approximation of ~4 characters per token (English text).
        This is not exact but good enough for mock usage tracking.

        Args:
            text: The text to estimate tokens for.

        Returns:
            LLMUsage with estimated token counts.
        """
        # Rough approximation: ~4 characters per token for English text
        estimated_tokens = max(1, len(text) // 4)
        return LLMUsage(
            prompt_tokens=estimated_tokens,
            completion_tokens=estimated_tokens,
            total_tokens=estimated_tokens * 2,
        )
