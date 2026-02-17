"""
Tests for conductor.agents.monitoring.monitor_agent
======================================================

These tests verify the MonitorAgent — the feedback generator that analyzes
deployment results and produces structured recommendations for the
development phase.

What's Being Tested:
    - Agent initialization (identity, type, LLM provider)
    - Task validation (deployment_result required, non-empty)
    - Monitoring execution (prompt building, LLM call, result packaging)
    - Output structure (analysis, has_issues, severity, issues, recommendations)
    - Response parsing (severity extraction, issues parsing, feedback extraction)
    - Feedback loop integration (has_issues triggers development re-run)
    - Error handling (LLM failure, missing inputs)
    - Startup hook (LLM provider validation)

All tests use MockLLMProvider — no real API calls.
"""

import pytest

from conductor.agents.monitoring.monitor_agent import MonitorAgent, MONITOR_SYSTEM_PROMPT
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


# --- Sample LLM responses for different scenarios ---

HEALTHY_DEPLOYMENT_RESPONSE = """## Severity: none

## Issues Found
1. No issues found

## Recommendations
1. No recommendations

## Feedback for Development
No action needed
"""

ISSUES_FOUND_RESPONSE = """## Severity: high

## Issues Found
1. Memory usage exceeds 85% threshold under load
2. API response time degraded to 2.5s (SLA is 1s)
3. Error rate increased to 3.2% after deployment

## Recommendations
1. Optimize database queries causing memory pressure
2. Add connection pooling for external API calls
3. Investigate error logs for root cause of failures

## Feedback for Development
Memory usage and API response time are critical concerns. The development team
should focus on optimizing database queries and adding connection pooling. The
3.2% error rate needs immediate investigation.
"""

CRITICAL_RESPONSE = """## Severity: critical

## Issues Found
1. Application crash loop detected — pods restarting every 30 seconds
2. Database connection pool exhausted

## Recommendations
1. Rollback to previous version immediately
2. Fix database connection leak in the connection manager

## Feedback for Development
Critical: Application is in a crash loop due to database connection leak.
Immediate rollback required. Development must fix the connection pool management.
"""


def _monitor_task(**overrides) -> TaskDefinition:
    """Create a standard monitoring task with optional overrides."""
    defaults = {
        "name": "Monitor Deployment",
        "assigned_to": AgentType.MONITOR,
        "input_data": {
            "deployment_result": "Deployed v2.1.0 to production. 3 pods running. Health check passed.",
        },
    }
    defaults.update(overrides)
    return TaskDefinition(**defaults)


# =============================================================================
# Tests: Agent Initialization
# =============================================================================
class TestMonitorAgentInit:
    """Tests for MonitorAgent initialization."""

    def test_creates_with_correct_type(self) -> None:
        """MonitorAgent should have AgentType.MONITOR."""
        agent = MonitorAgent("monitor-01", _config(), llm_provider=_provider())
        assert agent.agent_type == AgentType.MONITOR

    def test_creates_with_identity(self) -> None:
        """Agent should have the correct ID and name."""
        agent = MonitorAgent("monitor-01", _config(), llm_provider=_provider())
        assert agent.agent_id == "monitor-01"
        assert "MonitorAgent" in agent.identity.name

    def test_custom_name(self) -> None:
        """Custom name should override the default."""
        agent = MonitorAgent(
            "monitor-01", _config(), llm_provider=_provider(), name="Primary Monitor"
        )
        assert agent.identity.name == "Primary Monitor"

    def test_llm_provider_accessible(self) -> None:
        """LLM provider should be accessible via property."""
        provider = _provider()
        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        assert agent.llm_provider is provider


