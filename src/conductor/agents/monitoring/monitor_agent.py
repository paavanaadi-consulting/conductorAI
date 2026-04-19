"""
conductor.agents.monitoring.monitor_agent - System Monitor & Feedback Agent
=============================================================================

This module implements the MonitorAgent — the sole agent in ConductorAI's
MONITORING phase. It analyzes deployment results, logs, and metrics, then
generates feedback that can trigger the development phase to run again.

Architecture Context:
    The MonitorAgent is the final agent in the pipeline and the critical
    component of the feedback loop. When it detects issues (errors, performance
    degradation, quality concerns), it produces feedback that the Workflow
    Engine uses to re-trigger the DEVELOPMENT phase.

    ┌────────────────┐   analysis   ┌─────────────────┐
    │ DeployingAgent │ ──────────→  │  MonitorAgent   │
    │ (deploys)      │              │  (monitors)      │
    └────────────────┘              └──────┬──────────┘
                                           │
                                           │ feedback
                                           ↓
    ┌────────────────┐              ┌─────────────────┐
    │  CodingAgent   │ ←────────── │ WorkflowEngine  │
    │  (fixes)       │  re-trigger │ (feedback loop)  │
    └────────────────┘              └─────────────────┘

    Input (task.input_data):
        {
            "deployment_result": "...",     # REQUIRED: What was deployed
            "metrics": "...",               # optional: Performance metrics
            "logs": "...",                  # optional: Application logs
            "previous_feedback": "...",     # optional: Earlier feedback
        }

    Output (result.output_data):
        {
            "analysis": "...",              # The LLM's analysis text
            "has_issues": true/false,       # Whether issues were found
            "severity": "low|medium|high|critical",
            "issues": [...],               # List of identified issues
            "recommendations": [...],       # List of recommended fixes
            "feedback_for_development": "...",  # Feedback to pass back
            "llm_model": "...",
            "llm_usage": {...},
        }

How Monitoring Works:
    1. MonitorAgent receives a TaskDefinition with "deployment_result".
    2. It constructs a system prompt (defining the LLM's role as a systems monitor).
    3. It constructs a user prompt from the deployment result + metrics + logs.
    4. It calls the LLM provider via generate_with_system().
    5. It parses the LLM response to extract issues, severity, recommendations.
    6. It packages everything into a TaskResult with structured output.
    7. The WorkflowEngine checks "has_issues" — if True, triggers feedback loop.

Usage:
    >>> from conductor.agents.monitoring import MonitorAgent
    >>> from conductor.core.config import ConductorConfig
    >>> from conductor.integrations.llm import MockLLMProvider
    >>>
    >>> config = ConductorConfig()
    >>> provider = MockLLMProvider()
    >>> agent = MonitorAgent("monitor-01", config, llm_provider=provider)
    >>> await agent.start()
    >>>
    >>> task = TaskDefinition(
    ...     name="Monitor Deployment",
    ...     assigned_to=AgentType.MONITOR,
    ...     input_data={"deployment_result": "Deployed successfully to production"},
    ... )
    >>> result = await agent.execute_task(task)
    >>> result.output_data["has_issues"]  # True or False
"""

from __future__ import annotations

import re
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
# This system prompt defines the LLM's role as a systems monitor / SRE.
# It instructs the LLM to analyze deployment results and produce structured
# feedback with severity, issues, and recommendations.
# =============================================================================
MONITOR_SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) and systems monitor.
Your role is to analyze deployment results, application logs, and metrics to identify issues.

Guidelines:
- Analyze the deployment result for errors, warnings, and potential problems.
- Assess the severity of any issues found (low, medium, high, critical).
- Provide specific, actionable recommendations to fix identified issues.
- Consider performance, security, reliability, and correctness.
- If metrics or logs are provided, analyze them for anomalies.
- Look for patterns that could indicate future problems.

Response Format (ALWAYS follow this structure):
## Severity: [low|medium|high|critical|none]

## Issues Found
1. [Issue description]
2. [Issue description]
(or "No issues found" if deployment looks healthy)

## Recommendations
1. [Specific recommendation]
2. [Specific recommendation]
(or "No recommendations" if everything looks good)

