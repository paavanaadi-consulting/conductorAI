"""
conductor.agents.development.test_data_agent - Test Data Generation Agent
==========================================================================

This module implements the TestDataAgent — a specialized agent in the
DEVELOPMENT phase that generates test data, fixtures, and edge-case values
for source code using an LLM.

Architecture Context:
    The TestDataAgent sits after the ReviewAgent and before the TestAgent
    in the development pipeline. It examines code and produces realistic
    test data that the TestAgent can use to build comprehensive tests.

    ┌─────────────┐  reviewed  ┌───────────────┐  fixtures  ┌───────────┐
    │ ReviewAgent │ ─────────→ │ TestDataAgent │ ─────────→ │ TestAgent │
    │ (reviews)   │            │ (generates)   │            │ (tests)   │
    └─────────────┘            └───────────────┘            └───────────┘

    Input (task.input_data):
        {
            "code": "def add(a, b): ...",     # REQUIRED: Code to generate test data for
            "language": "python",              # optional, default "python"
            "data_format": "fixtures",         # optional, default "fixtures"
        }

    Output (result.output_data):
        {
            "test_data": "...",               # The generated test data / fixtures
            "format": "fixtures",
            "language": "python",
            "llm_model": "...",
            "llm_usage": {...},
        }

How Test Data Generation Works:
    1. TestDataAgent receives a TaskDefinition with "code" in input_data.
    2. It constructs a system prompt (defining the LLM's role as a test data engineer).
    3. It constructs a user prompt from the code + language + format.
    4. It calls the LLM provider via generate_with_system().
    5. It packages the LLM response into a TaskResult with structured output.

Usage:
    >>> from conductor.agents.development import TestDataAgent
    >>> from conductor.core.config import ConductorConfig
    >>> from conductor.integrations.llm import MockLLMProvider
    >>>
    >>> config = ConductorConfig()
    >>> provider = MockLLMProvider()
    >>> agent = TestDataAgent("test-data-01", config, llm_provider=provider)
    >>> await agent.start()
    >>>
    >>> task = TaskDefinition(
    ...     name="Generate Test Data",
    ...     assigned_to=AgentType.TEST_DATA,
    ...     input_data={"code": "def add(a, b): return a + b", "language": "python"},
    ... )
    >>> result = await agent.execute_task(task)
    >>> result.output_data["test_data"]  # The generated test data
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
# This system prompt defines the LLM's role as a test data engineer.
# It's used for every generate_with_system() call. The actual task
# details come from the user prompt (built from input_data).
# =============================================================================
TEST_DATA_SYSTEM_PROMPT = """You are an expert test data engineer specializing in generating high-quality test data.
Your role is to produce realistic test fixtures, edge cases, and boundary values for the given code.

Guidelines:
- Generate comprehensive test data covering normal, edge, and boundary cases.
- Include both valid and invalid inputs to test error handling paths.
- Provide realistic, representative data that exercises all code branches.
- Use appropriate data types and formats for the target language.
- Include null/None/empty values where applicable.
- Generate data that covers numeric boundaries (zero, negative, overflow).
- Include string edge cases (empty, whitespace, unicode, very long).
- Generate ONLY the test data — no explanations or markdown formatting unless requested.

