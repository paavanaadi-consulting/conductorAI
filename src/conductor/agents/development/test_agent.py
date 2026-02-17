"""
conductor.agents.development.test_agent - Test Suite Generation Agent
======================================================================

This module implements the TestAgent — a specialized agent in the
DEVELOPMENT phase that creates comprehensive test suites for source code
using an LLM.

Architecture Context:
    The TestAgent is the final agent in the DEVELOPMENT phase pipeline.
    It receives code (and optionally test data from the TestDataAgent)
    and produces a complete test suite.

    ┌───────────────┐  fixtures  ┌───────────┐   test suite   ┌───────────┐
    │ TestDataAgent │ ─────────→ │ TestAgent │ ──────────────→ │  DevOps   │
    │ (generates)   │            │ (tests)   │                 │  (next)   │
    └───────────────┘            └───────────┘                 └───────────┘

    Input (task.input_data):
        {
            "code": "def add(a, b): ...",     # REQUIRED: Code to write tests for
            "language": "python",              # optional, default "python"
            "test_framework": "pytest",        # optional, default "pytest"
            "test_data": "...",                # optional: pre-generated test data
        }

    Output (result.output_data):
        {
            "tests": "...",                   # The generated test suite
            "test_framework": "pytest",
            "language": "python",
            "llm_model": "...",
            "llm_usage": {...},
        }

How Test Generation Works:
    1. TestAgent receives a TaskDefinition with "code" in input_data.
    2. It constructs a system prompt (defining the LLM's role as a test engineer).
    3. It constructs a user prompt from the code + framework + test data.
    4. It calls the LLM provider via generate_with_system().
    5. It packages the LLM response into a TaskResult with structured output.

Usage:
    >>> from conductor.agents.development import TestAgent
    >>> from conductor.core.config import ConductorConfig
    >>> from conductor.integrations.llm import MockLLMProvider
    >>>
    >>> config = ConductorConfig()
    >>> provider = MockLLMProvider()
    >>> agent = TestAgent("test-01", config, llm_provider=provider)
    >>> await agent.start()
    >>>
    >>> task = TaskDefinition(
    ...     name="Generate Tests",
    ...     assigned_to=AgentType.TEST,
    ...     input_data={"code": "def add(a, b): return a + b", "language": "python"},
    ... )
    >>> result = await agent.execute_task(task)
    >>> result.output_data["tests"]  # The generated test suite
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from conductor.agents.base import BaseAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, TaskStatus
from conductor.core.models import TaskDefinition, TaskResult
from conductor.integrations.llm.base import BaseLLMProvider


# =============================================================================
# Logger
# =============================================================================
logger = structlog.get_logger()


# =============================================================================
# System Prompt Template
# =============================================================================
# This system prompt defines the LLM's role as a test engineer.
# It's used for every generate_with_system() call. The actual task
# details come from the user prompt (built from input_data).
# =============================================================================
TEST_SYSTEM_PROMPT = """You are an expert test engineer who writes comprehensive, well-structured tests.
Your role is to create thorough test suites with clear assertions and good coverage.

Guidelines:
- Write clear, readable tests that serve as documentation for the code.
- Cover all public functions, methods, and classes in the source code.
- Include tests for normal cases, edge cases, and error cases.
- Use descriptive test names that explain what is being tested.
- Include proper setup and teardown where needed.
- Use appropriate assertions with clear failure messages.
- Follow the conventions and idioms of the specified test framework.
- Group related tests logically using test classes or describe blocks.
- Generate ONLY the test code — no explanations or markdown formatting unless requested.

