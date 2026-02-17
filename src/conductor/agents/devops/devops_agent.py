"""
conductor.agents.devops.devops_agent - DevOps Configuration Agent
==================================================================

This module implements the DevOpsAgent — the first specialized agent in
ConductorAI's DEVOPS phase. It generates CI/CD configurations, Dockerfiles,
and infrastructure configs from code or project descriptions using an LLM.

Architecture Context:
    The DevOpsAgent is the entry point of the DEVOPS phase. It receives
    code or a project description (what was built) and produces CI/CD
    pipeline configurations (how to build, test, and deploy it).

    ┌───────────────────┐    TaskDefinition     ┌─────────────────┐
    │ AgentCoordinator  │ ──────────────────→   │   DevOpsAgent    │
    │                   │                       │                   │
    │                   │ ←── TaskResult ────── │  ┌────────────┐  │
    └───────────────────┘                       │  │ LLMProvider│  │
                                                │  └────────────┘  │
                                                └─────────────────┘

    Input (task.input_data):
        {
            "code": "...",                         # or "project_description"
            "platform": "github_actions",          # optional, default "github_actions"
            "language": "python",                  # optional, default "python"
            "additional_requirements": "..."       # optional
        }

    Output (result.output_data):
        {
            "config": "...",                       # The generated CI/CD configuration
            "platform": "github_actions",
            "language": "python",
            "files": [".github/workflows/ci.yml"], # List of generated file names
            "llm_model": "...",
            "llm_usage": {...},
        }

How Configuration Generation Works:
    1. DevOpsAgent receives a TaskDefinition with "code" or "project_description".
    2. It constructs a system prompt (defining the LLM's role as a DevOps engineer).
    3. It constructs a user prompt from the code/description + platform/language.
    4. It calls the LLM provider via generate_with_system().
    5. It packages the LLM response into a TaskResult with structured output.

Usage:
    >>> from conductor.agents.devops import DevOpsAgent
    >>> from conductor.core.config import ConductorConfig
    >>> from conductor.integrations.llm import MockLLMProvider
    >>>
    >>> config = ConductorConfig()
    >>> provider = MockLLMProvider()
    >>> agent = DevOpsAgent("devops-01", config, llm_provider=provider)
    >>> await agent.start()
    >>>
    >>> task = TaskDefinition(
    ...     name="Generate CI/CD",
    ...     assigned_to=AgentType.DEVOPS,
    ...     input_data={"code": "def main(): ...", "platform": "github_actions"},
    ... )
    >>> result = await agent.execute_task(task)
    >>> result.output_data["config"]  # The generated configuration
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
# This system prompt defines the LLM's role as a DevOps configuration generator.
# It's used for every generate_with_system() call. The actual task
# details come from the user prompt (built from input_data).
# =============================================================================
DEVOPS_SYSTEM_PROMPT = """You are an expert DevOps engineer working on a professional project.
Your role is to create production-ready CI/CD configurations, Dockerfiles, and infrastructure configs.

Guidelines:
- Write clean, well-commented configuration files following best practices for the specified platform.
- Include comprehensive comments explaining each section and decision.
- Use secure defaults and follow security best practices.
- Handle caching, artifacts, and build optimization where appropriate.
- Follow the principle of least privilege for permissions and access.
- Generate ONLY the configuration — no explanations or markdown formatting unless requested.