If a specific data format (fixtures, factories, CSV, JSON) is specified, use that format."""


class TestDataAgent(BaseAgent):
    """Specialized agent for generating test data and fixtures.

    The TestDataAgent examines source code and generates comprehensive test
    data including fixtures, edge cases, and boundary values. It uses an LLM
    to analyze code paths and produce data that exercises all branches.

    How It Extends BaseAgent:
        - _validate_task(): Checks that input_data contains "code"
        - _execute(): Constructs prompts, calls LLM, packages result
        - _on_start(): Validates the LLM provider is ready

    Input Requirements (task.input_data):
        Required:
            - "code" (str): The source code to generate test data for.
        Optional:
            - "language" (str): Programming language (default: "python")
            - "data_format" (str): Output format for test data (default: "fixtures")
                Supported: "fixtures", "factories", "json", "csv", "parametrize"

    Output Format (result.output_data):
        - "test_data" (str): The generated test data / fixtures
        - "format" (str): The data format used
        - "language" (str): Language of the test data
        - "llm_model" (str): Which LLM model was used
        - "llm_usage" (dict): Token usage stats

    Attributes:
        _llm_provider: The LLM provider used for test data generation.

    Example:
        >>> agent = TestDataAgent("test-data-01", config, llm_provider=mock_provider)
        >>> await agent.start()
        >>> result = await agent.execute_task(test_data_task)
        >>> print(result.output_data["test_data"])
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
        """Initialize the TestDataAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
                Convention: "test-data-01", "test-data-02", etc.
            config: ConductorAI configuration.
            llm_provider: The LLM provider for test data generation.
                Use MockLLMProvider for testing, OpenAIProvider for production.
            name: Human-readable name. Defaults to agent_id.
            description: Optional agent description.
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.TEST_DATA,
            config=config,
            name=name or f"TestDataAgent-{agent_id}",
            description=description or "Generates test data and fixtures for source code using LLM",
        )

        # Store the LLM provider — this is how the agent "thinks"
        self._llm_provider = llm_provider

        # Bind test-data-specific context to the logger
        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type="test_data",
            component="test_data_agent",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def llm_provider(self) -> BaseLLMProvider:
        """Access the LLM provider.

        Returns:
            The BaseLLMProvider instance used for test data generation.
        """
        return self._llm_provider

    # =========================================================================
    # BaseAgent Abstract Method Implementations
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that the task contains code to generate test data for.

        The TestDataAgent requires at minimum a "code" field in the task's
        input_data. This is the source code to analyze for test data generation.

        Args:
            task: The task to validate.

        Returns:
            True if "code" is present and non-empty, False otherwise.
        """
        code = task.input_data.get("code")

        if not code:
            self._logger.warning(
                "test_data_task_missing_code",
                task_id=task.task_id,
                task_name=task.name,
                available_keys=list(task.input_data.keys()),
            )
            return False

        # Code must be a non-empty string
        if not isinstance(code, str) or not code.strip():
            self._logger.warning(
                "test_data_task_empty_code",
                task_id=task.task_id,
            )
            return False

        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Generate test data by calling the LLM with the source code.

        Execution Steps:
            1. Extract code, language, and data_format from input_data.
            2. Build a detailed user prompt from these inputs.
            3. Call the LLM with system prompt + user prompt.
            4. Package the response into a structured TaskResult.

        Args:
            task: The validated task with code in input_data.

        Returns:
            TaskResult with generated test data in output_data.
        """
        # --- Extract inputs ---
        code = task.input_data["code"]
        language = task.input_data.get("language", "python")
        data_format = task.input_data.get("data_format", "fixtures")

        self._logger.info(
            "test_data_execution_starting",
            task_id=task.task_id,
            language=language,
            data_format=data_format,
            code_length=len(code),
        )

        # --- Build the user prompt ---
        user_prompt = self._build_user_prompt(
            code=code,
            language=language,
            data_format=data_format,
        )

        # --- Call the LLM ---
        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=TEST_DATA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=self._config.llm.temperature,
            max_tokens=self._config.llm.max_tokens,
        )

        self._logger.info(
            "test_data_llm_response_received",
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
                "test_data": llm_response.content,
                "format": data_format,
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
                "test_data_agent_llm_validation_failed",
                provider=self._llm_provider.provider_name,
                model=self._llm_provider.model,
            )

        self._logger.info(
            "test_data_agent_initialized",
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
        data_format: str = "fixtures",
    ) -> str:
        """Build the user prompt from task inputs.

        Constructs a clear, structured prompt that tells the LLM exactly
        what test data to generate. The prompt includes:
        1. The source code to analyze
        2. The target language
        3. The desired data format

        Args:
            code: The source code to generate test data for.
            language: Target programming language.
            data_format: Desired output format (fixtures, factories, json, etc.).

        Returns:
            A formatted prompt string ready for the LLM.
        """
        parts = [
            f"Generate {language} test data in {data_format} format for the following code:\n",
            f"## Source Code\n```{language}\n{code}\n```\n",
            f"## Data Format\n{data_format}\n",
            f"## Requirements\n"
            f"- Language: {language}\n"
            f"- Format: {data_format}\n"
            f"- Include normal case data (typical valid inputs)\n"
            f"- Include edge case data (boundary values, empty inputs)\n"
            f"- Include error case data (invalid inputs for error path testing)\n"
            f"- Cover all function parameters and code branches\n"
            f"- Use realistic, representative values\n",
        ]

        return "\n".join(parts)
