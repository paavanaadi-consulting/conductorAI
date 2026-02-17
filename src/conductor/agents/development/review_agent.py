"""
conductor.agents.development.review_agent - Code Review Agent
===============================================================

This module implements the ReviewAgent — the quality gatekeeper in the
DEVELOPMENT phase. It reviews code for quality, bugs, style, and best
practices using an LLM.

Architecture Context:
    The ReviewAgent sits after the CodingAgent in the development pipeline.
    It receives code produced by the CodingAgent and evaluates it.

    ┌─────────────┐  code   ┌─────────────┐  reviewed   ┌───────────┐
    │ CodingAgent │ ──────→ │ ReviewAgent │ ──────────→ │ TestAgent │
    │ (generates) │         │ (reviews)   │             │ (tests)   │
    └─────────────┘         └─────────────┘             └───────────┘

    Input (task.input_data):
        {
            "code": "def hello(): ...",           # REQUIRED: Code to review
            "language": "python",                 # optional, default "python"
            "review_criteria": ["security", ...], # optional criteria
            "context": "REST API endpoint",       # optional context
        }

    Output (result.output_data):
        {
            "review": "...",                  # Full review text from LLM
            "approved": true/false,           # Whether the code passes review
            "score": 8,                       # Quality score out of 10
            "findings": [...],                # List of finding descriptions
            "recommendations": [...],         # List of improvement suggestions
            "language": "python",
        }

How Code Review Works:
    1. ReviewAgent receives a task with "code" in input_data.
    2. It constructs a system prompt (defining the LLM's role as a reviewer).
    3. It builds a user prompt with the code + review criteria.
    4. It calls the LLM provider via generate_with_system().
    5. It parses the LLM response to extract structured review data.
    6. It packages everything into a TaskResult.

Usage:
    >>> from conductor.agents.development import ReviewAgent
    >>> agent = ReviewAgent("review-01", config, llm_provider=mock_provider)
    >>> await agent.start()
    >>> result = await agent.execute_task(review_task)
    >>> print(result.output_data["approved"])  # True or False
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
REVIEW_SYSTEM_PROMPT = """You are a senior code reviewer conducting a thorough code review.
Your role is to evaluate code quality, identify potential bugs, and suggest improvements.

Review Guidelines:
- Check for correctness: Does the code do what it's supposed to do?
- Check for security: Are there any security vulnerabilities?
- Check for performance: Are there obvious performance issues?
- Check for readability: Is the code easy to understand and maintain?
- Check for best practices: Does it follow language-specific conventions?
- Check for error handling: Are errors handled gracefully?

Output Format:
Provide your review as a structured report with:
1. An overall quality score from 1-10
2. A clear APPROVED or REJECTED verdict
3. A list of specific findings (bugs, style issues, security concerns)
4. A list of actionable recommendations

