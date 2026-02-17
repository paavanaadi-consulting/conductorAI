"""
Tests for conductor.agents.devops.devops_agent
===================================================

These tests verify the DevOpsAgent — the CI/CD configuration generator
in ConductorAI's DEVOPS phase.

What's Being Tested:
    - Agent initialization (identity, type, LLM provider)
    - Task validation (code or project_description required)
    - Config generation (prompt building, LLM call, result packaging)
    - Output structure (config, platform, files, LLM metadata)
    - Platform-to-filename mapping
    - Error handling (LLM failure, missing inputs)
    - Startup hook (LLM provider validation)

All tests use MockLLMProvider — no real API calls.
"""

import pytest

from conductor.agents.devops.devops_agent import (
    DevOpsAgent,
    DEVOPS_SYSTEM_PROMPT,
    PLATFORM_FILENAMES,
)
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


SAMPLE_CI_CONFIG = """name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest
"""


def _devops_task(**overrides) -> TaskDefinition:
    """Create a standard DevOps task with optional overrides."""
    defaults = {
        "name": "Generate CI/CD",
        "assigned_to": AgentType.DEVOPS,
        "input_data": {
            "code": "def main():\n    print('Hello, World!')",
            "platform": "github_actions",
            "language": "python",
        },
    }
    defaults.update(overrides)
    return TaskDefinition(**defaults)


# =============================================================================
# Tests: Agent Initialization
# =============================================================================
class TestDevOpsAgentInit:
    """Tests for DevOpsAgent initialization."""

    def test_creates_with_correct_type(self) -> None:
        """DevOpsAgent should have AgentType.DEVOPS."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        assert agent.agent_type == AgentType.DEVOPS

    def test_creates_with_identity(self) -> None:
        """Agent should have the correct ID and name."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        assert agent.agent_id == "devops-01"
        assert "DevOpsAgent" in agent.identity.name

    def test_custom_name(self) -> None:
        """Custom name should override the default."""
        agent = DevOpsAgent(
            "devops-01", _config(), llm_provider=_provider(), name="Primary CI Builder"
        )
        assert agent.identity.name == "Primary CI Builder"

    def test_llm_provider_accessible(self) -> None:
        """LLM provider should be accessible via property."""
        provider = _provider()
        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        assert agent.llm_provider is provider


# =============================================================================
# Tests: Task Validation
# =============================================================================
class TestDevOpsAgentValidation:
    """Tests for _validate_task."""

    async def test_valid_task_with_code_passes(self) -> None:
        """Task with code should pass validation."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        task = _devops_task()
        assert await agent._validate_task(task) is True

    async def test_valid_task_with_project_description_passes(self) -> None:
        """Task with project_description should pass validation."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        task = _devops_task(input_data={
            "project_description": "A Python REST API for user management",
        })
        assert await agent._validate_task(task) is True

    async def test_missing_both_inputs_fails(self) -> None:
        """Task without code or project_description should fail."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        task = _devops_task(input_data={"platform": "github_actions"})
        assert await agent._validate_task(task) is False

    async def test_empty_code_fails(self) -> None:
        """Task with empty code and no description should fail."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        task = _devops_task(input_data={"code": ""})
        assert await agent._validate_task(task) is False

    async def test_whitespace_code_fails(self) -> None:
        """Task with whitespace-only code should fail."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        task = _devops_task(input_data={"code": "   "})
        assert await agent._validate_task(task) is False

    async def test_validation_failure_raises_agent_error(self) -> None:
        """Invalid task should raise AgentError through execute_task."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        await agent.start()

        task = _devops_task(input_data={"platform": "docker"})
        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(task)
        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"


# =============================================================================
# Tests: Config Generation
# =============================================================================
class TestDevOpsAgentExecution:
    """Tests for _execute (configuration generation)."""

    async def test_generates_config_with_defaults(self) -> None:
        """Agent should generate config and return structured result."""
        provider = _provider()
        provider.queue_response(SAMPLE_CI_CONFIG)

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "devops-01"
        assert "config" in result.output_data
        assert result.output_data["config"] == SAMPLE_CI_CONFIG

    async def test_output_includes_platform(self) -> None:
        """Result should include the platform used."""
        provider = _provider()
        provider.queue_response("config content")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task()
        result = await agent.execute_task(task)

        assert result.output_data["platform"] == "github_actions"

    async def test_output_includes_language(self) -> None:
        """Result should include the project language."""
        provider = _provider()
        provider.queue_response("config content")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task()
        result = await agent.execute_task(task)

        assert result.output_data["language"] == "python"

    async def test_output_includes_files(self) -> None:
        """Result should include generated file names."""
        provider = _provider()
        provider.queue_response("config content")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task()
        result = await agent.execute_task(task)

        assert "files" in result.output_data
        assert len(result.output_data["files"]) >= 1
        assert result.output_data["files"][0] == ".github/workflows/ci.yml"

    async def test_output_includes_llm_metadata(self) -> None:
        """Result should include LLM model and usage stats."""
        provider = _provider()
        provider.queue_response("config content")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task()
        result = await agent.execute_task(task)

        assert "llm_model" in result.output_data
        assert "llm_usage" in result.output_data
        assert isinstance(result.output_data["llm_usage"], dict)

    async def test_docker_platform(self) -> None:
        """Docker platform should produce Dockerfile."""
        provider = _provider()
        provider.queue_response("FROM python:3.12\nCOPY . /app")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task(input_data={
            "code": "app code",
            "platform": "docker",
        })
        result = await agent.execute_task(task)

        assert result.output_data["platform"] == "docker"
        assert result.output_data["files"][0] == "Dockerfile"

    async def test_project_description_instead_of_code(self) -> None:
        """Agent should accept project_description as input."""
        provider = _provider()
        provider.queue_response("CI config here")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task(input_data={
            "project_description": "A Python web API built with FastAPI",
            "platform": "github_actions",
        })
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED


