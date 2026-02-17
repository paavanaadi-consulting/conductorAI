"""
Tests for conductor.agents.development.coding_agent
======================================================

These tests verify the CodingAgent — the first specialized agent that
generates source code from specifications using an LLM.

What's Being Tested:
    - Agent initialization (identity, type, LLM provider)
    - Task validation (specification required, non-empty)
    - Code generation (prompt building, LLM call, result packaging)
    - Output structure (code, language, files, LLM metadata)
    - Error handling (LLM failure, missing inputs)
    - Startup hook (LLM provider validation)

All tests use MockLLMProvider — no real API calls.
"""

import pytest

from conductor.agents.development.coding_agent import CodingAgent, CODING_SYSTEM_PROMPT
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


def _coding_task(**overrides) -> TaskDefinition:
    """Create a standard coding task with optional overrides."""
    defaults = {
        "name": "Generate API",
        "assigned_to": AgentType.CODING,
        "input_data": {
            "specification": "Create a REST API for user management",
            "language": "python",
        },
    }
    defaults.update(overrides)
    return TaskDefinition(**defaults)


# =============================================================================
# Tests: Agent Initialization
# =============================================================================
class TestCodingAgentInit:
    """Tests for CodingAgent initialization."""

    def test_creates_with_correct_type(self) -> None:
        """CodingAgent should have AgentType.CODING."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider())
        assert agent.agent_type == AgentType.CODING

    def test_creates_with_identity(self) -> None:
        """Agent should have the correct ID and name."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider())
        assert agent.agent_id == "coding-01"
        assert "CodingAgent" in agent.identity.name

    def test_custom_name(self) -> None:
        """Custom name should override the default."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider(), name="Primary Coder")
        assert agent.identity.name == "Primary Coder"

    def test_llm_provider_accessible(self) -> None:
        """LLM provider should be accessible via property."""
        provider = _provider()
        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        assert agent.llm_provider is provider


# =============================================================================
# Tests: Task Validation
# =============================================================================
class TestCodingAgentValidation:
    """Tests for _validate_task."""

    async def test_valid_task_passes(self) -> None:
        """Task with specification should pass validation."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider())
        task = _coding_task()
        assert await agent._validate_task(task) is True

    async def test_missing_specification_fails(self) -> None:
        """Task without specification should fail validation."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider())
        task = _coding_task(input_data={"language": "python"})
        assert await agent._validate_task(task) is False

    async def test_empty_specification_fails(self) -> None:
        """Task with empty specification should fail validation."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider())
        task = _coding_task(input_data={"specification": ""})
        assert await agent._validate_task(task) is False

    async def test_whitespace_specification_fails(self) -> None:
        """Task with whitespace-only specification should fail."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider())
        task = _coding_task(input_data={"specification": "   "})
        assert await agent._validate_task(task) is False

    async def test_validation_failure_raises_agent_error(self) -> None:
        """Invalid task should raise AgentError through execute_task."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider())
        await agent.start()

        task = _coding_task(input_data={"language": "python"})
        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(task)
        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"


# =============================================================================
# Tests: Code Generation
# =============================================================================
class TestCodingAgentExecution:
    """Tests for _execute (code generation)."""

    async def test_generates_code_with_defaults(self) -> None:
        """Agent should generate code and return structured result."""
        provider = _provider()
        provider.queue_response("def hello():\n    return 'Hello, World!'")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "coding-01"
        assert "code" in result.output_data
        assert result.output_data["code"] == "def hello():\n    return 'Hello, World!'"
        assert result.output_data["language"] == "python"

    async def test_output_includes_files_list(self) -> None:
        """Result should include generated file names."""
        provider = _provider()
        provider.queue_response("code here")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task()
        result = await agent.execute_task(task)

        assert "files" in result.output_data
        assert len(result.output_data["files"]) >= 1
        assert result.output_data["files"][0].endswith(".py")

    async def test_output_includes_llm_metadata(self) -> None:
        """Result should include LLM model and usage stats."""
        provider = _provider()
        provider.queue_response("code here")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task()
        result = await agent.execute_task(task)

        assert "llm_model" in result.output_data
        assert "llm_usage" in result.output_data
        assert isinstance(result.output_data["llm_usage"], dict)

    async def test_custom_language(self) -> None:
        """Agent should use the specified language."""
        provider = _provider()
        provider.queue_response("function hello() { return 'Hello'; }")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task(input_data={
            "specification": "Hello world function",
            "language": "javascript",
        })
        result = await agent.execute_task(task)

        assert result.output_data["language"] == "javascript"
        assert result.output_data["files"][0].endswith(".js")

    async def test_custom_file_name(self) -> None:
        """Agent should use custom file_name from input_data."""
        provider = _provider()
        provider.queue_response("code")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task(input_data={
            "specification": "API endpoint",
            "file_name": "api_routes.py",
        })
        result = await agent.execute_task(task)

        assert result.output_data["files"][0] == "api_routes.py"

    async def test_specification_passed_to_output(self) -> None:
        """Output should include the original specification for tracing."""
        provider = _provider()
        provider.queue_response("code")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task()
        result = await agent.execute_task(task)

        assert "specification" in result.output_data


