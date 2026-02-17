"""
Tests for conductor.agents.development.review_agent
======================================================

These tests verify the ReviewAgent — the quality gatekeeper that reviews
source code using an LLM and produces structured feedback.

What's Being Tested:
    - Agent initialization (identity, type, approval threshold)
    - Task validation (code required, non-empty)
    - Code review execution (prompt building, LLM call, result packaging)
    - Output structure (review, approved, score, findings, recommendations)
    - Approval logic (threshold-based auto-approval)
    - Response parsing (score extraction, findings extraction)
    - Error handling (LLM failure)

All tests use MockLLMProvider — no real API calls.
"""

import pytest

from conductor.agents.development.review_agent import ReviewAgent, REVIEW_SYSTEM_PROMPT
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentStatus, AgentType, TaskStatus
from conductor.core.exceptions import AgentError
from conductor.core.models import TaskDefinition
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Helpers
# =============================================================================
def _config() -> ConductorConfig:
    return ConductorConfig()


def _provider() -> MockLLMProvider:
    return MockLLMProvider()


SAMPLE_REVIEW_RESPONSE = """## Code Review Summary

**Overall Quality**: Good
**Score**: 8/10

### Findings

1. **Missing input validation**: The function does not check for None input.
2. **No error handling**: Add try/except for edge cases.
3. **Style**: Variable names could be more descriptive.

### Recommendations

1. Add type hints to all function parameters.
2. Consider adding logging for debugging.
3. Add unit tests for edge cases.

**Verdict**: APPROVED with minor suggestions.
"""


def _review_task(**overrides) -> TaskDefinition:
    """Create a standard review task with optional overrides."""
    defaults = {
        "name": "Review API Code",
        "assigned_to": AgentType.REVIEW,
        "input_data": {
            "code": "def hello():\n    return 'Hello, World!'",
            "language": "python",
        },
    }
    defaults.update(overrides)
    return TaskDefinition(**defaults)


# =============================================================================
# Tests: Agent Initialization
# =============================================================================
class TestReviewAgentInit:
    """Tests for ReviewAgent initialization."""

    def test_creates_with_correct_type(self) -> None:
        """ReviewAgent should have AgentType.REVIEW."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider())
        assert agent.agent_type == AgentType.REVIEW

    def test_creates_with_identity(self) -> None:
        """Agent should have correct ID and name."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider())
        assert agent.agent_id == "review-01"
        assert "ReviewAgent" in agent.identity.name

    def test_default_approval_threshold(self) -> None:
        """Default threshold should be 6."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider())
        assert agent.approval_threshold == 6

    def test_custom_approval_threshold(self) -> None:
        """Custom threshold should be respected."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider(), approval_threshold=8)
        assert agent.approval_threshold == 8

    def test_threshold_clamped_to_range(self) -> None:
        """Threshold should be clamped to 1-10."""
        agent_low = ReviewAgent("r-01", _config(), llm_provider=_provider(), approval_threshold=0)
        assert agent_low.approval_threshold == 1

        agent_high = ReviewAgent("r-02", _config(), llm_provider=_provider(), approval_threshold=15)
        assert agent_high.approval_threshold == 10

    def test_llm_provider_accessible(self) -> None:
        """LLM provider should be accessible."""
        provider = _provider()
        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        assert agent.llm_provider is provider


# =============================================================================
# Tests: Task Validation
# =============================================================================
class TestReviewAgentValidation:
    """Tests for _validate_task."""

    async def test_valid_task_passes(self) -> None:
        """Task with code should pass validation."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider())
        task = _review_task()
        assert await agent._validate_task(task) is True

    async def test_missing_code_fails(self) -> None:
        """Task without code should fail validation."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider())
        task = _review_task(input_data={"language": "python"})
        assert await agent._validate_task(task) is False

    async def test_empty_code_fails(self) -> None:
        """Task with empty code should fail validation."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider())
        task = _review_task(input_data={"code": ""})
        assert await agent._validate_task(task) is False

    async def test_whitespace_code_fails(self) -> None:
        """Task with whitespace-only code should fail."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider())
        task = _review_task(input_data={"code": "   "})
        assert await agent._validate_task(task) is False

    async def test_validation_failure_raises_agent_error(self) -> None:
        """Invalid task should raise AgentError through execute_task."""
        agent = ReviewAgent("review-01", _config(), llm_provider=_provider())
        await agent.start()

        task = _review_task(input_data={"language": "python"})
        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(task)
        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"