Be constructive and specific in your feedback."""


class ReviewAgent(BaseAgent):
    """Specialized agent for reviewing source code quality.

    The ReviewAgent examines code produced by the CodingAgent (or provided
    externally) and evaluates it against quality criteria. It uses an LLM
    to perform intelligent code review, producing structured feedback.

    How It Extends BaseAgent:
        - _validate_task(): Checks that input_data contains "code"
        - _execute(): Constructs review prompts, calls LLM, parses response
        - _on_start(): Validates the LLM provider is ready

    Input Requirements (task.input_data):
        Required:
            - "code" (str): The source code to review.
        Optional:
            - "language" (str): Programming language (default: "python")
            - "review_criteria" (list[str]): Specific aspects to focus on
                (e.g., ["security", "performance", "readability"])
            - "context" (str): Description of what the code does
            - "specification" (str): Original spec the code was built from

    Output Format (result.output_data):
        - "review" (str): Full review text from the LLM
        - "approved" (bool): Whether the code passes review
        - "score" (int): Quality score out of 10
        - "findings" (list[str]): Specific issues found
        - "recommendations" (list[str]): Improvement suggestions
        - "language" (str): Language of the reviewed code
        - "llm_model" (str): Which LLM model was used
        - "llm_usage" (dict): Token usage stats

    Attributes:
        _llm_provider: The LLM provider used for code review.
        _approval_threshold: Minimum score (1-10) for auto-approval.

    Example:
        >>> agent = ReviewAgent("review-01", config, llm_provider=mock_provider)
        >>> await agent.start()
        >>> result = await agent.execute_task(review_task)
        >>> print(result.output_data["approved"])  # True
        >>> print(result.output_data["score"])      # 8
    """

    def __init__(
        self,
        agent_id: str,
        config: ConductorConfig,
        *,
        llm_provider: BaseLLMProvider,
        approval_threshold: int = 6,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Initialize the ReviewAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
                Convention: "review-01", "review-02", etc.
            config: ConductorAI configuration.
            llm_provider: The LLM provider for code review.
            approval_threshold: Minimum quality score (1-10) for auto-approval.
                Code scoring at or above this threshold is marked approved=True.
                Default is 6 (reviews scoring 6+ are approved).
            name: Human-readable name. Defaults to agent_id.
            description: Optional agent description.
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.REVIEW,
            config=config,
            name=name or f"ReviewAgent-{agent_id}",
            description=description or "Reviews source code for quality, bugs, and best practices",
        )

        # Store the LLM provider and approval threshold
        self._llm_provider = llm_provider
        self._approval_threshold = max(1, min(10, approval_threshold))

        # Bind review-specific context to the logger
        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type="review",
            component="review_agent",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def llm_provider(self) -> BaseLLMProvider:
        """Access the LLM provider.

        Returns:
            The BaseLLMProvider instance used for code review.
        """
        return self._llm_provider

    @property
    def approval_threshold(self) -> int:
        """The minimum score for auto-approval.

        Returns:
            Integer threshold (1-10).
        """
        return self._approval_threshold

    # =========================================================================
    # BaseAgent Abstract Method Implementations
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that the task contains code to review.

        The ReviewAgent requires at minimum a "code" field in the task's
        input_data. This is the source code to be reviewed.

        Args:
            task: The task to validate.

        Returns:
            True if "code" is present and non-empty, False otherwise.
        """
        code = task.input_data.get("code")

        if not code:
            self._logger.warning(
                "review_task_missing_code",
                task_id=task.task_id,
                task_name=task.name,
                available_keys=list(task.input_data.keys()),
            )
            return False

        # Code must be a non-empty string
        if not isinstance(code, str) or not code.strip():
            self._logger.warning(
                "review_task_empty_code",
                task_id=task.task_id,
            )
            return False

        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Review code by calling the LLM with the code and review criteria.

        Execution Steps:
            1. Extract code, language, and criteria from input_data.
            2. Build a detailed review prompt.
            3. Call the LLM with system prompt + review prompt.
            4. Parse the LLM response for structured feedback.
            5. Determine approval based on score vs threshold.
            6. Package into a TaskResult.

        Args:
            task: The validated task with code in input_data.

        Returns:
            TaskResult with review findings in output_data.
        """
        # --- Extract inputs ---
        code = task.input_data["code"]
        language = task.input_data.get("language", "python")
        review_criteria = task.input_data.get("review_criteria", [])
        context = task.input_data.get("context", "")
        specification = task.input_data.get("specification", "")

        self._logger.info(
            "review_execution_starting",
            task_id=task.task_id,
            language=language,
            code_length=len(code),
            criteria_count=len(review_criteria),
        )

        # --- Build the user prompt ---
        user_prompt = self._build_review_prompt(
            code=code,
            language=language,
            review_criteria=review_criteria,
            context=context,
            specification=specification,
        )

        # --- Call the LLM ---
        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=max(0.3, self._config.llm.temperature - 0.2),
            max_tokens=self._config.llm.max_tokens,
        )

        self._logger.info(
            "review_llm_response_received",
            task_id=task.task_id,
            response_length=len(llm_response.content),
            model=llm_response.model,
        )

        # --- Parse the review response ---
        review_data = self._parse_review_response(llm_response.content)

        # --- Determine approval ---
        score = review_data.get("score", 7)
        approved = score >= self._approval_threshold

        self._logger.info(
            "review_completed",
            task_id=task.task_id,
            score=score,
            approved=approved,
            findings_count=len(review_data.get("findings", [])),
        )

        # --- Build the result ---
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "review": llm_response.content,
                "approved": approved,
                "score": score,
                "findings": review_data.get("findings", []),
                "recommendations": review_data.get("recommendations", []),
                "language": language,
                "llm_model": llm_response.model,
                "llm_usage": llm_response.usage.model_dump(),
            },
        )

    async def _on_start(self) -> None:
        """Validate the LLM provider during startup."""
        is_valid = await self._llm_provider.validate()
        if not is_valid:
            self._logger.warning(
                "review_agent_llm_validation_failed",
                provider=self._llm_provider.provider_name,
                model=self._llm_provider.model,
            )

        self._logger.info(
            "review_agent_initialized",
            provider=self._llm_provider.provider_name,
            model=self._llm_provider.model,
            approval_threshold=self._approval_threshold,
        )

    # =========================================================================
    # Prompt Building
    # =========================================================================

    @staticmethod
    def _build_review_prompt(
        code: str,
        language: str,
        review_criteria: list[str] | None = None,
        context: str = "",
        specification: str = "",
    ) -> str:
        """Build the review prompt from task inputs.

        Constructs a detailed prompt that tells the LLM exactly what to
        review and what criteria to focus on.

        Args:
            code: The source code to review.
            language: Programming language of the code.
            review_criteria: Specific aspects to focus on.
            context: Description of what the code does.
            specification: Original specification the code was built from.

        Returns:
            A formatted review prompt string.
        """
        parts = [f"Review the following {language} code:\n"]

        if context:
            parts.append(f"## Context\n{context}\n")

        if specification:
            parts.append(f"## Original Specification\n{specification}\n")

        parts.append(f"## Code\n```{language}\n{code}\n```\n")

        if review_criteria:
            criteria_str = "\n".join(f"- {c}" for c in review_criteria)
            parts.append(f"## Review Focus Areas\n{criteria_str}\n")

        parts.append(
            "## Required Output Format\n"
            "1. Overall Score (1-10)\n"
            "2. Verdict: APPROVED or REJECTED\n"
            "3. Findings (numbered list of issues)\n"
            "4. Recommendations (numbered list of improvements)\n"
        )

        return "\n".join(parts)

    # =========================================================================
    # Response Parsing
    # =========================================================================

    @staticmethod
    def _parse_review_response(review_text: str) -> dict[str, Any]:
        """Parse the LLM review response into structured data.

        Extracts score, findings, and recommendations from the LLM's
        review text. Uses regex patterns and keyword detection.

        The parser is intentionally lenient — if it can't extract structured
        data, it falls back to sensible defaults. This ensures the agent
        doesn't fail just because the LLM formatted its response differently.

        Args:
            review_text: The raw review text from the LLM.

        Returns:
            Dict with "score", "findings", and "recommendations" keys.
        """
        result: dict[str, Any] = {
            "score": 7,
            "findings": [],
            "recommendations": [],
        }

        text_lower = review_text.lower()

        # --- Extract score ---
        # Look for patterns like "Score: 8/10", "Quality: 8", "8 out of 10"
        score_patterns = [
            r"(?:score|quality|rating)\s*[:=]\s*(\d{1,2})\s*/\s*10",
            r"(\d{1,2})\s*/\s*10",
            r"(?:score|quality|rating)\s*[:=]\s*(\d{1,2})",
            r"(\d{1,2})\s*out\s*of\s*10",
        ]
        for pattern in score_patterns:
            match = re.search(pattern, text_lower)
            if match:
                score = int(match.group(1))
                if 1 <= score <= 10:
                    result["score"] = score
                    break

        # --- Extract findings ---
        # Look for numbered items after "Findings" header
        findings_section = re.search(
            r"(?:findings|issues|problems|bugs)(.*?)(?:recommend|suggest|verdict|$)",
            review_text,
            re.DOTALL | re.IGNORECASE,
        )
        if findings_section:
            finding_items = re.findall(
                r"(?:^|\n)\s*(?:\d+[\.\)]\s*|[-*]\s*)\**(.+?)(?:\n|$)",
                findings_section.group(1),
            )
            result["findings"] = [f.strip() for f in finding_items if f.strip()]

        # --- Extract recommendations ---
        # Look for numbered items after "Recommendations" header
        rec_section = re.search(
            r"(?:recommend|suggest|improvement)(.*?)(?:verdict|$)",
            review_text,
            re.DOTALL | re.IGNORECASE,
        )
        if rec_section:
            rec_items = re.findall(
                r"(?:^|\n)\s*(?:\d+[\.\)]\s*|[-*]\s*)\**(.+?)(?:\n|$)",
                rec_section.group(1),
            )
            result["recommendations"] = [r.strip() for r in rec_items if r.strip()]

        return result
