"""
conductor.agents.development.coding_agent - Code Generation Agent
===================================================================

This module implements the CodingAgent — the first specialized agent in
ConductorAI. It generates source code from specifications using an LLM.

Architecture Context:
    The CodingAgent is the entry point of the DEVELOPMENT phase. It receives
    a specification (what to build) and produces code (the implementation).

    ┌───────────────────┐    TaskDefinition     ┌─────────────────┐
    │ AgentCoordinator  │ ──────────────────→   │   CodingAgent    │
    │                   │                       │                   │
    │                   │ ←── TaskResult ────── │  ┌────────────┐  │
    └───────────────────┘                       │  │ LLMProvider│  │
                                                │  └────────────┘  │
                                                └─────────────────┘

    Input (task.input_data):
        {
            "specification": "Create a REST API for user management",
            "language": "python",               # optional, default "python"
            "framework": "fastapi",             # optional
            "additional_context": "Use SQLAlchemy ORM"  # optional
        }

    Output (result.output_data):
        {
            "code": "...",                      # The generated source code
            "language": "python",
            "description": "...",               # Brief description of what was generated
            "files": ["main.py"],               # List of generated file names
        }

How Code Generation Works:
    1. CodingAgent receives a TaskDefinition with a "specification" in input_data.
    2. It constructs a system prompt (defining the LLM's role as a developer).
    3. It constructs a user prompt from the specification + context.
    4. It calls the LLM provider via generate_with_system().
    5. It packages the LLM response into a TaskResult with structured output.

Usage:
    >>> from conductor.agents.development import CodingAgent
    >>> from conductor.core.config import ConductorConfig
    >>> from conductor.integrations.llm import MockLLMProvider
    >>>
    >>> config = ConductorConfig()
    >>> provider = MockLLMProvider()
    >>> agent = CodingAgent("coding-01", config, llm_provider=provider)
    >>> await agent.start()
    >>>
    >>> task = TaskDefinition(
    ...     name="Generate API",
    ...     assigned_to=AgentType.CODING,
    ...     input_data={"specification": "REST API for users", "language": "python"},
    ... )
    >>> result = await agent.execute_task(task)
    >>> result.output_data["code"]  # The generated code
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
# This system prompt defines the LLM's role as a code generator.
# It's used for every generate_with_system() call. The actual task
# details come from the user prompt (built from input_data).
# =============================================================================
CODING_SYSTEM_PROMPT = """You are an expert software developer working on a professional project.
Your role is to generate clean, well-documented, production-quality source code.

Guidelines:
- Write clear, readable code following best practices for the specified language.
- Include comprehensive docstrings and inline comments.
- Use type hints where the language supports them.
- Handle errors gracefully with proper exception handling.
- Follow SOLID principles and clean architecture patterns.
- Generate ONLY the code — no explanations or markdown formatting unless requested.