# =============================================================================
# Tests: Code Review Execution
# =============================================================================
class TestReviewAgentExecution:
    """Tests for _execute (code review)."""

    async def test_reviews_code_and_returns_result(self) -> None:
        """Agent should review code and return structured result."""
        provider = _provider()
        provider.queue_response(SAMPLE_REVIEW_RESPONSE)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "review-01"
        assert "review" in result.output_data
        assert "approved" in result.output_data
        assert "score" in result.output_data

    async def test_output_includes_findings(self) -> None:
        """Result should include parsed findings."""
        provider = _provider()
        provider.queue_response(SAMPLE_REVIEW_RESPONSE)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task()
        result = await agent.execute_task(task)

        assert "findings" in result.output_data
        assert isinstance(result.output_data["findings"], list)

    async def test_output_includes_recommendations(self) -> None:
        """Result should include parsed recommendations."""
        provider = _provider()
        provider.queue_response(SAMPLE_REVIEW_RESPONSE)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task()
        result = await agent.execute_task(task)

        assert "recommendations" in result.output_data
        assert isinstance(result.output_data["recommendations"], list)

    async def test_output_includes_llm_metadata(self) -> None:
        """Result should include LLM model and usage."""
        provider = _provider()
        provider.queue_response(SAMPLE_REVIEW_RESPONSE)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task()
        result = await agent.execute_task(task)

        assert "llm_model" in result.output_data
        assert "llm_usage" in result.output_data

    async def test_language_passed_to_output(self) -> None:
        """Output should include the language of the reviewed code."""
        provider = _provider()
        provider.queue_response(SAMPLE_REVIEW_RESPONSE)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task(input_data={
            "code": "console.log('hello')",
            "language": "javascript",
        })
        result = await agent.execute_task(task)

        assert result.output_data["language"] == "javascript"


# =============================================================================
# Tests: Approval Logic
# =============================================================================
class TestReviewAgentApproval:
    """Tests for approval threshold logic."""

    async def test_high_score_approved(self) -> None:
        """Score above threshold should be approved."""
        provider = _provider()
        provider.queue_response("**Score**: 9/10\n\n**Verdict**: APPROVED")

        agent = ReviewAgent("review-01", _config(), llm_provider=provider, approval_threshold=6)
        await agent.start()

        task = _review_task()
        result = await agent.execute_task(task)

        assert result.output_data["approved"] is True

    async def test_low_score_rejected(self) -> None:
        """Score below threshold should be rejected."""
        provider = _provider()
        provider.queue_response("**Score**: 3/10\n\n**Verdict**: REJECTED")

        agent = ReviewAgent("review-01", _config(), llm_provider=provider, approval_threshold=6)
        await agent.start()

        task = _review_task()
        result = await agent.execute_task(task)

        assert result.output_data["approved"] is False

    async def test_score_equals_threshold_approved(self) -> None:
        """Score exactly at threshold should be approved."""
        provider = _provider()
        provider.queue_response("**Score**: 6/10\n\nFindings\n1. Minor issue")

        agent = ReviewAgent("review-01", _config(), llm_provider=provider, approval_threshold=6)
        await agent.start()

        task = _review_task()
        result = await agent.execute_task(task)

        assert result.output_data["approved"] is True
        assert result.output_data["score"] == 6


