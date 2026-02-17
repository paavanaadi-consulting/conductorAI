"""
Tests for conductor.agents.development.test_data_agent
========================================================

These tests verify the TestDataAgent — a specialized agent that generates
test data and fixtures for source code using an LLM.

What's Being Tested:
    - Agent initialization (identity, type, LLM provider)
    - Task validation (code required, non-empty)
    - Test data generation (prompt building, LLM call, result packaging)
    - Output structure (test_data, format, language, LLM metadata)
    - Error handling (LLM failure, missing inputs)
    - Startup hook (LLM provider validation)

All tests use MockLLMProvider — no real API calls.
"""

import pytest

from conductor.agents.development.test_data_agent import TestDataAgent, TEST_DATA_SYSTEM_PROMPT
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


SAMPLE_TEST_DATA_RESPONSE = """# Test Fixtures for add(a, b)

## Normal Cases
VALID_INPUTS = [
    (1, 2, 3),
    (0, 0, 0),
    (100, 200, 300),
    (-5, 5, 0),
]

## Edge Cases
EDGE_CASES = [
    (0, 0, 0),
    (-1, -1, -2),
    (2**31 - 1, 1, 2**31),
    (float('inf'), 1, float('inf')),
]

## Error Cases
ERROR_INPUTS = [
    (None, 1),
    ("string", 1),
    ([], 1),
]
"""