If a framework is specified, use its idioms and conventions."""


class CodingAgent(BaseAgent):
    """Specialized agent for generating source code from specifications.

    The CodingAgent is the primary code producer in ConductorAI. It takes
    a specification (what to build), sends it to an LLM with appropriate
    context (system prompt + language/framework hints), and returns the
    generated code as a structured TaskResult.

    How It Extends BaseAgent:
        - _validate_task(): Checks that input_data contains "specification"
        - _execute(): Constructs prompts, calls LLM, packages result
        - _on_start(): Validates the LLM provider is ready

    Input Requirements (task.input_data):
        Required:
            - "specification" (str): What to build. This is the core prompt.
        Optional:
            - "language" (str): Target programming language (default: "python")
            - "framework" (str): Framework to use (e.g., "fastapi", "django")
            - "additional_context" (str): Extra instructions or constraints
            - "file_name" (str): Suggested output file name

    Output Format (result.output_data):
        - "code" (str): The generated source code
        - "language" (str): Language of the generated code
        - "description" (str): Brief description of what was generated
        - "files" (list[str]): Generated file names
        - "llm_model" (str): Which LLM model was used
        - "llm_usage" (dict): Token usage stats

    Attributes:
        _llm_provider: The LLM provider used for code generation.

    Example:
        >>> agent = CodingAgent("coding-01", config, llm_provider=mock_provider)
        >>> await agent.start()
        >>> result = await agent.execute_task(coding_task)
        >>> print(result.output_data["code"])
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
        """Initialize the CodingAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
                Convention: "coding-01", "coding-02", etc.
            config: ConductorAI configuration.
            llm_provider: The LLM provider for code generation.
                Use MockLLMProvider for testing, OpenAIProvider for production.
            name: Human-readable name. Defaults to agent_id.
            description: Optional agent description.
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.CODING,
            config=config,
            name=name or f"CodingAgent-{agent_id}",
            description=description or "Generates source code from specifications using LLM",
        )

        # Store the LLM provider — this is how the agent "thinks"
        self._llm_provider = llm_provider

        # Bind coding-specific context to the logger
        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type="coding",
            component="coding_agent",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def llm_provider(self) -> BaseLLMProvider:
        """Access the LLM provider.

        Returns:
            The BaseLLMProvider instance used for code generation.
        """
        return self._llm_provider

    # =========================================================================
    # BaseAgent Abstract Method Implementations
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that the task contains a code specification.

        The CodingAgent requires at minimum a "specification" field in the
        task's input_data. This tells the agent WHAT to generate.

        Args:
            task: The task to validate.

        Returns:
            True if "specification" is present and non-empty, False otherwise.
        """
        specification = task.input_data.get("specification")

        if not specification:
            self._logger.warning(
                "coding_task_missing_specification",
                task_id=task.task_id,
                task_name=task.name,
                available_keys=list(task.input_data.keys()),
            )
            return False

        # Specification must be a non-empty string
        if not isinstance(specification, str) or not specification.strip():
            self._logger.warning(
                "coding_task_empty_specification",
                task_id=task.task_id,
            )
            return False

        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Generate code by calling the LLM with the specification.

        Execution Steps:
            1. Extract specification, language, and framework from input_data.
            2. Build a detailed user prompt from these inputs.
            3. Call the LLM with system prompt + user prompt.
            4. Package the response into a structured TaskResult.

        Args:
            task: The validated task with specification in input_data.

        Returns:
            TaskResult with generated code in output_data.
        """
        # --- Extract inputs ---
        specification = task.input_data["specification"]
        language = task.input_data.get("language", "python")
        framework = task.input_data.get("framework")
        additional_context = task.input_data.get("additional_context", "")
        file_name = task.input_data.get("file_name", f"generated.{self._get_extension(language)}")

        self._logger.info(
            "coding_execution_starting",
            task_id=task.task_id,
            language=language,
            framework=framework,
            spec_length=len(specification),
        )

        # --- Build the user prompt ---
        user_prompt = self._build_user_prompt(
            specification=specification,
            language=language,
            framework=framework,
            additional_context=additional_context,
        )

        # --- Call the LLM ---
        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=CODING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=self._config.llm.temperature,
            max_tokens=self._config.llm.max_tokens,
        )

        self._logger.info(
            "coding_llm_response_received",
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
                "code": llm_response.content,
                "language": language,
                "framework": framework,
                "description": f"Generated {language} code for: {task.name}",
                "files": [file_name],
                "llm_model": llm_response.model,
                "llm_usage": llm_response.usage.model_dump(),
                "specification": specification,
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
                "coding_agent_llm_validation_failed",
                provider=self._llm_provider.provider_name,
                model=self._llm_provider.model,
            )

        self._logger.info(
            "coding_agent_initialized",
            provider=self._llm_provider.provider_name,
            model=self._llm_provider.model,
        )

    # =========================================================================
    # Prompt Building
    # =========================================================================

    @staticmethod
    def _build_user_prompt(
        specification: str,
        language: str,
        framework: Optional[str] = None,
        additional_context: str = "",
    ) -> str:
        """Build the user prompt from task inputs.

        Constructs a clear, structured prompt that tells the LLM exactly
        what to generate. The prompt includes:
        1. The specification (what to build)
        2. The target language
        3. Framework requirements (if specified)
        4. Additional context/constraints

        Args:
            specification: What to build (the core requirement).
            language: Target programming language.
            framework: Optional framework to use.
            additional_context: Extra instructions or constraints.

        Returns:
            A formatted prompt string ready for the LLM.
        """
        parts = [
            f"Generate {language} code for the following specification:\n",
            f"## Specification\n{specification}\n",
        ]

        if framework:
            parts.append(f"## Framework\nUse the {framework} framework.\n")

        if additional_context:
            parts.append(f"## Additional Context\n{additional_context}\n")

        parts.append(
            f"## Requirements\n"
            f"- Language: {language}\n"
            f"- Include proper error handling\n"
            f"- Include docstrings and type hints\n"
            f"- Follow {language} best practices\n"
        )

        return "\n".join(parts)

    # =========================================================================
    # Utility
    # =========================================================================

    @staticmethod
    def _get_extension(language: str) -> str:
        """Map a language name to its file extension.

        Args:
            language: Programming language name (case-insensitive).

        Returns:
            File extension string (without dot).
        """
        extensions = {
            "python": "py",
            "javascript": "js",
            "typescript": "ts",
            "java": "java",
            "go": "go",
            "rust": "rs",
            "ruby": "rb",
            "c": "c",
            "cpp": "cpp",
            "c++": "cpp",
            "csharp": "cs",
            "c#": "cs",
            "swift": "swift",
            "kotlin": "kt",
            "php": "php",
        }
        return extensions.get(language.lower(), "txt")