# =============================================================================
# Tests: LLM Interaction
# =============================================================================
class TestCodingAgentLLMInteraction:
    """Tests for how the agent interacts with the LLM provider."""

    async def test_calls_generate_with_system(self) -> None:
        """Agent should call generate_with_system (not plain generate)."""
        provider = _provider()
        provider.queue_response("generated code")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task()
        await agent.execute_task(task)

        # Check that generate_with_system was called (has system_prompt)
        assert provider.call_count == 1
        call = provider.call_history[0]
        assert call["system_prompt"] is not None
        assert call["system_prompt"] == CODING_SYSTEM_PROMPT

    async def test_prompt_contains_specification(self) -> None:
        """The user prompt should contain the specification text."""
        provider = _provider()
        provider.queue_response("code")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task(input_data={
            "specification": "Create a binary search tree implementation",
            "language": "python",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "binary search tree" in call["prompt"].lower()

    async def test_prompt_contains_language(self) -> None:
        """The prompt should mention the target language."""
        provider = _provider()
        provider.queue_response("code")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task(input_data={
            "specification": "Hello world",
            "language": "rust",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "rust" in call["prompt"].lower()

    async def test_prompt_includes_framework(self) -> None:
        """If framework is specified, it should appear in the prompt."""
        provider = _provider()
        provider.queue_response("code")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task(input_data={
            "specification": "REST API",
            "language": "python",
            "framework": "fastapi",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "fastapi" in call["prompt"].lower()

    async def test_prompt_includes_additional_context(self) -> None:
        """Additional context should be included in the prompt."""
        provider = _provider()
        provider.queue_response("code")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task(input_data={
            "specification": "API",
            "additional_context": "Use SQLAlchemy ORM for database access",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "sqlalchemy" in call["prompt"].lower()


# =============================================================================
# Tests: Error Handling
# =============================================================================
class TestCodingAgentErrors:
    """Tests for error handling during code generation."""

    async def test_llm_failure_returns_failed_result(self) -> None:
        """If the LLM fails, agent should return a FAILED TaskResult.

        BaseAgent catches RuntimeError and converts to FAILED result.
        """
        provider = _provider()
        provider.set_should_fail(True, "LLM service unavailable")

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task()
        result = await agent.execute_task(task)

        # BaseAgent catches RuntimeError → FAILED TaskResult
        assert result.status == TaskStatus.FAILED
        assert "LLM service unavailable" in result.error_message

    async def test_agent_returns_to_idle_after_failure(self) -> None:
        """Agent should return to IDLE after a task failure."""
        provider = _provider()
        provider.set_should_fail(True)

        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        task = _coding_task()
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE
        assert agent.state.error_count == 1


# =============================================================================
# Tests: Startup Hook
# =============================================================================
class TestCodingAgentStartup:
    """Tests for the _on_start lifecycle hook."""

    async def test_start_validates_provider(self) -> None:
        """start() should validate the LLM provider."""
        provider = _provider()
        agent = CodingAgent("coding-01", _config(), llm_provider=provider)
        await agent.start()

        assert agent.status == AgentStatus.IDLE

    async def test_start_sets_idle(self) -> None:
        """After start(), agent should be IDLE and ready."""
        agent = CodingAgent("coding-01", _config(), llm_provider=_provider())
        await agent.start()
        assert agent.status == AgentStatus.IDLE


# =============================================================================
# Tests: Prompt Building (Static Method)
# =============================================================================
class TestCodingAgentPromptBuilding:
    """Tests for the _build_user_prompt static method."""

    def test_basic_prompt(self) -> None:
        """Prompt should contain specification and language."""
        prompt = CodingAgent._build_user_prompt(
            specification="Build a calculator",
            language="python",
        )
        assert "calculator" in prompt.lower()
        assert "python" in prompt.lower()

    def test_prompt_with_framework(self) -> None:
        """Prompt should include framework when specified."""
        prompt = CodingAgent._build_user_prompt(
            specification="REST API",
            language="python",
            framework="flask",
        )
        assert "flask" in prompt.lower()

    def test_prompt_with_additional_context(self) -> None:
        """Prompt should include additional context."""
        prompt = CodingAgent._build_user_prompt(
            specification="API",
            language="python",
            additional_context="Use PostgreSQL database",
        )
        assert "postgresql" in prompt.lower()


# =============================================================================
# Tests: File Extension Mapping
# =============================================================================
class TestFileExtensionMapping:
    """Tests for the _get_extension utility."""

    def test_python(self) -> None:
        assert CodingAgent._get_extension("python") == "py"

    def test_javascript(self) -> None:
        assert CodingAgent._get_extension("javascript") == "js"

    def test_typescript(self) -> None:
        assert CodingAgent._get_extension("typescript") == "ts"

    def test_go(self) -> None:
        assert CodingAgent._get_extension("go") == "go"

    def test_rust(self) -> None:
        assert CodingAgent._get_extension("rust") == "rs"

    def test_unknown_language(self) -> None:
        assert CodingAgent._get_extension("brainf") == "txt"

    def test_case_insensitive(self) -> None:
        assert CodingAgent._get_extension("Python") == "py"
