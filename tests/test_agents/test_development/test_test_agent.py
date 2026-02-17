"""
Tests for conductor.agents.development.test_agent
=====================================================

These tests verify the TestAgent — the final agent in the DEVELOPMENT phase
that creates comprehensive test suites for source code using an LLM.

What's Being Tested:
    - Agent initialization (identity, type, LLM provider)
    - Task validation (code required, non-empty)
    - Test generation (prompt building, LLM call, result packaging)
    - Output structure (tests, test_framework, language, LLM metadata)
    - Test data integration (pre-generated fixtures from TestDataAgent)
    - Error handling (LLM failure, missing inputs)
    - Startup hook (LLM provider validation)

All tests use MockLLMProvider — no real API calls.
"""

import pytest

from conductor.agents.development.test_agent import TestAgent, TEST_SYSTEM_PROMPT
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


SAMPLE_TEST_SUITE_RESPONSE = """import pytest


class TestAdd:
    def test_positive_numbers(self):
        assert add(1, 2) == 3

    def test_zero(self):
        assert add(0, 0) == 0

    def test_negative_numbers(self):
        assert add(-1, -2) == -3

    def test_mixed_signs(self):
        assert add(-1, 1) == 0

    def test_large_numbers(self):
        assert add(1000000, 2000000) == 3000000
"""


def _test_agent_task(**overrides) -> TaskDefinition:
    """Create a standard test generation task with optional overrides."""
    defaults = {
        "name": "Generate Tests",
        "assigned_to": AgentType.TEST,
        "input_data": {
            "code": "def add(a, b):\n    return a + b",
            "language": "python",
        },
    }
    defaults.update(overrides)
    return TaskDefinition(**defaults)


# =============================================================================
# Tests: Agent Initialization
# =============================================================================
class TestTestAgentInit:
    """Tests for TestAgent initialization."""

    def test_creates_with_correct_type(self) -> None:
        """TestAgent should have AgentType.TEST."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider())
        assert agent.agent_type == AgentType.TEST

    def test_creates_with_identity(self) -> None:
        """Agent should have the correct ID and name."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider())
        assert agent.agent_id == "test-01"
        assert "TestAgent" in agent.identity.name

    def test_custom_name(self) -> None:
        """Custom name should override the default."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider(), name="Unit Tester")
        assert agent.identity.name == "Unit Tester"

    def test_llm_provider_accessible(self) -> None:
        """LLM provider should be accessible via property."""
        provider = _provider()
        agent = TestAgent("test-01", _config(), llm_provider=provider)
        assert agent.llm_provider is provider


# =============================================================================
# Tests: Task Validation
# =============================================================================
class TestTestAgentValidation:
    """Tests for _validate_task."""

    async def test_valid_task_passes(self) -> None:
        """Task with code should pass validation."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider())
        task = _test_agent_task()
        assert await agent._validate_task(task) is True

    async def test_missing_code_fails(self) -> None:
        """Task without code should fail validation."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider())
        task = _test_agent_task(input_data={"language": "python"})
        assert await agent._validate_task(task) is False

    async def test_empty_code_fails(self) -> None:
        """Task with empty code should fail validation."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider())
        task = _test_agent_task(input_data={"code": ""})
        assert await agent._validate_task(task) is False

    async def test_whitespace_code_fails(self) -> None:
        """Task with whitespace-only code should fail."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider())
        task = _test_agent_task(input_data={"code": "   "})
        assert await agent._validate_task(task) is False

    async def test_validation_failure_raises_agent_error(self) -> None:
        """Invalid task should raise AgentError through execute_task."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider())
        await agent.start()

        task = _test_agent_task(input_data={"language": "python"})
        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(task)
        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"


# =============================================================================
# Tests: Test Suite Generation
# =============================================================================
class TestTestAgentExecution:
    """Tests for _execute (test suite generation)."""

    async def test_generates_tests_with_defaults(self) -> None:
        """Agent should generate tests and return structured result."""
        provider = _provider()
        provider.queue_response(SAMPLE_TEST_SUITE_RESPONSE)

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "test-01"
        assert "tests" in result.output_data
        assert result.output_data["tests"] == SAMPLE_TEST_SUITE_RESPONSE

    async def test_output_includes_test_framework(self) -> None:
        """Result should include the test framework used."""
        provider = _provider()
        provider.queue_response("test code")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task()
        result = await agent.execute_task(task)

        assert result.output_data["test_framework"] == "pytest"

    async def test_output_includes_language(self) -> None:
        """Result should include the target language."""
        provider = _provider()
        provider.queue_response("test code")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task()
        result = await agent.execute_task(task)

        assert result.output_data["language"] == "python"

    async def test_output_includes_llm_metadata(self) -> None:
        """Result should include LLM model and usage stats."""
        provider = _provider()
        provider.queue_response("test code")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task()
        result = await agent.execute_task(task)

        assert "llm_model" in result.output_data
        assert "llm_usage" in result.output_data
        assert isinstance(result.output_data["llm_usage"], dict)

    async def test_custom_test_framework(self) -> None:
        """Agent should use the specified test framework."""
        provider = _provider()
        provider.queue_response("describe('add', () => { ... })")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task(input_data={
            "code": "function add(a, b) { return a + b; }",
            "language": "javascript",
            "test_framework": "jest",
        })
        result = await agent.execute_task(task)

        assert result.output_data["test_framework"] == "jest"
        assert result.output_data["language"] == "javascript"

    async def test_with_test_data(self) -> None:
        """Agent should incorporate pre-generated test data."""
        provider = _provider()
        provider.queue_response("tests using fixtures")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task(input_data={
            "code": "def add(a, b): return a + b",
            "test_data": "VALID_INPUTS = [(1, 2, 3), (0, 0, 0)]",
        })
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        # Verify test data was sent to LLM
        call = provider.call_history[0]
        assert "VALID_INPUTS" in call["prompt"]