If test data or fixtures are provided, incorporate them into the tests."""


class TestAgent(BaseAgent):
    """Specialized agent for creating test suites from source code.

    The TestAgent is the final agent in the DEVELOPMENT phase. It examines
    source code and generates a comprehensive test suite using the specified
    test framework. It can optionally incorporate pre-generated test data
    from the TestDataAgent.

    How It Extends BaseAgent:
        - _validate_task(): Checks that input_data contains "code"
        - _execute(): Constructs prompts, calls LLM, packages result
        - _on_start(): Validates the LLM provider is ready

    Input Requirements (task.input_data):
        Required:
            - "code" (str): The source code to write tests for.
        Optional:
            - "language" (str): Programming language (default: "python")
            - "test_framework" (str): Test framework to use (default: "pytest")
                Supported: "pytest", "unittest", "jest", "mocha", "junit", "go test"
            - "test_data" (str): Pre-generated test data/fixtures from TestDataAgent

    Output Format (result.output_data):
        - "tests" (str): The generated test suite code
        - "test_framework" (str): Framework used for the tests
        - "language" (str): Language of the test code
        - "llm_model" (str): Which LLM model was used
        - "llm_usage" (dict): Token usage stats

    Attributes:
        _llm_provider: The LLM provider used for test generation.

    Example:
        >>> agent = TestAgent("test-01", config, llm_provider=mock_provider)
        >>> await agent.start()
        >>> result = await agent.execute_task(test_task)
        >>> print(result.output_data["tests"])
    """

    def __init__(
        self,
        agent_id: str,
        config: ConductorConfig,
        *,
        llm_provider: BaseLLMProvider,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Initialize the TestAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
                Convention: "test-01", "test-02", etc.
            config: ConductorAI configuration.
            llm_provider: The LLM provider for test generation.
                Use MockLLMProvider for testing, OpenAIProvider for production.
            name: Human-readable name. Defaults to agent_id.
            description: Optional agent description.
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.TEST,
            config=config,
            name=name or f"TestAgent-{agent_id}",
            description=description or "Creates test suites for source code using LLM",
        )

        # Store the LLM provider — this is how the agent "thinks"
        self._llm_provider = llm_provider

        # Bind test-specific context to the logger
        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type="test",
            component="test_agent",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def llm_provider(self) -> BaseLLMProvider:
        """Access the LLM provider.

        Returns:
            The BaseLLMProvider instance used for test generation.
        """
        return self._llm_provider

    # =========================================================================
    # BaseAgent Abstract Method Implementations
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that the task contains code to write tests for.

        The TestAgent requires at minimum a "code" field in the task's
        input_data. This is the source code to generate tests for.

        Args:
            task: The task to validate.

        Returns:
            True if "code" is present and non-empty, False otherwise.
        """
        code = task.input_data.get("code")

        if not code:
            self._logger.warning(
                "test_task_missing_code",
                task_id=task.task_id,
                task_name=task.name,
                available_keys=list(task.input_data.keys()),
            )
            return False

        # Code must be a non-empty string
        if not isinstance(code, str) or not code.strip():
            self._logger.warning(
                "test_task_empty_code",
                task_id=task.task_id,
            )
            return False

        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Generate tests by calling the LLM with the source code.

        Execution Steps:
            1. Extract code, language, test_framework, and test_data from input_data.
            2. Build a detailed user prompt from these inputs.
            3. Call the LLM with system prompt + user prompt.
            4. Package the response into a structured TaskResult.

        Args:
            task: The validated task with code in input_data.

        Returns:
            TaskResult with generated tests in output_data.
        """
        # --- Extract inputs ---
        code = task.input_data["code"]
        language = task.input_data.get("language", "python")
        test_framework = task.input_data.get("test_framework", "pytest")
        test_data = task.input_data.get("test_data")

        self._logger.info(
            "test_execution_starting",
            task_id=task.task_id,
            language=language,
            test_framework=test_framework,
            code_length=len(code),
            has_test_data=test_data is not None,
        )

        # --- Build the user prompt ---
        user_prompt = self._build_user_prompt(
            code=code,
            language=language,
            test_framework=test_framework,
            test_data=test_data,
        )

        # --- Call the LLM ---
        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=TEST_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=self._config.llm.temperature,
            max_tokens=self._config.llm.max_tokens,
        )

        self._logger.info(
            "test_llm_response_received",
            task_id=task.task_id,
            response_length=len(llm_response.content),
            model=llm_response.model,
            tokens_used=llm_response.usage.total_tokens,
        )

        # --- Build the result ---
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "tests": llm_response.content,
                "test_framework": test_framework,
                "language": language,
                "llm_model": llm_response.model,
                "llm_usage": llm_response.usage.model_dump(),
            },
        )

    async def _on_start(self) -> None:
        """Validate the LLM provider during startup.

        Called by BaseAgent.start(). Checks that the LLM provider is
        properly configured and ready to generate.
        """
        is_valid = await self._llm_provider.validate()
        if not is_valid:
            self._logger.warning(
                "test_agent_llm_validation_failed",
                provider=self._llm_provider.provider_name,
                model=self._llm_provider.model,
            )

        self._logger.info(
            "test_agent_initialized",
            provider=self._llm_provider.provider_name,
            model=self._llm_provider.model,
        )

    # =========================================================================
    # Prompt Building
    # =========================================================================

    @staticmethod
    def _build_user_prompt(
        code: str,
        language: str,
        test_framework: str = "pytest",
        test_data: Optional[str] = None,
    ) -> str:
        """Build the user prompt from task inputs.

        Constructs a clear, structured prompt that tells the LLM exactly
        what tests to generate. The prompt includes:
        1. The source code to test
        2. The target language
        3. The test framework to use
        4. Pre-generated test data (if available)

        Args:
            code: The source code to write tests for.
            language: Target programming language.
            test_framework: Test framework to use (e.g., "pytest", "jest").
            test_data: Optional pre-generated test data/fixtures.

        Returns:
            A formatted prompt string ready for the LLM.
        """
        parts = [
            f"Generate a comprehensive {test_framework} test suite in {language} "
            f"for the following code:\n",
            f"## Source Code\n```{language}\n{code}\n```\n",
        ]

        if test_data:
            parts.append(f"## Test Data / Fixtures\n{test_data}\n")

        parts.append(
            f"## Requirements\n"
            f"- Language: {language}\n"
            f"- Test framework: {test_framework}\n"
            f"- Include tests for normal/happy path cases\n"
            f"- Include tests for edge cases and boundary values\n"
            f"- Include tests for error handling and invalid inputs\n"
            f"- Use descriptive test names\n"
            f"- Include clear assertion messages\n"
            f"- Follow {test_framework} conventions and best practices\n"
        )

        return "\n".join(parts)
