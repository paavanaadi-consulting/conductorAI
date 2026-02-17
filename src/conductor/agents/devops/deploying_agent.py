"""
conductor.agents.devops.deploying_agent - Deployment Configuration Agent
=========================================================================

This module implements the DeployingAgent — the second specialized agent in
ConductorAI's DEVOPS phase. It generates deployment configurations and scripts
for target environments using an LLM.

Architecture Context:
    The DeployingAgent follows the DevOpsAgent in the DEVOPS phase. It receives
    a target environment and optionally code/CI/CD configs, and produces
    deployment configurations (how to deploy the application).

    ┌───────────────────┐    TaskDefinition     ┌──────────────────┐
    │ AgentCoordinator  │ ──────────────────→   │  DeployingAgent   │
    │                   │                       │                    │
    │                   │ ←── TaskResult ────── │  ┌────────────┐   │
    └───────────────────┘                       │  │ LLMProvider│   │
                                                │  └────────────┘   │
                                                └──────────────────┘

    Input (task.input_data):
        {
            "target_environment": "production",        # required
            "deployment_type": "kubernetes",            # optional, default "kubernetes"
            "code": "...",                              # optional
            "config": "...",                            # optional, CI/CD config from DevOpsAgent
        }

    Output (result.output_data):
        {
            "deployment_config": "...",                # The generated deployment configuration
            "target_environment": "production",
            "deployment_type": "kubernetes",
            "files": ["deployment.yaml"],              # List of generated file names
            "llm_model": "...",
            "llm_usage": {...},
        }

How Deployment Configuration Works:
    1. DeployingAgent receives a TaskDefinition with "target_environment".
    2. It constructs a system prompt (defining the LLM's role as a deployment engineer).
    3. It constructs a user prompt from the environment + deployment type + context.
    4. It calls the LLM provider via generate_with_system().
    5. It packages the LLM response into a TaskResult with structured output.

Usage:
    >>> from conductor.agents.devops import DeployingAgent
    >>> from conductor.core.config import ConductorConfig
    >>> from conductor.integrations.llm import MockLLMProvider
    >>>
    >>> config = ConductorConfig()
    >>> provider = MockLLMProvider()
    >>> agent = DeployingAgent("deploying-01", config, llm_provider=provider)
    >>> await agent.start()
    >>>
    >>> task = TaskDefinition(
    ...     name="Deploy to Production",
    ...     assigned_to=AgentType.DEPLOYING,
    ...     input_data={"target_environment": "production", "deployment_type": "kubernetes"},
    ... )
    >>> result = await agent.execute_task(task)
    >>> result.output_data["deployment_config"]  # The generated deployment config
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
# This system prompt defines the LLM's role as a deployment configuration generator.
# It's used for every generate_with_system() call. The actual task
# details come from the user prompt (built from input_data).
# =============================================================================
DEPLOYING_SYSTEM_PROMPT = """You are an expert deployment engineer working on a professional project.
Your role is to create reliable, production-ready deployment configurations and scripts.

Guidelines:
- Write clean, well-commented deployment configurations following best practices.
- Include comprehensive comments explaining each section and decision.
- Use secure defaults and follow security best practices for the target environment.
- Handle health checks, resource limits, and scaling configurations appropriately.
- Include rollback strategies and zero-downtime deployment patterns.
- Follow the principle of least privilege for service accounts and permissions.
- Generate ONLY the configuration — no explanations or markdown formatting unless requested.

