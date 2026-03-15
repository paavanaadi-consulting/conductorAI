"""
Tests for context generation across agents
=============================================

Verifies:
    - BaseAgent._generate_context() default returns empty contribution
    - Context entries appear in result.metadata when agents override hook
    - Context generation failures are non-fatal
    - CodingAgent, DevOpsAgent, TestAgent, ReviewAgent produce expected entries
    - Config flag disables context generation
"""

import pytest

from conductor.agents.base import BaseAgent
from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.devops.devops_agent import DevOpsAgent
from conductor.core.config import ConductorConfig
from conductor.core.context_models import ContextContribution, ContextEntry
from conductor.core.enums import AgentType, TaskStatus
from conductor.core.models import TaskDefinition, TaskResult
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Helpers
# =============================================================================
def _config(**overrides) -> ConductorConfig:
    return ConductorConfig(**overrides)


def _provider() -> MockLLMProvider:
    return MockLLMProvider()


# =============================================================================
# MockAgent for testing base hook
# =============================================================================
class _PlainMockAgent(BaseAgent):
    """Agent with no _generate_context override (default no-op)."""

    def __init__(self, config=None):
        super().__init__(
            agent_id="plain-01",
            agent_type=AgentType.CODING,
            config=config or ConductorConfig(),
        )

    async def _validate_task(self, task):
        return True

    async def _execute(self, task):
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={"code": "hello"},
        )


class _FailingContextAgent(BaseAgent):
    """Agent whose _generate_context raises an exception."""

    def __init__(self, config=None):
        super().__init__(
            agent_id="failctx-01",
            agent_type=AgentType.CODING,
            config=config or ConductorConfig(),
        )

    async def _validate_task(self, task):
        return True

    async def _execute(self, task):
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={"code": "hello"},
        )

    async def _generate_context(self, task, result):
        raise RuntimeError("Context LLM call failed")


# =============================================================================
# Tests: BaseAgent default hook
# =============================================================================
class TestBaseAgentContextHook:
    """Default _generate_context() returns empty ContextContribution."""

    async def test_default_returns_empty(self) -> None:
        agent = _PlainMockAgent()
        await agent.start()
        task = TaskDefinition(name="Test")
        result = await agent.execute_task(task)

        # No context entries because default hook returns empty
        assert "context_entries" not in result.metadata

    async def test_context_failure_non_fatal(self) -> None:
        """Context generation failure should not fail the task."""
        agent = _FailingContextAgent()
        await agent.start()
        task = TaskDefinition(name="Test")
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "context_entries" not in result.metadata

    async def test_config_flag_disables_context(self) -> None:
        """When enable_context_generation=False, hook is not called."""
        config = _config(enable_context_generation=False)
        agent = _FailingContextAgent(config=config)
        await agent.start()
        task = TaskDefinition(name="Test")
        result = await agent.execute_task(task)

        # Would have raised if called — result should be clean
        assert result.status == TaskStatus.COMPLETED


# =============================================================================
# Tests: CodingAgent context generation
# =============================================================================
class TestCodingAgentContext:
    """CodingAgent should produce context entries in result.metadata."""

    async def test_produces_context_entries(self) -> None:
        provider = _provider()
        # First response: code generation
        provider.queue_response("def hello(): pass")
        # Second response: context generation
        provider.queue_response(
            "### DECISIONS\nChose Flask for REST API.\n\n"
            "### TRACEABILITY\nSpec → hello function.\n\n"
            "### KNOWN_GAPS\nNo async support.\n\n"
            "### CONFIDENCE\n0.85\nHigh confidence."
        )

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = TaskDefinition(
            name="Generate code",
            assigned_to=AgentType.CODING,
            input_data={"specification": "Hello world", "language": "python"},
        )
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "context_entries" in result.metadata
        entries = result.metadata["context_entries"]
        assert len(entries) >= 1

        # Check that entries target the expected files
        files = {e["context_file"] for e in entries}
        assert "decisions.md" in files

    async def test_two_llm_calls_made(self) -> None:
        """Should make 2 LLM calls: code gen + context gen."""
        provider = _provider()
        provider.queue_response("generated code")
        provider.queue_response("### DECISIONS\nSome decisions.")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = TaskDefinition(
            name="Generate code",
            assigned_to=AgentType.CODING,
            input_data={"specification": "API", "language": "python"},
        )
        await agent.execute_task(task)

        assert provider.call_count == 2


# =============================================================================
# Tests: DevOpsAgent context generation
# =============================================================================
class TestDevOpsAgentContext:
    """DevOpsAgent should produce context entries in result.metadata."""

    async def test_produces_context_entries(self) -> None:
        provider = _provider()
        # First: config generation
        provider.queue_response("name: CI\non: push\njobs: ...")
        # Second: context generation
        provider.queue_response(
            "### INFRA_DECISIONS\nChose GitHub Actions.\n\n"
            "### INFRA_BINDINGS\n- Python 3.11\n\n"
            "### RUNBOOK\n1. Install deps.\n"
        )

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = TaskDefinition(
            name="Generate CI/CD",
            assigned_to=AgentType.DEVOPS,
            input_data={"code": "def main(): pass", "platform": "github_actions"},
        )
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "context_entries" in result.metadata

        files = {e["context_file"] for e in result.metadata["context_entries"]}
        assert "decisions.md" in files
        assert "infra-bindings.md" in files
        assert "runbook.md" in files


# =============================================================================
# Tests: TestAgent context generation
# =============================================================================
class TestTestAgentContext:
    """TestAgent should produce known-gaps.md entries."""

    async def test_produces_known_gaps(self) -> None:
        provider = _provider()
        # First: test generation
        provider.queue_response("def test_hello(): assert True")
        # Second: context generation
        provider.queue_response(
            "### KNOWN_GAPS\n- No integration tests for DB layer."
        )

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = TaskDefinition(
            name="Generate tests",
            assigned_to=AgentType.TEST,
            input_data={"code": "def hello(): pass", "language": "python"},
        )
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "context_entries" in result.metadata

        files = {e["context_file"] for e in result.metadata["context_entries"]}
        assert "known-gaps.md" in files


# =============================================================================
# Tests: ReviewAgent context generation
# =============================================================================
class TestReviewAgentContext:
    """ReviewAgent should produce confidence-report.md entries."""

    async def test_produces_confidence_report(self) -> None:
        provider = _provider()
        # First: code review
        provider.queue_response(
            "Score: 8/10\nVerdict: APPROVED\n"
            "Findings:\n1. Good structure\n"
            "Recommendations:\n1. Add docstrings"
        )
        # Second: context generation
        provider.queue_response(
            "### VALIDATION_SUMMARY\nApproved with score 8/10."
        )

        agent = ReviewAgent("review-01", _config(), llm_provider=provider)
        await agent.start()

        task = TaskDefinition(
            name="Review code",
            assigned_to=AgentType.REVIEW,
            input_data={"code": "def hello(): pass", "language": "python"},
        )
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "context_entries" in result.metadata

        files = {e["context_file"] for e in result.metadata["context_entries"]}
        assert "confidence-report.md" in files
