"""
Tests for conductor.agents.devops.deploying_agent
====================================================

These tests verify the DeployingAgent — the deployment configuration generator
in ConductorAI's DEVOPS phase.

What's Being Tested:
    - Agent initialization (identity, type, LLM provider)
    - Task validation (target_environment required)
    - Deployment config generation (prompt building, LLM call, result packaging)
    - Output structure (deployment_config, target_environment, files, LLM metadata)
    - Deployment type-to-filename mapping
    - Error handling (LLM failure, missing inputs)
    - Startup hook (LLM provider validation)

All tests use MockLLMProvider — no real API calls.
"""

import pytest

from conductor.agents.devops.deploying_agent import (
    DeployingAgent,
    DEPLOYING_SYSTEM_PROMPT,
    DEPLOYMENT_TYPE_FILENAMES,
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


SAMPLE_DEPLOYMENT_CONFIG = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: conductor-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: conductor-api
  template:
    metadata:
      labels:
        app: conductor-api
    spec:
      containers:
        - name: conductor-api
          image: conductor-api:latest
          ports:
            - containerPort: 8000
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
"""


def _deploying_task(**overrides) -> TaskDefinition:
    """Create a standard deploying task with optional overrides."""
    defaults = {
        "name": "Deploy to Production",
        "assigned_to": AgentType.DEPLOYING,
        "input_data": {
            "target_environment": "production",
            "deployment_type": "kubernetes",
        },
    }
    defaults.update(overrides)
    return TaskDefinition(**defaults)


# =============================================================================
# Tests: Agent Initialization
# =============================================================================
class TestDeployingAgentInit:
    """Tests for DeployingAgent initialization."""

    def test_creates_with_correct_type(self) -> None:
        """DeployingAgent should have AgentType.DEPLOYING."""
        agent = DeployingAgent("deploying-01", _config(), llm_provider=_provider())
        assert agent.agent_type == AgentType.DEPLOYING

    def test_creates_with_identity(self) -> None:
        """Agent should have the correct ID and name."""
        agent = DeployingAgent("deploying-01", _config(), llm_provider=_provider())
        assert agent.agent_id == "deploying-01"
        assert "DeployingAgent" in agent.identity.name

    def test_custom_name(self) -> None:
        """Custom name should override the default."""
        agent = DeployingAgent(
            "deploying-01", _config(), llm_provider=_provider(), name="K8s Deployer"
        )
        assert agent.identity.name == "K8s Deployer"

    def test_llm_provider_accessible(self) -> None:
        """LLM provider should be accessible via property."""
        provider = _provider()
        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        assert agent.llm_provider is provider


# =============================================================================
# Tests: Task Validation
# =============================================================================
class TestDeployingAgentValidation:
    """Tests for _validate_task."""

    async def test_valid_task_passes(self) -> None:
        """Task with target_environment should pass validation."""
        agent = DeployingAgent("deploying-01", _config(), llm_provider=_provider())
        task = _deploying_task()
        assert await agent._validate_task(task) is True

    async def test_missing_target_environment_fails(self) -> None:
        """Task without target_environment should fail validation."""
        agent = DeployingAgent("deploying-01", _config(), llm_provider=_provider())
        task = _deploying_task(input_data={"deployment_type": "kubernetes"})
        assert await agent._validate_task(task) is False

    async def test_empty_target_environment_fails(self) -> None:
        """Task with empty target_environment should fail validation."""
        agent = DeployingAgent("deploying-01", _config(), llm_provider=_provider())
        task = _deploying_task(input_data={"target_environment": ""})
        assert await agent._validate_task(task) is False

    async def test_whitespace_target_environment_fails(self) -> None:
        """Task with whitespace-only target_environment should fail."""
        agent = DeployingAgent("deploying-01", _config(), llm_provider=_provider())
        task = _deploying_task(input_data={"target_environment": "   "})
        assert await agent._validate_task(task) is False

    async def test_validation_failure_raises_agent_error(self) -> None:
        """Invalid task should raise AgentError through execute_task."""
        agent = DeployingAgent("deploying-01", _config(), llm_provider=_provider())
        await agent.start()

        task = _deploying_task(input_data={"deployment_type": "kubernetes"})
        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(task)
        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"


# =============================================================================
# Tests: Deployment Config Generation
# =============================================================================
class TestDeployingAgentExecution:
    """Tests for _execute (deployment config generation)."""

    async def test_generates_config_with_defaults(self) -> None:
        """Agent should generate deployment config and return structured result."""
        provider = _provider()
        provider.queue_response(SAMPLE_DEPLOYMENT_CONFIG)

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "deploying-01"
        assert "deployment_config" in result.output_data
        assert result.output_data["deployment_config"] == SAMPLE_DEPLOYMENT_CONFIG

    async def test_output_includes_target_environment(self) -> None:
        """Result should include the target environment."""
        provider = _provider()
        provider.queue_response("deploy config")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task()
        result = await agent.execute_task(task)

        assert result.output_data["target_environment"] == "production"

    async def test_output_includes_deployment_type(self) -> None:
        """Result should include the deployment type."""
        provider = _provider()
        provider.queue_response("deploy config")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task()
        result = await agent.execute_task(task)

        assert result.output_data["deployment_type"] == "kubernetes"

    async def test_output_includes_files(self) -> None:
        """Result should include generated file names."""
        provider = _provider()
        provider.queue_response("deploy config")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task()
        result = await agent.execute_task(task)

        assert "files" in result.output_data
        assert len(result.output_data["files"]) >= 1
        assert result.output_data["files"][0] == "deployment.yaml"

    async def test_output_includes_llm_metadata(self) -> None:
        """Result should include LLM model and usage stats."""
        provider = _provider()
        provider.queue_response("deploy config")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task()
        result = await agent.execute_task(task)

        assert "llm_model" in result.output_data
        assert "llm_usage" in result.output_data
        assert isinstance(result.output_data["llm_usage"], dict)

    async def test_docker_compose_deployment(self) -> None:
        """Docker compose deployment should produce docker-compose.yml."""
        provider = _provider()
        provider.queue_response("version: '3.8'\nservices:\n  app:\n    build: .")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task(input_data={
            "target_environment": "staging",
            "deployment_type": "docker_compose",
        })
        result = await agent.execute_task(task)

        assert result.output_data["deployment_type"] == "docker_compose"
        assert result.output_data["files"][0] == "docker-compose.yml"
        assert result.output_data["target_environment"] == "staging"

    async def test_with_code_context(self) -> None:
        """Agent should accept optional code context."""
        provider = _provider()
        provider.queue_response("deployment config with code context")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task(input_data={
            "target_environment": "production",
            "code": "from fastapi import FastAPI\napp = FastAPI()",
        })
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED

    async def test_with_cicd_config_context(self) -> None:
        """Agent should accept optional CI/CD config from DevOpsAgent."""
        provider = _provider()
        provider.queue_response("deployment config with CI/CD context")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task(input_data={
            "target_environment": "production",
            "config": "name: CI\non:\n  push:\n    branches: [main]",
        })
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED


# =============================================================================
# Tests: Deployment Type Filename Mapping
# =============================================================================
class TestDeploymentTypeFilenameMapping:
    """Tests for DEPLOYMENT_TYPE_FILENAMES constant."""

    def test_kubernetes(self) -> None:
        assert DEPLOYMENT_TYPE_FILENAMES["kubernetes"] == "deployment.yaml"

    def test_docker_compose(self) -> None:
        assert DEPLOYMENT_TYPE_FILENAMES["docker_compose"] == "docker-compose.yml"

    def test_terraform(self) -> None:
        assert DEPLOYMENT_TYPE_FILENAMES["terraform"] == "main.tf"

    def test_ansible(self) -> None:
        assert DEPLOYMENT_TYPE_FILENAMES["ansible"] == "playbook.yml"

    def test_unknown_type_gets_fallback(self) -> None:
        """Unknown deployment types should get a sensible fallback filename."""
        assert DEPLOYMENT_TYPE_FILENAMES.get("helm", "helm-deploy.yml") == "helm-deploy.yml"


# =============================================================================
# Tests: LLM Interaction
# =============================================================================
class TestDeployingAgentLLMInteraction:
    """Tests for how the agent interacts with the LLM provider."""

    async def test_calls_generate_with_system(self) -> None:
        """Agent should call generate_with_system with deploying prompt."""
        provider = _provider()
        provider.queue_response("deploy config")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task()
        await agent.execute_task(task)

        assert provider.call_count == 1
        call = provider.call_history[0]
        assert call["system_prompt"] == DEPLOYING_SYSTEM_PROMPT

    async def test_prompt_contains_environment(self) -> None:
        """The user prompt should contain the target environment."""
        provider = _provider()
        provider.queue_response("config")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task(input_data={
            "target_environment": "staging",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "staging" in call["prompt"]

    async def test_prompt_contains_deployment_type(self) -> None:
        """The prompt should mention the deployment type."""
        provider = _provider()
        provider.queue_response("config")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task(input_data={
            "target_environment": "production",
            "deployment_type": "terraform",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "terraform" in call["prompt"]

    async def test_prompt_includes_code_context(self) -> None:
        """If code is provided, it should appear in the prompt."""
        provider = _provider()
        provider.queue_response("config")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task(input_data={
            "target_environment": "production",
            "code": "class OrderService:\n    pass",
        })
        await agent.execute_task(task)

        call = provider.call_history[0]
        assert "OrderService" in call["prompt"]


# =============================================================================
# Tests: Error Handling
# =============================================================================
class TestDeployingAgentErrors:
    """Tests for error handling during deployment config generation."""

    async def test_llm_failure_returns_failed_result(self) -> None:
        """If the LLM fails, agent should return a FAILED TaskResult."""
        provider = _provider()
        provider.set_should_fail(True, "LLM service unavailable")

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task()
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        assert "LLM service unavailable" in result.error_message

    async def test_agent_returns_to_idle_after_failure(self) -> None:
        """Agent should return to IDLE after a task failure."""
        provider = _provider()
        provider.set_should_fail(True)

        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        task = _deploying_task()
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE
        assert agent.state.error_count == 1


# =============================================================================
# Tests: Startup Hook
# =============================================================================
class TestDeployingAgentStartup:
    """Tests for the _on_start lifecycle hook."""

    async def test_start_validates_provider(self) -> None:
        """start() should validate the LLM provider."""
        provider = _provider()
        agent = DeployingAgent("deploying-01", _config(), llm_provider=provider)
        await agent.start()

        assert agent.status == AgentStatus.IDLE

    async def test_start_sets_idle(self) -> None:
        """After start(), agent should be IDLE and ready."""
        agent = DeployingAgent("deploying-01", _config(), llm_provider=_provider())
        await agent.start()
        assert agent.status == AgentStatus.IDLE


# =============================================================================
# Tests: Prompt Building (Static Method)
# =============================================================================
class TestDeployingAgentPromptBuilding:
    """Tests for the _build_user_prompt static method."""

    def test_basic_prompt(self) -> None:
        """Prompt should contain target environment and deployment type."""
        prompt = DeployingAgent._build_user_prompt(
            target_environment="production",
            deployment_type="kubernetes",
        )
        assert "production" in prompt
        assert "kubernetes" in prompt

    def test_prompt_with_code(self) -> None:
        """Prompt should include source code when provided."""
        prompt = DeployingAgent._build_user_prompt(
            target_environment="staging",
            deployment_type="kubernetes",
            code="from fastapi import FastAPI",
        )
        assert "FastAPI" in prompt

    def test_prompt_with_cicd_config(self) -> None:
        """Prompt should include CI/CD config when provided."""
        prompt = DeployingAgent._build_user_prompt(
            target_environment="production",
            deployment_type="kubernetes",
            config="name: CI\non:\n  push:",
        )
        assert "CI" in prompt

    def test_prompt_includes_requirements(self) -> None:
        """Prompt should include deployment requirements."""
        prompt = DeployingAgent._build_user_prompt(
            target_environment="production",
            deployment_type="kubernetes",
        )
        assert "health check" in prompt.lower()
        assert "rollback" in prompt.lower()