# =============================================================================
# Tests: Platform Filename Mapping
# =============================================================================
class TestPlatformFilenameMapping:
    """Tests for PLATFORM_FILENAMES constant."""

    def test_github_actions(self) -> None:
        assert PLATFORM_FILENAMES["github_actions"] == ".github/workflows/ci.yml"

    def test_docker(self) -> None:
        assert PLATFORM_FILENAMES["docker"] == "Dockerfile"

    def test_gitlab_ci(self) -> None:
        assert PLATFORM_FILENAMES["gitlab_ci"] == ".gitlab-ci.yml"

    def test_jenkins(self) -> None:
        assert PLATFORM_FILENAMES["jenkins"] == "Jenkinsfile"

    def test_unknown_platform_gets_fallback(self) -> None:
        """Unknown platforms should get a sensible fallback filename."""
        # This tests the get() call in _execute with default
        assert PLATFORM_FILENAMES.get("circleci", "circleci-config.yml") == "circleci-config.yml"


# =============================================================================
# Tests: LLM Interaction
# =============================================================================
class TestDevOpsAgentLLMInteraction:
    """Tests for how the agent interacts with the LLM provider."""

    async def test_calls_generate_with_system(self) -> None:
        """Agent should call generate_with_system with DevOps prompt."""
        provider = _provider()
        provider.queue_response("CI config")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task()
        await agent.execute_task(task)

        assert provider.call_count == 1
        call = provider.call_history[0]
        assert call["system_prompt"] == DEVOPS_SYSTEM_PROMPT

    async def test_prompt_contains_code(self) -> None:
        """The user prompt should contain the source code."""
        provider = _provider()
        provider.queue_response("config")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task(input_data={
            "code": "class UserService:\n    pass",
            "platform": "github_actions",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "UserService" in call["prompt"]

    async def test_prompt_contains_platform(self) -> None:
        """The prompt should mention the target platform."""
        provider = _provider()
        provider.queue_response("config")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task(input_data={
            "code": "app code",
            "platform": "gitlab_ci",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "gitlab_ci" in call["prompt"]

    async def test_prompt_includes_additional_requirements(self) -> None:
        """Additional requirements should appear in the prompt."""
        provider = _provider()
        provider.queue_response("config")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task(input_data={
            "code": "app code",
            "additional_requirements": "Include SonarQube analysis step",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "sonarqube" in call["prompt"].lower()


# =============================================================================
# Tests: Error Handling
# =============================================================================
class TestDevOpsAgentErrors:
    """Tests for error handling during config generation."""

    async def test_llm_failure_returns_failed_result(self) -> None:
        """If the LLM fails, agent should return a FAILED TaskResult."""
        provider = _provider()
        provider.set_should_fail(True, "LLM service unavailable")

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        assert "LLM service unavailable" in result.error_message

    async def test_agent_returns_to_idle_after_failure(self) -> None:
        """Agent should return to IDLE after a task failure."""
        provider = _provider()
        provider.set_should_fail(True)

        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        task = _devops_task()
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE
        assert agent.state.error_count == 1


# =============================================================================
# Tests: Startup Hook
# =============================================================================
class TestDevOpsAgentStartup:
    """Tests for the _on_start lifecycle hook."""

    async def test_start_validates_provider(self) -> None:
        """start() should validate the LLM provider."""
        provider = _provider()
        agent = DevOpsAgent("devops-01", _config(), llm_provider=provider)
        await agent.start()

        assert agent.status == AgentStatus.IDLE

    async def test_start_sets_idle(self) -> None:
        """After start(), agent should be IDLE and ready."""
        agent = DevOpsAgent("devops-01", _config(), llm_provider=_provider())
        await agent.start()
        assert agent.status == AgentStatus.IDLE


# =============================================================================
# Tests: Prompt Building (Static Method)
# =============================================================================
class TestDevOpsAgentPromptBuilding:
    """Tests for the _build_user_prompt static method."""

    def test_basic_prompt_with_code(self) -> None:
        """Prompt should contain code and platform."""
        prompt = DevOpsAgent._build_user_prompt(
            code="def main(): pass",
            platform="github_actions",
            language="python",
        )
        assert "def main(): pass" in prompt
        assert "github_actions" in prompt

    def test_prompt_with_project_description(self) -> None:
        """Prompt should include project description."""
        prompt = DevOpsAgent._build_user_prompt(
            project_description="A FastAPI web service",
            platform="docker",
            language="python",
        )
        assert "FastAPI" in prompt

    def test_prompt_with_additional_requirements(self) -> None:
        """Prompt should include additional requirements."""
        prompt = DevOpsAgent._build_user_prompt(
            code="code here",
            platform="github_actions",
            language="python",
            additional_requirements="Run security scanning with Snyk",
        )
        assert "Snyk" in prompt

    def test_prompt_includes_platform_requirements(self) -> None:
        """Prompt should include platform best practices."""
        prompt = DevOpsAgent._build_user_prompt(
            code="code here",
            platform="gitlab_ci",
            language="python",
        )
        assert "gitlab_ci" in prompt
        assert "best practices" in prompt.lower()