## Feedback for Development
[Concise summary of what the development team should address, or "No action needed"]
"""


# =============================================================================
# Severity Levels
# =============================================================================
VALID_SEVERITIES = {"none", "low", "medium", "high", "critical"}


class MonitorAgent(BaseAgent):
    """Specialized agent for monitoring deployments and generating feedback.

    The MonitorAgent is the sole agent in the MONITORING phase. It analyzes
    deployment results (and optionally logs/metrics) to determine if issues
    exist that need to be fed back to the development phase.

    How It Extends BaseAgent:
        - _validate_task(): Checks that input_data contains "deployment_result"
        - _execute(): Constructs prompts, calls LLM, parses response
        - _on_start(): Validates the LLM provider is ready

    Input Requirements (task.input_data):
        Required:
            - "deployment_result" (str): Deployment outcome to analyze.
        Optional:
            - "metrics" (str): Performance metrics data.
            - "logs" (str): Application or system logs.
            - "previous_feedback" (str): Earlier feedback from a previous loop.

    Output Format (result.output_data):
        - "analysis" (str): Full LLM analysis text
        - "has_issues" (bool): Whether any issues were identified
        - "severity" (str): Overall severity (none, low, medium, high, critical)
        - "issues" (list[str]): List of identified issues
        - "recommendations" (list[str]): List of recommended fixes
        - "feedback_for_development" (str): Summary feedback for dev team
        - "llm_model" (str): Which LLM model was used
        - "llm_usage" (dict): Token usage stats

    Attributes:
        _llm_provider: The LLM provider used for deployment analysis.

    Example:
        >>> agent = MonitorAgent("monitor-01", config, llm_provider=mock_provider)
        >>> await agent.start()
        >>> result = await agent.execute_task(monitor_task)
        >>> if result.output_data["has_issues"]:
        ...     print("Issues found! Triggering feedback loop.")
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
        """Initialize the MonitorAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
                Convention: "monitor-01", "monitor-02", etc.
            config: ConductorAI configuration.
            llm_provider: The LLM provider for deployment analysis.
                Use MockLLMProvider for testing, OpenAIProvider for production.
            name: Human-readable name. Defaults to agent_id.
            description: Optional agent description.
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.MONITOR,
            config=config,
            name=name or f"MonitorAgent-{agent_id}",
            description=description or "Analyzes deployments and generates feedback using LLM",
        )

        # Store the LLM provider — this is how the agent "thinks"
        self._llm_provider = llm_provider

        # Bind monitor-specific context to the logger
        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type="monitor",
            component="monitor_agent",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def llm_provider(self) -> BaseLLMProvider:
        """Access the LLM provider.

        Returns:
            The BaseLLMProvider instance used for deployment analysis.
        """
        return self._llm_provider

    # =========================================================================
    # BaseAgent Abstract Method Implementations
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that the task contains a deployment result to analyze.

        The MonitorAgent requires a "deployment_result" field in the task's
        input_data. This is the deployment outcome to analyze.

        Args:
            task: The task to validate.

        Returns:
            True if "deployment_result" is present and non-empty, False otherwise.
        """
        deployment_result = task.input_data.get("deployment_result")

        if not deployment_result:
            self._logger.warning(
                "monitor_task_missing_deployment_result",
                task_id=task.task_id,
                task_name=task.name,
                available_keys=list(task.input_data.keys()),
            )
            return False

        # Deployment result must be a non-empty string
        if not isinstance(deployment_result, str) or not deployment_result.strip():
            self._logger.warning(
                "monitor_task_empty_deployment_result",
                task_id=task.task_id,
            )
            return False

        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Analyze a deployment by calling the LLM.

        Execution Steps:
            1. Extract deployment_result, metrics, logs from input_data.
            2. Build a detailed user prompt from these inputs.
            3. Call the LLM with system prompt + user prompt.
            4. Parse the response for severity, issues, recommendations.
            5. Package everything into a structured TaskResult.

        Args:
            task: The validated task with deployment_result in input_data.

        Returns:
            TaskResult with analysis and feedback in output_data.
        """
        # --- Extract inputs ---
        deployment_result = task.input_data["deployment_result"]
        metrics = task.input_data.get("metrics", "")
        logs = task.input_data.get("logs", "")
        previous_feedback = task.input_data.get("previous_feedback", "")

        self._logger.info(
            "monitor_execution_starting",
            task_id=task.task_id,
            deployment_result_length=len(deployment_result),
            has_metrics=bool(metrics),
            has_logs=bool(logs),
            has_previous_feedback=bool(previous_feedback),
        )

        # --- Build the user prompt ---
        user_prompt = self._build_user_prompt(
            deployment_result=deployment_result,
            metrics=metrics,
            logs=logs,
            previous_feedback=previous_feedback,
        )

        # --- Call the LLM ---
        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=MONITOR_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=self._config.llm.temperature,
            max_tokens=self._config.llm.max_tokens,
        )

        self._logger.info(
            "monitor_llm_response_received",
            task_id=task.task_id,
            response_length=len(llm_response.content),
            model=llm_response.model,
            tokens_used=llm_response.usage.total_tokens,
        )

        # --- Parse the response ---
        parsed = self._parse_monitor_response(llm_response.content)

        # --- Build the result ---
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "analysis": llm_response.content,
                "has_issues": parsed["has_issues"],
                "severity": parsed["severity"],
                "issues": parsed["issues"],
                "recommendations": parsed["recommendations"],
                "feedback_for_development": parsed["feedback_for_development"],
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
                "monitor_agent_llm_validation_failed",
                provider=self._llm_provider.provider_name,
                model=self._llm_provider.model,
            )

        self._logger.info(
            "monitor_agent_initialized",
            provider=self._llm_provider.provider_name,
            model=self._llm_provider.model,
        )

    # =========================================================================
    # Response Parsing
    # =========================================================================

    @staticmethod
    def _parse_monitor_response(text: str) -> dict[str, Any]:
        """Parse the LLM's monitoring analysis response.

        Extracts structured data from the LLM's text response:
        - severity: from "Severity: [level]" pattern
        - issues: from numbered list under "Issues Found"
        - recommendations: from numbered list under "Recommendations"
        - feedback_for_development: from "Feedback for Development" section
        - has_issues: True if severity != "none" and issues are found

        Args:
            text: The raw LLM response text.

        Returns:
            Dict with keys: severity, issues, recommendations,
            feedback_for_development, has_issues.
        """
        # --- Extract severity ---
        severity = "none"
        severity_match = re.search(
            r"severity[:\s]*\*{0,2}\s*(none|low|medium|high|critical)",
            text,
            re.IGNORECASE,
        )
        if severity_match:
            severity = severity_match.group(1).lower()

        # --- Extract issues ---
        issues: list[str] = []
        issues_section = re.search(
            r"Issues\s+Found\s*\n([\s\S]*?)(?:\n##|\Z)",
            text,
            re.IGNORECASE,
        )
        if issues_section:
            # Extract numbered items (1. ..., 2. ..., etc.)
            items = re.findall(r"\d+\.\s*(.+)", issues_section.group(1))
            issues = [
                item.strip()
                for item in items
                if item.strip().lower() != "no issues found"
                and item.strip().lower() != "none"
            ]

        # --- Extract recommendations ---
        recommendations: list[str] = []
        recs_section = re.search(
            r"Recommendations\s*\n([\s\S]*?)(?:\n##|\Z)",
            text,
            re.IGNORECASE,
        )
        if recs_section:
            items = re.findall(r"\d+\.\s*(.+)", recs_section.group(1))
            recommendations = [
                item.strip()
                for item in items
                if item.strip().lower() != "no recommendations"
                and item.strip().lower() != "none"
            ]

        # --- Extract feedback for development ---
        feedback = ""
        feedback_section = re.search(
            r"Feedback\s+for\s+Development\s*\n([\s\S]*?)(?:\n##|\Z)",
            text,
            re.IGNORECASE,
        )
        if feedback_section:
            feedback_text = feedback_section.group(1).strip()
            if feedback_text.lower() not in ("no action needed", "none", "n/a"):
                feedback = feedback_text

        # --- Determine has_issues ---
        # Issues exist if severity is not "none" OR there are actual issues found
        has_issues = severity != "none" or len(issues) > 0

        return {
            "severity": severity,
            "issues": issues,
            "recommendations": recommendations,
            "feedback_for_development": feedback,
            "has_issues": has_issues,
        }

    # =========================================================================
    # Prompt Building
    # =========================================================================

    @staticmethod
    def _build_user_prompt(
        deployment_result: str,
        metrics: str = "",
        logs: str = "",
        previous_feedback: str = "",
    ) -> str:
        """Build the user prompt from task inputs.

        Constructs a clear, structured prompt that tells the LLM exactly
        what to analyze. The prompt includes:
        1. The deployment result (what happened)
        2. Metrics data (if available)
        3. Application logs (if available)
        4. Previous feedback (if this is a re-analysis after a fix)

        Args:
            deployment_result: The deployment outcome to analyze.
            metrics: Optional performance metrics data.
            logs: Optional application or system logs.
            previous_feedback: Optional earlier feedback from a previous loop.

        Returns:
            A formatted prompt string ready for the LLM.
        """
        parts = [
            "Analyze the following deployment result and provide a detailed assessment:\n",
            f"## Deployment Result\n{deployment_result}\n",
        ]

        if metrics:
            parts.append(f"## Performance Metrics\n{metrics}\n")

        if logs:
            parts.append(f"## Application Logs\n{logs}\n")

        if previous_feedback:
            parts.append(
                f"## Previous Feedback (from earlier monitoring cycle)\n"
                f"{previous_feedback}\n"
                f"Please check if the issues from the previous feedback have been addressed.\n"
            )

        parts.append(
            "## Analysis Requirements\n"
            "- Identify any errors, warnings, or anomalies\n"
            "- Assess the overall health and stability of the deployment\n"
            "- Provide actionable recommendations for the development team\n"
            "- Determine if the deployment needs immediate attention\n"
        )

        return "\n".join(parts)