# =============================================================================
# Tests: Task Validation
# =============================================================================
class TestMonitorAgentValidation:
    """Tests for _validate_task."""

    async def test_valid_task_passes(self) -> None:
        """Task with deployment_result should pass validation."""
        agent = MonitorAgent("monitor-01", _config(), llm_provider=_provider())
        task = _monitor_task()
        assert await agent._validate_task(task) is True

    async def test_missing_deployment_result_fails(self) -> None:
        """Task without deployment_result should fail validation."""
        agent = MonitorAgent("monitor-01", _config(), llm_provider=_provider())
        task = _monitor_task(input_data={"metrics": "cpu: 50%"})
        assert await agent._validate_task(task) is False

    async def test_empty_deployment_result_fails(self) -> None:
        """Task with empty deployment_result should fail validation."""
        agent = MonitorAgent("monitor-01", _config(), llm_provider=_provider())
        task = _monitor_task(input_data={"deployment_result": ""})
        assert await agent._validate_task(task) is False

    async def test_whitespace_deployment_result_fails(self) -> None:
        """Task with whitespace-only deployment_result should fail."""
        agent = MonitorAgent("monitor-01", _config(), llm_provider=_provider())
        task = _monitor_task(input_data={"deployment_result": "   "})
        assert await agent._validate_task(task) is False

    async def test_validation_failure_raises_agent_error(self) -> None:
        """Invalid task should raise AgentError through execute_task."""
        agent = MonitorAgent("monitor-01", _config(), llm_provider=_provider())
        await agent.start()

        task = _monitor_task(input_data={"metrics": "cpu: 50%"})
        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(task)
        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"