# =============================================================================
# Tests: LLM Interaction
# =============================================================================
class TestTestAgentLLMInteraction:
    """Tests for how the agent interacts with the LLM provider."""

    async def test_calls_generate_with_system(self) -> None:
        """Agent should call generate_with_system (not plain generate)."""
        provider = _provider()
        provider.queue_response("generated tests")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task()
        await agent.execute_task(task)

        assert provider.call_count == 1
        call = provider.call_history[0]
        assert call["system_prompt"] is not None
        assert call["system_prompt"] == TEST_SYSTEM_PROMPT

    async def test_prompt_contains_code(self) -> None:
        """The user prompt should contain the source code."""
        provider = _provider()
        provider.queue_response("tests")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task(input_data={
            "code": "def binary_search(arr, target): pass",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "binary_search" in call["prompt"]

    async def test_prompt_contains_framework(self) -> None:
        """The prompt should mention the test framework."""
        provider = _provider()
        provider.queue_response("tests")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task(input_data={
            "code": "code here",
            "test_framework": "unittest",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "unittest" in call["prompt"].lower()

    async def test_prompt_includes_test_data(self) -> None:
        """If test data is provided, it should appear in the prompt."""
        provider = _provider()
        provider.queue_response("tests")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        test_fixtures = "EDGE_CASES = [(0, 0, 0), (-1, 1, 0)]"
        task = _test_agent_task(input_data={
            "code": "def add(a, b): return a + b",
            "test_data": test_fixtures,
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "EDGE_CASES" in call["prompt"]


# =============================================================================
# Tests: Error Handling
# =============================================================================
class TestTestAgentErrors:
    """Tests for error handling during test generation."""

    async def test_llm_failure_returns_failed_result(self) -> None:
        """If the LLM fails, agent should return a FAILED TaskResult.

        BaseAgent catches RuntimeError and converts to FAILED result.
        """
        provider = _provider()
        provider.set_should_fail(True, "LLM service unavailable")

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        assert "LLM service unavailable" in result.error_message

    async def test_agent_returns_to_idle_after_failure(self) -> None:
        """Agent should return to IDLE after a task failure."""
        provider = _provider()
        provider.set_should_fail(True)

        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_agent_task()
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE
        assert agent.state.error_count == 1


# =============================================================================
# Tests: Startup Hook
# =============================================================================
class TestTestAgentStartup:
    """Tests for the _on_start lifecycle hook."""

    async def test_start_validates_provider(self) -> None:
        """start() should validate the LLM provider."""
        provider = _provider()
        agent = TestAgent("test-01", _config(), llm_provider=provider)
        await agent.start()

        assert agent.status == AgentStatus.IDLE

    async def test_start_sets_idle(self) -> None:
        """After start(), agent should be IDLE and ready."""
        agent = TestAgent("test-01", _config(), llm_provider=_provider())
        await agent.start()
        assert agent.status == AgentStatus.IDLE


# =============================================================================
# Tests: Prompt Building (Static Method)
# =============================================================================
class TestTestAgentPromptBuilding:
    """Tests for the _build_user_prompt static method."""

    def test_basic_prompt(self) -> None:
        """Prompt should contain code and language."""
        prompt = TestAgent._build_user_prompt(
            code="def add(a, b): return a + b",
            language="python",
        )
        assert "add" in prompt
        assert "python" in prompt.lower()

    def test_prompt_includes_framework(self) -> None:
        """Prompt should include the test framework."""
        prompt = TestAgent._build_user_prompt(
            code="code here",
            language="python",
            test_framework="unittest",
        )
        assert "unittest" in prompt.lower()

    def test_prompt_with_test_data(self) -> None:
        """Prompt should include test data when provided."""
        prompt = TestAgent._build_user_prompt(
            code="code here",
            language="python",
            test_data="FIXTURES = [(1, 2, 3)]",
        )
        assert "FIXTURES" in prompt

    def test_prompt_without_test_data(self) -> None:
        """Prompt should not include test data section when not provided."""
        prompt = TestAgent._build_user_prompt(
            code="code here",
            language="python",
        )
        # Should not contain a test data section header
        assert "Test Data" not in prompt or "Fixtures" not in prompt

    def test_prompt_includes_requirements(self) -> None:
        """Prompt should include testing requirements."""
        prompt = TestAgent._build_user_prompt(
            code="code here",
            language="python",
        )
        assert "edge case" in prompt.lower()
        assert "error handling" in prompt.lower()