If a specific deployment type is specified, use its idioms and conventions."""


# =============================================================================
# Deployment Type-to-Filename Mapping
# =============================================================================
DEPLOYMENT_TYPE_FILENAMES = {
    "kubernetes": "deployment.yaml",
    "docker_compose": "docker-compose.yml",
    "terraform": "main.tf",
    "ansible": "playbook.yml",
}


class DeployingAgent(BaseAgent):
    """Specialized agent for generating deployment configurations and scripts.

    The DeployingAgent is the deployment producer in ConductorAI's DEVOPS
    phase. It takes a target environment and optional code/CI/CD context,
    sends it to an LLM with appropriate context (system prompt + deployment
    type hints), and returns the generated deployment configuration as a
    structured TaskResult.

    How It Extends BaseAgent:
        - _validate_task(): Checks that input_data contains "target_environment"
        - _execute(): Constructs prompts, calls LLM, packages result
        - _on_start(): Validates the LLM provider is ready

    Input Requirements (task.input_data):
        Required:
            - "target_environment" (str): Deployment target (e.g., "staging", "production")
        Optional:
            - "deployment_type" (str): Type of deployment (default: "kubernetes")
            - "code" (str): Source code for context
            - "config" (str): CI/CD configuration from DevOpsAgent

    Output Format (result.output_data):
        - "deployment_config" (str): The generated deployment configuration
        - "target_environment" (str): Target environment used
        - "deployment_type" (str): Deployment type used
        - "files" (list[str]): Generated file names
        - "llm_model" (str): Which LLM model was used
        - "llm_usage" (dict): Token usage stats

    Attributes:
        _llm_provider: The LLM provider used for deployment configuration generation.

    Example:
        >>> agent = DeployingAgent("deploying-01", config, llm_provider=mock_provider)
        >>> await agent.start()
        >>> result = await agent.execute_task(deploying_task)
        >>> print(result.output_data["deployment_config"])
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
        """Initialize the DeployingAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
                Convention: "deploying-01", "deploying-02", etc.
            config: ConductorAI configuration.
            llm_provider: The LLM provider for deployment configuration generation.
                Use MockLLMProvider for testing, OpenAIProvider for production.
            name: Human-readable name. Defaults to agent_id.
            description: Optional agent description.
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.DEPLOYING,
            config=config,
            name=name or f"DeployingAgent-{agent_id}",
            description=description or "Generates deployment configurations and scripts using LLM",
        )

        # Store the LLM provider — this is how the agent "thinks"
        self._llm_provider = llm_provider

        # Bind deploying-specific context to the logger
        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type="deploying",
            component="deploying_agent",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def llm_provider(self) -> BaseLLMProvider:
        """Access the LLM provider.

        Returns:
            The BaseLLMProvider instance used for deployment configuration generation.
        """
        return self._llm_provider

    # =========================================================================
    # BaseAgent Abstract Method Implementations
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that the task contains a target environment.

        The DeployingAgent requires a "target_environment" field in the
        task's input_data. This tells the agent WHERE to deploy.

        Args:
            task: The task to validate.

        Returns:
            True if "target_environment" is present and non-empty, False otherwise.
        """
        target_environment = task.input_data.get("target_environment")

        if not target_environment:
            self._logger.warning(
                "deploying_task_missing_target_environment",
                task_id=task.task_id,
                task_name=task.name,
                available_keys=list(task.input_data.keys()),
            )
            return False

        # Target environment must be a non-empty string
        if not isinstance(target_environment, str) or not target_environment.strip():
            self._logger.warning(
                "deploying_task_empty_target_environment",
                task_id=task.task_id,
            )
            return False

        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Generate deployment configuration by calling the LLM.

        Execution Steps:
            1. Extract target_environment, deployment_type, code, and config from input_data.
            2. Build a detailed user prompt from these inputs.
            3. Call the LLM with system prompt + user prompt.
            4. Package the response into a structured TaskResult.

        Args:
            task: The validated task with target_environment in input_data.

        Returns:
            TaskResult with generated deployment configuration in output_data.
        """
        # --- Extract inputs ---
        target_environment = task.input_data["target_environment"]
        deployment_type = task.input_data.get("deployment_type", "kubernetes")
        code = task.input_data.get("code", "")
        config = task.input_data.get("config", "")

        self._logger.info(
            "deploying_execution_starting",
            task_id=task.task_id,
            target_environment=target_environment,
            deployment_type=deployment_type,
            has_code=bool(code),
            has_config=bool(config),
        )

        # --- Build the user prompt ---
        user_prompt = self._build_user_prompt(
            target_environment=target_environment,
            deployment_type=deployment_type,
            code=code,
            config=config,
        )

        # --- Call the LLM ---
        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=DEPLOYING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=self._config.llm.temperature,
            max_tokens=self._config.llm.max_tokens,
        )

        self._logger.info(
            "deploying_llm_response_received",
            task_id=task.task_id,
            response_length=len(llm_response.content),
            model=llm_response.model,
            tokens_used=llm_response.usage.total_tokens,
        )

        # --- Determine the output filename ---
        filename = DEPLOYMENT_TYPE_FILENAMES.get(deployment_type, f"{deployment_type}-deploy.yml")

        # --- Build the result ---
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "deployment_config": llm_response.content,
                "target_environment": target_environment,
                "deployment_type": deployment_type,
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
                "deploying_agent_llm_validation_failed",
                provider=self._llm_provider.provider_name,
                model=self._llm_provider.model,
            )

        self._logger.info(
            "deploying_agent_initialized",
            provider=self._llm_provider.provider_name,
            model=self._llm_provider.model,
        )

    # =========================================================================
    # Prompt Building
    # =========================================================================

    @staticmethod
    def _build_user_prompt(
        target_environment: str,
        deployment_type: str = "kubernetes",
        code: str = "",
        config: str = "",
    ) -> str:
        """Build the user prompt from task inputs.

        Constructs a clear, structured prompt that tells the LLM exactly
        what deployment configuration to generate. The prompt includes:
        1. The target environment (where to deploy)
        2. The deployment type (how to deploy)
        3. Source code context (if provided)
        4. CI/CD configuration context (if provided)

        Args:
            target_environment: Target deployment environment (e.g., "staging", "production").
            deployment_type: Type of deployment (e.g., "kubernetes", "docker_compose").
            code: Optional source code for context.
            config: Optional CI/CD configuration from DevOpsAgent.

        Returns:
            A formatted prompt string ready for the LLM.
        """
        parts = [
            f"Generate a {deployment_type} deployment configuration for the {target_environment} environment.\n",
        ]

        if code:
            parts.append(f"## Source Code\n{code}\n")

        if config:
            parts.append(f"## CI/CD Configuration\n{config}\n")

        parts.append(
            f"## Requirements\n"
            f"- Target Environment: {target_environment}\n"
            f"- Deployment Type: {deployment_type}\n"
            f"- Include health checks and readiness probes\n"
            f"- Configure appropriate resource limits\n"
            f"- Follow {deployment_type} best practices\n"
            f"- Include rollback strategy\n"
            f"- Ensure zero-downtime deployment\n"
        )

        return "\n".join(parts)