# =============================================================================
# Tests: Monitoring Execution
# =============================================================================
class TestMonitorAgentExecution:
    """Tests for _execute (monitoring execution)."""

    async def test_healthy_deployment_no_issues(self) -> None:
        """Healthy deployment should result in has_issues=False."""
        provider = _provider()
        provider.queue_response(HEALTHY_DEPLOYMENT_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "monitor-01"
        assert result.output_data["has_issues"] is False
        assert result.output_data["severity"] == "none"

    async def test_deployment_with_issues(self) -> None:
        """Deployment with issues should result in has_issues=True."""
        provider = _provider()
        provider.queue_response(ISSUES_FOUND_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.output_data["has_issues"] is True
        assert result.output_data["severity"] == "high"
        assert len(result.output_data["issues"]) >= 1
        assert len(result.output_data["recommendations"]) >= 1

    async def test_critical_deployment(self) -> None:
        """Critical deployment should have severity=critical."""
        provider = _provider()
        provider.queue_response(CRITICAL_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        result = await agent.execute_task(task)

        assert result.output_data["severity"] == "critical"
        assert result.output_data["has_issues"] is True

    async def test_output_includes_analysis(self) -> None:
        """Result should include the full analysis text."""
        provider = _provider()
        provider.queue_response(ISSUES_FOUND_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        result = await agent.execute_task(task)

        assert "analysis" in result.output_data
        assert len(result.output_data["analysis"]) > 0

    async def test_output_includes_feedback_for_development(self) -> None:
        """Result should include feedback for the development team."""
        provider = _provider()
        provider.queue_response(ISSUES_FOUND_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        result = await agent.execute_task(task)

        assert "feedback_for_development" in result.output_data
        assert len(result.output_data["feedback_for_development"]) > 0

    async def test_output_includes_llm_metadata(self) -> None:
        """Result should include LLM model and usage stats."""
        provider = _provider()
        provider.queue_response(HEALTHY_DEPLOYMENT_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        result = await agent.execute_task(task)

        assert "llm_model" in result.output_data
        assert "llm_usage" in result.output_data
        assert isinstance(result.output_data["llm_usage"], dict)


# =============================================================================
# Tests: LLM Interaction
# =============================================================================
class TestMonitorAgentLLMInteraction:
    """Tests for how the agent interacts with the LLM provider."""

    async def test_calls_generate_with_system(self) -> None:
        """Agent should call generate_with_system with monitor prompt."""
        provider = _provider()
        provider.queue_response(HEALTHY_DEPLOYMENT_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        await agent.execute_task(task)

        assert provider.call_count == 1
        call = provider.call_history[0]
        assert call["system_prompt"] == MONITOR_SYSTEM_PROMPT

    async def test_prompt_contains_deployment_result(self) -> None:
        """The user prompt should contain the deployment result."""
        provider = _provider()
        provider.queue_response(HEALTHY_DEPLOYMENT_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task(input_data={
            "deployment_result": "Deployed v3.0.0 to staging. All containers running.",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "v3.0.0" in call["prompt"]

    async def test_prompt_includes_metrics(self) -> None:
        """If metrics are provided, they should appear in the prompt."""
        provider = _provider()
        provider.queue_response(HEALTHY_DEPLOYMENT_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task(input_data={
            "deployment_result": "Deployed successfully",
            "metrics": "CPU: 75%, Memory: 2.1GB, p99 latency: 450ms",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "p99" in call["prompt"]

    async def test_prompt_includes_logs(self) -> None:
        """If logs are provided, they should appear in the prompt."""
        provider = _provider()
        provider.queue_response(HEALTHY_DEPLOYMENT_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task(input_data={
            "deployment_result": "Deployed successfully",
            "logs": "ERROR: Connection timeout to database at 14:32:01",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "Connection timeout" in call["prompt"]

    async def test_prompt_includes_previous_feedback(self) -> None:
        """If previous feedback is provided, it should appear in the prompt."""
        provider = _provider()
        provider.queue_response(HEALTHY_DEPLOYMENT_RESPONSE)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task(input_data={
            "deployment_result": "Re-deployed with fixes",
            "previous_feedback": "Memory leak in connection pool needs fixing",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "Memory leak" in call["prompt"]


# =============================================================================
# Tests: Response Parsing
# =============================================================================
class TestMonitorResponseParsing:
    """Tests for the _parse_monitor_response static method."""

    def test_extracts_severity_none(self) -> None:
        """Should extract severity: none from response."""
        result = MonitorAgent._parse_monitor_response(HEALTHY_DEPLOYMENT_RESPONSE)
        assert result["severity"] == "none"

    def test_extracts_severity_high(self) -> None:
        """Should extract severity: high from response."""
        result = MonitorAgent._parse_monitor_response(ISSUES_FOUND_RESPONSE)
        assert result["severity"] == "high"

    def test_extracts_severity_critical(self) -> None:
        """Should extract severity: critical from response."""
        result = MonitorAgent._parse_monitor_response(CRITICAL_RESPONSE)
        assert result["severity"] == "critical"

    def test_extracts_issues(self) -> None:
        """Should extract issues from numbered list."""
        result = MonitorAgent._parse_monitor_response(ISSUES_FOUND_RESPONSE)
        assert len(result["issues"]) == 3
        assert "Memory usage" in result["issues"][0]

    def test_filters_no_issues_placeholder(self) -> None:
        """Should filter out 'No issues found' placeholder."""
        result = MonitorAgent._parse_monitor_response(HEALTHY_DEPLOYMENT_RESPONSE)
        assert len(result["issues"]) == 0

    def test_extracts_recommendations(self) -> None:
        """Should extract recommendations from numbered list."""
        result = MonitorAgent._parse_monitor_response(ISSUES_FOUND_RESPONSE)
        assert len(result["recommendations"]) == 3

    def test_filters_no_recommendations_placeholder(self) -> None:
        """Should filter out 'No recommendations' placeholder."""
        result = MonitorAgent._parse_monitor_response(HEALTHY_DEPLOYMENT_RESPONSE)
        assert len(result["recommendations"]) == 0

    def test_extracts_feedback_for_development(self) -> None:
        """Should extract feedback for development section."""
        result = MonitorAgent._parse_monitor_response(ISSUES_FOUND_RESPONSE)
        assert len(result["feedback_for_development"]) > 0
        assert "database queries" in result["feedback_for_development"].lower()

    def test_no_feedback_when_healthy(self) -> None:
        """Should have empty feedback when no action needed."""
        result = MonitorAgent._parse_monitor_response(HEALTHY_DEPLOYMENT_RESPONSE)
        assert result["feedback_for_development"] == ""

    def test_has_issues_false_for_healthy(self) -> None:
        """has_issues should be False when severity is none."""
        result = MonitorAgent._parse_monitor_response(HEALTHY_DEPLOYMENT_RESPONSE)
        assert result["has_issues"] is False

    def test_has_issues_true_for_issues(self) -> None:
        """has_issues should be True when severity is not none."""
        result = MonitorAgent._parse_monitor_response(ISSUES_FOUND_RESPONSE)
        assert result["has_issues"] is True

    def test_default_severity_when_not_found(self) -> None:
        """Should default to 'none' when no severity found."""
        result = MonitorAgent._parse_monitor_response("Just a plain response with no format.")
        assert result["severity"] == "none"

    def test_empty_text_returns_defaults(self) -> None:
        """Empty text should return safe defaults."""
        result = MonitorAgent._parse_monitor_response("")
        assert result["severity"] == "none"
        assert result["issues"] == []
        assert result["recommendations"] == []
        assert result["has_issues"] is False


# =============================================================================
# Tests: Error Handling
# =============================================================================
class TestMonitorAgentErrors:
    """Tests for error handling during monitoring."""

    async def test_llm_failure_returns_failed_result(self) -> None:
        """If the LLM fails, agent should return a FAILED TaskResult."""
        provider = _provider()
        provider.set_should_fail(True, "LLM service unavailable")

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        assert "LLM service unavailable" in result.error_message

    async def test_agent_returns_to_idle_after_failure(self) -> None:
        """Agent should return to IDLE after a task failure."""
        provider = _provider()
        provider.set_should_fail(True)

        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        task = _monitor_task()
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE
        assert agent.state.error_count == 1


# =============================================================================
# Tests: Startup Hook
# =============================================================================
class TestMonitorAgentStartup:
    """Tests for the _on_start lifecycle hook."""

    async def test_start_validates_provider(self) -> None:
        """start() should validate the LLM provider."""
        provider = _provider()
        agent = MonitorAgent("monitor-01", _config(), llm_provider=provider)
        await agent.start()

        assert agent.status == AgentStatus.IDLE

    async def test_start_sets_idle(self) -> None:
        """After start(), agent should be IDLE and ready."""
        agent = MonitorAgent("monitor-01", _config(), llm_provider=_provider())
        await agent.start()
        assert agent.status == AgentStatus.IDLE


# =============================================================================
# Tests: Prompt Building (Static Method)
# =============================================================================
class TestMonitorAgentPromptBuilding:
    """Tests for the _build_user_prompt static method."""

    def test_basic_prompt(self) -> None:
        """Prompt should contain deployment result."""
        prompt = MonitorAgent._build_user_prompt(
            deployment_result="Deployed to production successfully",
        )
        assert "Deployed to production" in prompt

    def test_prompt_with_metrics(self) -> None:
        """Prompt should include metrics when provided."""
        prompt = MonitorAgent._build_user_prompt(
            deployment_result="Deployed OK",
            metrics="CPU: 80%, Memory: 3GB",
        )
        assert "CPU: 80%" in prompt

    def test_prompt_with_logs(self) -> None:
        """Prompt should include logs when provided."""
        prompt = MonitorAgent._build_user_prompt(
            deployment_result="Deployed OK",
            logs="ERROR: Timeout at 14:32",
        )
        assert "Timeout" in prompt

    def test_prompt_with_previous_feedback(self) -> None:
        """Prompt should include previous feedback when provided."""
        prompt = MonitorAgent._build_user_prompt(
            deployment_result="Re-deployed",
            previous_feedback="Fix the memory leak",
        )
        assert "memory leak" in prompt

    def test_prompt_includes_analysis_requirements(self) -> None:
        """Prompt should include analysis requirements."""
        prompt = MonitorAgent._build_user_prompt(
            deployment_result="Deployed",
        )
        assert "anomalies" in prompt.lower()