If a specific platform is specified, use its idioms and conventions."""


# =============================================================================
# Platform-to-Filename Mapping
# =============================================================================
PLATFORM_FILENAMES = {
    "github_actions": ".github/workflows/ci.yml",
    "docker": "Dockerfile",
    "gitlab_ci": ".gitlab-ci.yml",
    "jenkins": "Jenkinsfile",
}


class DevOpsAgent(BaseAgent):
    """Specialized agent for generating CI/CD and infrastructure configurations.

    The DevOpsAgent is the primary configuration producer in ConductorAI's
    DEVOPS phase. It takes code or a project description, sends it to an LLM
    with appropriate context (system prompt + platform/language hints), and
    returns the generated configuration as a structured TaskResult.

    How It Extends BaseAgent:
        - _validate_task(): Checks that input_data contains "code" or "project_description"
        - _execute(): Constructs prompts, calls LLM, packages result
        - _on_start(): Validates the LLM provider is ready

    Input Requirements (task.input_data):
        Required (at least one):
            - "code" (str): Source code to create CI/CD configs for.
            - "project_description" (str): Description of the project.
        Optional:
            - "platform" (str): Target CI/CD platform (default: "github_actions")
            - "language" (str): Project programming language (default: "python")
            - "additional_requirements" (str): Extra instructions or constraints

    Output Format (result.output_data):
        - "config" (str): The generated configuration content
        - "platform" (str): Target platform used
        - "language" (str): Project language
        - "files" (list[str]): Generated file names
        - "llm_model" (str): Which LLM model was used
        - "llm_usage" (dict): Token usage stats

    Attributes:
        _llm_provider: The LLM provider used for configuration generation.

    Example:
        >>> agent = DevOpsAgent("devops-01", config, llm_provider=mock_provider)
        >>> await agent.start()
        >>> result = await agent.execute_task(devops_task)
        >>> print(result.output_data["config"])
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
        """Initialize the DevOpsAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
                Convention: "devops-01", "devops-02", etc.
            config: ConductorAI configuration.
            llm_provider: The LLM provider for configuration generation.
                Use MockLLMProvider for testing, OpenAIProvider for production.
            name: Human-readable name. Defaults to agent_id.
            description: Optional agent description.
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.DEVOPS,
            config=config,
            name=name or f"DevOpsAgent-{agent_id}",
            description=description or "Generates CI/CD configurations and infrastructure configs using LLM",
        )

        # Store the LLM provider — this is how the agent "thinks"
        self._llm_provider = llm_provider

        # Bind devops-specific context to the logger
        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type="devops",
            component="devops_agent",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def llm_provider(self) -> BaseLLMProvider:
        """Access the LLM provider.

        Returns:
            The BaseLLMProvider instance used for configuration generation.
        """
        return self._llm_provider

    # =========================================================================
    # BaseAgent Abstract Method Implementations
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that the task contains code or a project description.

        The DevOpsAgent requires at minimum a "code" or "project_description"
        field in the task's input_data. This tells the agent WHAT to create
        CI/CD configurations for.

        Args:
            task: The task to validate.

        Returns:
            True if "code" or "project_description" is present and non-empty,
            False otherwise.
        """
        code = task.input_data.get("code")
        project_description = task.input_data.get("project_description")

        if not code and not project_description:
            self._logger.warning(
                "devops_task_missing_input",
                task_id=task.task_id,
                task_name=task.name,
                available_keys=list(task.input_data.keys()),
            )
            return False

        # The provided input must be a non-empty string
        input_value = code or project_description
        if not isinstance(input_value, str) or not input_value.strip():
            self._logger.warning(
                "devops_task_empty_input",
                task_id=task.task_id,
            )
            return False

        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Generate CI/CD configuration by calling the LLM.

        Execution Steps:
            1. Extract code/project_description, platform, and language from input_data.
            2. Build a detailed user prompt from these inputs.
            3. Call the LLM with system prompt + user prompt.
            4. Package the response into a structured TaskResult.

        Args:
            task: The validated task with code or project_description in input_data.

        Returns:
            TaskResult with generated configuration in output_data.
        """
        # --- Extract inputs ---
        code = task.input_data.get("code", "")
        project_description = task.input_data.get("project_description", "")
        platform = task.input_data.get("platform", "github_actions")
        language = task.input_data.get("language", "python")
        additional_requirements = task.input_data.get("additional_requirements", "")

        self._logger.info(
            "devops_execution_starting",
            task_id=task.task_id,
            platform=platform,
            language=language,
            has_code=bool(code),
            has_description=bool(project_description),
        )

        # --- Build the user prompt ---
        user_prompt = self._build_user_prompt(
            code=code,
            project_description=project_description,
            platform=platform,
            language=language,
            additional_requirements=additional_requirements,
        )

        # --- Call the LLM ---
        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=DEVOPS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=self._config.llm.temperature,
            max_tokens=self._config.llm.max_tokens,
        )

        self._logger.info(
            "devops_llm_response_received",
            task_id=task.task_id,
            response_length=len(llm_response.content),
            model=llm_response.model,
            tokens_used=llm_response.usage.total_tokens,
        )

        # --- Determine the output filename ---
        filename = PLATFORM_FILENAMES.get(platform, f"{platform}-config.yml")

        # --- Build the result ---
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "config": llm_response.content,
                "platform": platform,
                "language": language,
                "files": [filename],
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
                "devops_agent_llm_validation_failed",
                provider=self._llm_provider.provider_name,
                model=self._llm_provider.model,
            )

        self._logger.info(
            "devops_agent_initialized",
            provider=self._llm_provider.provider_name,
            model=self._llm_provider.model,
        )

    # =========================================================================
    # Prompt Building
    # =========================================================================

    @staticmethod
    def _build_user_prompt(
        code: str = "",
        project_description: str = "",
        platform: str = "github_actions",
        language: str = "python",
        additional_requirements: str = "",
    ) -> str:
        """Build the user prompt from task inputs.

        Constructs a clear, structured prompt that tells the LLM exactly
        what configuration to generate. The prompt includes:
        1. The code or project description (what was built)
        2. The target CI/CD platform
        3. The project language
        4. Additional requirements/constraints

        Args:
            code: Source code to create configurations for.
            project_description: Description of the project.
            platform: Target CI/CD platform (e.g., "github_actions", "docker").
            language: Project programming language.
            additional_requirements: Extra instructions or constraints.

        Returns:
            A formatted prompt string ready for the LLM.
        """
        parts = [
            f"Generate a {platform} configuration for a {language} project.\n",
        ]

        if code:
            parts.append(f"## Source Code\n{code}\n")

        if project_description:
            parts.append(f"## Project Description\n{project_description}\n")

        parts.append(
            f"## Requirements\n"
            f"- Platform: {platform}\n"
            f"- Language: {language}\n"
            f"- Include proper build, test, and deploy stages\n"
            f"- Use caching for dependencies where appropriate\n"
            f"- Follow {platform} best practices\n"
            f"- Include security scanning if applicable\n"
        )

        if additional_requirements:
            parts.append(f"## Additional Requirements\n{additional_requirements}\n")

        return "\n".join(parts)