# =============================================================================
# Tests: LLM Interaction
# =============================================================================
class TestReviewAgentLLMInteraction:
    """Tests for how the agent interacts with the LLM."""

    async def test_calls_generate_with_system(self) -> None:
        """Agent should call generate_with_system with review prompt."""
        provider = _provider()
        provider.queue_response(SAMPLE_REVIEW_RESPONSE)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task()
        await agent.execute_task(task)

        assert provider.call_count == 1
        call = provider.call_history[0]
        assert call["system_prompt"] == REVIEW_SYSTEM_PROMPT

    async def test_prompt_contains_code(self) -> None:
        """The review prompt should contain the code to review."""
        provider = _provider()
        provider.queue_response(SAMPLE_REVIEW_RESPONSE)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task(input_data={
            "code": "def fibonacci(n): pass",
            "language": "python",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "fibonacci" in call["prompt"]

    async def test_prompt_includes_criteria(self) -> None:
        """Review criteria should appear in the prompt."""
        provider = _provider()
        provider.queue_response(SAMPLE_REVIEW_RESPONSE)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task(input_data={
            "code": "code here",
            "review_criteria": ["security", "performance"],
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "security" in call["prompt"].lower()
        assert "performance" in call["prompt"].lower()


# =============================================================================
# Tests: Response Parsing
# =============================================================================
class TestReviewResponseParsing:
    """Tests for the _parse_review_response static method."""

    def test_extracts_score_from_standard_format(self) -> None:
        """Should extract score from 'Score: 8/10' format."""
        result = ReviewAgent._parse_review_response("Score: 8/10\nGood code.")
        assert result["score"] == 8

    def test_extracts_score_from_quality_format(self) -> None:
        """Should extract score from 'Quality: 7/10' format."""
        result = ReviewAgent._parse_review_response("Quality: 7/10")
        assert result["score"] == 7

    def test_default_score_when_not_found(self) -> None:
        """Should default to 7 when no score is found."""
        result = ReviewAgent._parse_review_response("This is a review with no score.")
        assert result["score"] == 7

    def test_extracts_findings(self) -> None:
        """Should extract findings from numbered list."""
        text = (
            "Findings\n"
            "1. Missing error handling\n"
            "2. No input validation\n"
            "\nRecommendations\n"
            "1. Add try-except blocks\n"
        )
        result = ReviewAgent._parse_review_response(text)
        assert len(result["findings"]) >= 1

    def test_extracts_recommendations(self) -> None:
        """Should extract recommendations from numbered list."""
        text = (
            "Findings\n"
            "1. Issue one\n"
            "\nRecommendations\n"
            "1. Add type hints\n"
            "2. Add logging\n"
            "\nVerdict: APPROVED"
        )
        result = ReviewAgent._parse_review_response(text)
        assert len(result["recommendations"]) >= 1

    def test_empty_text_returns_defaults(self) -> None:
        """Empty text should return default values."""
        result = ReviewAgent._parse_review_response("")
        assert result["score"] == 7
        assert result["findings"] == []
        assert result["recommendations"] == []


# =============================================================================
# Tests: Error Handling
# =============================================================================
class TestReviewAgentErrors:
    """Tests for error handling during review."""

    async def test_llm_failure_returns_failed_result(self) -> None:
        """LLM failure should return FAILED TaskResult (BaseAgent catches it)."""
        provider = _provider()
        provider.set_should_fail(True, "LLM rate limited")

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        assert "LLM rate limited" in result.error_message

    async def test_agent_returns_to_idle_after_failure(self) -> None:
        """Agent should return to IDLE after a task failure."""
        provider = _provider()
        provider.set_should_fail(True)

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = _review_task()
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE
        assert agent.state.error_count == 1


# =============================================================================
# Tests: Prompt Building (Static Method)
# =============================================================================
class TestReviewPromptBuilding:
    """Tests for the _build_review_prompt static method."""

    def test_basic_prompt(self) -> None:
        """Prompt should contain code and language."""
        prompt = ReviewAgent._build_review_prompt(
            code="def foo(): pass",
            language="python",
        )
        assert "def foo(): pass" in prompt
        assert "python" in prompt.lower()

    def test_prompt_with_context(self) -> None:
        """Prompt should include context when provided."""
        prompt = ReviewAgent._build_review_prompt(
            code="code here",
            language="python",
            context="This is a REST API endpoint",
        )
        assert "REST API" in prompt

    def test_prompt_with_specification(self) -> None:
        """Prompt should include specification when provided."""
        prompt = ReviewAgent._build_review_prompt(
            code="code here",
            language="python",
            specification="Build user authentication",
        )
        assert "user authentication" in prompt

    def test_prompt_with_criteria(self) -> None:
        """Prompt should list review criteria."""
        prompt = ReviewAgent._build_review_prompt(
            code="code here",
            language="python",
            review_criteria=["security", "performance", "readability"],
        )
        assert "security" in prompt.lower()
        assert "performance" in prompt.lower()