def _test_data_task(**overrides) -> TaskDefinition:
    """Create a standard test data task with optional overrides."""
    defaults = {
        "name": "Generate Test Data",
        "assigned_to": AgentType.TEST_DATA,
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
class TestTestDataAgentInit:
    """Tests for TestDataAgent initialization."""

    def test_creates_with_correct_type(self) -> None:
        """TestDataAgent should have AgentType.TEST_DATA."""
        agent = TestDataAgent("test-data-01", _config(), llm_provider=_provider())
        assert agent.agent_type == AgentType.TEST_DATA

    def test_creates_with_identity(self) -> None:
        """Agent should have the correct ID and name."""
        agent = TestDataAgent("test-data-01", _config(), llm_provider=_provider())
        assert agent.agent_id == "test-data-01"
        assert "TestDataAgent" in agent.identity.name

    def test_custom_name(self) -> None:
        """Custom name should override the default."""
        agent = TestDataAgent(
            "test-data-01", _config(), llm_provider=_provider(), name="Fixture Generator"
        )
        assert agent.identity.name == "Fixture Generator"

    def test_llm_provider_accessible(self) -> None:
        """LLM provider should be accessible via property."""
        provider = _provider()
        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        assert agent.llm_provider is provider


# =============================================================================
# Tests: Task Validation
# =============================================================================
class TestTestDataAgentValidation:
    """Tests for _validate_task."""

    async def test_valid_task_passes(self) -> None:
        """Task with code should pass validation."""
        agent = TestDataAgent("test-data-01", _config(), llm_provider=_provider())
        task = _test_data_task()
        assert await agent._validate_task(task) is True

    async def test_missing_code_fails(self) -> None:
        """Task without code should fail validation."""
        agent = TestDataAgent("test-data-01", _config(), llm_provider=_provider())
        task = _test_data_task(input_data={"language": "python"})
        assert await agent._validate_task(task) is False

    async def test_empty_code_fails(self) -> None:
        """Task with empty code should fail validation."""
        agent = TestDataAgent("test-data-01", _config(), llm_provider=_provider())
        task = _test_data_task(input_data={"code": ""})
        assert await agent._validate_task(task) is False

    async def test_whitespace_code_fails(self) -> None:
        """Task with whitespace-only code should fail."""
        agent = TestDataAgent("test-data-01", _config(), llm_provider=_provider())
        task = _test_data_task(input_data={"code": "   "})
        assert await agent._validate_task(task) is False

    async def test_validation_failure_raises_agent_error(self) -> None:
        """Invalid task should raise AgentError through execute_task."""
        agent = TestDataAgent("test-data-01", _config(), llm_provider=_provider())
        await agent.start()

        task = _test_data_task(input_data={"language": "python"})
        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(task)
        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"


# =============================================================================
# Tests: Test Data Generation
# =============================================================================
class TestTestDataAgentExecution:
    """Tests for _execute (test data generation)."""

    async def test_generates_test_data_with_defaults(self) -> None:
        """Agent should generate test data and return structured result."""
        provider = _provider()
        provider.queue_response(SAMPLE_TEST_DATA_RESPONSE)

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "test-data-01"
        assert "test_data" in result.output_data
        assert result.output_data["test_data"] == SAMPLE_TEST_DATA_RESPONSE

    async def test_output_includes_format(self) -> None:
        """Result should include the data format used."""
        provider = _provider()
        provider.queue_response("fixtures here")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task()
        result = await agent.execute_task(task)

        assert result.output_data["format"] == "fixtures"

    async def test_output_includes_language(self) -> None:
        """Result should include the target language."""
        provider = _provider()
        provider.queue_response("test data")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task()
        result = await agent.execute_task(task)

        assert result.output_data["language"] == "python"

    async def test_output_includes_llm_metadata(self) -> None:
        """Result should include LLM model and usage stats."""
        provider = _provider()
        provider.queue_response("test data")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task()
        result = await agent.execute_task(task)

        assert "llm_model" in result.output_data
        assert "llm_usage" in result.output_data
        assert isinstance(result.output_data["llm_usage"], dict)

    async def test_custom_data_format(self) -> None:
        """Agent should use the specified data format."""
        provider = _provider()
        provider.queue_response("{\"data\": [1, 2, 3]}")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task(input_data={
            "code": "def process(data): pass",
            "data_format": "json",
        })
        result = await agent.execute_task(task)

        assert result.output_data["format"] == "json"

    async def test_custom_language(self) -> None:
        """Agent should use the specified language."""
        provider = _provider()
        provider.queue_response("const testData = [];")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task(input_data={
            "code": "function add(a, b) { return a + b; }",
            "language": "javascript",
        })
        result = await agent.execute_task(task)

        assert result.output_data["language"] == "javascript"


# =============================================================================
# Tests: LLM Interaction
# =============================================================================
class TestTestDataAgentLLMInteraction:
    """Tests for how the agent interacts with the LLM provider."""

    async def test_calls_generate_with_system(self) -> None:
        """Agent should call generate_with_system (not plain generate)."""
        provider = _provider()
        provider.queue_response("generated test data")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task()
        await agent.execute_task(task)

        assert provider.call_count == 1
        call = provider.call_history[0]
        assert call["system_prompt"] is not None
        assert call["system_prompt"] == TEST_DATA_SYSTEM_PROMPT

    async def test_prompt_contains_code(self) -> None:
        """The user prompt should contain the source code."""
        provider = _provider()
        provider.queue_response("test data")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task(input_data={
            "code": "def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "fibonacci" in call["prompt"]

    async def test_prompt_contains_format(self) -> None:
        """The prompt should mention the data format."""
        provider = _provider()
        provider.queue_response("test data")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task(input_data={
            "code": "def add(a, b): return a + b",
            "data_format": "parametrize",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "parametrize" in call["prompt"].lower()

    async def test_prompt_contains_language(self) -> None:
        """The prompt should mention the target language."""
        provider = _provider()
        provider.queue_response("test data")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task(input_data={
            "code": "func Add(a, b int) int { return a + b }",
            "language": "go",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "go" in call["prompt"].lower()


# =============================================================================
# Tests: Error Handling
# =============================================================================
class TestTestDataAgentErrors:
    """Tests for error handling during test data generation."""

    async def test_llm_failure_returns_failed_result(self) -> None:
        """If the LLM fails, agent should return a FAILED TaskResult.

        BaseAgent catches RuntimeError and converts to FAILED result.
        """
        provider = _provider()
        provider.set_should_fail(True, "LLM service unavailable")

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        assert "LLM service unavailable" in result.error_message

    async def test_agent_returns_to_idle_after_failure(self) -> None:
        """Agent should return to IDLE after a task failure."""
        provider = _provider()
        provider.set_should_fail(True)

        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        task = _test_data_task()
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE
        assert agent.state.error_count == 1


# =============================================================================
# Tests: Startup Hook
# =============================================================================
class TestTestDataAgentStartup:
    """Tests for the _on_start lifecycle hook."""

    async def test_start_validates_provider(self) -> None:
        """start() should validate the LLM provider."""
        provider = _provider()
        agent = TestDataAgent("test-data-01", _config(), llm_provider=provider)
        await agent.start()

        assert agent.status == AgentStatus.IDLE

    async def test_start_sets_idle(self) -> None:
        """After start(), agent should be IDLE and ready."""
        agent = TestDataAgent("test-data-01", _config(), llm_provider=_provider())
        await agent.start()
        assert agent.status == AgentStatus.IDLE


# =============================================================================
# Tests: Prompt Building (Static Method)
# =============================================================================
class TestTestDataAgentPromptBuilding:
    """Tests for the _build_user_prompt static method."""

    def test_basic_prompt(self) -> None:
        """Prompt should contain code and language."""
        prompt = TestDataAgent._build_user_prompt(
            code="def add(a, b): return a + b",
            language="python",
        )
        assert "add" in prompt
        assert "python" in prompt.lower()

    def test_prompt_includes_format(self) -> None:
        """Prompt should include the data format."""
        prompt = TestDataAgent._build_user_prompt(
            code="def add(a, b): return a + b",
            language="python",
            data_format="json",
        )
        assert "json" in prompt.lower()

    def test_prompt_includes_requirements(self) -> None:
        """Prompt should include requirements for edge and error cases."""
        prompt = TestDataAgent._build_user_prompt(
            code="def add(a, b): return a + b",
            language="python",
        )
        assert "edge case" in prompt.lower()
        assert "error case" in prompt.lower()

    def test_prompt_with_custom_format(self) -> None:
        """Prompt should use the specified data format."""
        prompt = TestDataAgent._build_user_prompt(
            code="code here",
            language="python",
            data_format="factories",
        )
        assert "factories" in prompt.lower()
