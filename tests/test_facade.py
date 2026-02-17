"""
Tests for conductor.facade - ConductorAI Top-Level Facade
============================================================

These tests verify the ConductorAI facade — the main entry point
that ties together all framework layers.

What's Being Tested:
    - Initialization and shutdown lifecycle
    - Async context manager (async with)
    - Agent registration and unregistration
    - Workflow execution through the facade
    - Single task dispatch
    - Artifact management
    - Property access to internal components
    - Error handling (uninitialized access)

All tests use in-memory implementations — no external dependencies.
"""

import pytest

from conductor.facade import ConductorAI
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, TaskStatus, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.infrastructure.artifact_store import Artifact, InMemoryArtifactStore
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Helpers
# =============================================================================
def _config() -> ConductorConfig:
    return ConductorConfig()


def _provider() -> MockLLMProvider:
    provider = MockLLMProvider()
    provider.queue_response("generated code here")
    provider.queue_response("generated code here")
    provider.queue_response("generated code here")
    return provider


def _coding_agent(provider: MockLLMProvider) -> CodingAgent:
    return CodingAgent("coding-01", _config(), llm_provider=provider)


def _coding_task() -> TaskDefinition:
    return TaskDefinition(
        name="Generate API",
        assigned_to=AgentType.CODING,
        input_data={
            "specification": "Create a REST API for user management",
            "language": "python",
        },
    )


# =============================================================================
# Tests: Initialization
# =============================================================================
class TestConductorAIInit:
    """Tests for ConductorAI initialization."""

    def test_creates_with_defaults(self) -> None:
        """ConductorAI should create with default config."""
        conductor = ConductorAI()
        assert conductor.config is not None
        assert conductor.is_initialized is False

    def test_creates_with_custom_config(self) -> None:
        """ConductorAI should accept custom config."""
        config = ConductorConfig()
        conductor = ConductorAI(config)
        assert conductor.config is config

    async def test_initialize(self) -> None:
        """initialize() should set up all components."""
        conductor = ConductorAI()
        await conductor.initialize()

        assert conductor.is_initialized is True

        await conductor.shutdown()

    async def test_initialize_is_idempotent(self) -> None:
        """Calling initialize() twice should be safe."""
        conductor = ConductorAI()
        await conductor.initialize()
        await conductor.initialize()  # Should not raise

        assert conductor.is_initialized is True

        await conductor.shutdown()

    async def test_shutdown(self) -> None:
        """shutdown() should tear down all components."""
        conductor = ConductorAI()
        await conductor.initialize()
        await conductor.shutdown()

        assert conductor.is_initialized is False

    async def test_shutdown_is_idempotent(self) -> None:
        """Calling shutdown() twice should be safe."""
        conductor = ConductorAI()
        await conductor.initialize()
        await conductor.shutdown()
        await conductor.shutdown()  # Should not raise

        assert conductor.is_initialized is False

    async def test_shutdown_without_initialize(self) -> None:
        """shutdown() without initialize() should be safe."""
        conductor = ConductorAI()
        await conductor.shutdown()  # Should not raise


# =============================================================================
# Tests: Async Context Manager
# =============================================================================
class TestConductorAIContextManager:
    """Tests for async with ConductorAI()."""

    async def test_context_manager_initializes(self) -> None:
        """async with should call initialize()."""
        async with ConductorAI() as conductor:
            assert conductor.is_initialized is True

    async def test_context_manager_shuts_down(self) -> None:
        """Exiting async with should call shutdown()."""
        conductor = ConductorAI()
        async with conductor:
            assert conductor.is_initialized is True
        assert conductor.is_initialized is False

    async def test_context_manager_returns_self(self) -> None:
        """async with should return the ConductorAI instance."""
        async with ConductorAI() as conductor:
            assert isinstance(conductor, ConductorAI)


# =============================================================================
# Tests: Agent Management
# =============================================================================
class TestConductorAIAgentManagement:
    """Tests for agent registration and unregistration."""

    async def test_register_agent(self) -> None:
        """Should register an agent with the coordinator."""
        provider = _provider()
        async with ConductorAI() as conductor:
            agent = _coding_agent(provider)
            await conductor.register_agent(agent)

            # Agent should be available for dispatch
            task = _coding_task()
            result = await conductor.dispatch_task(task)
            assert result.status == TaskStatus.COMPLETED

    async def test_register_multiple_agents(self) -> None:
        """Should support multiple agent registrations."""
        provider = _provider()
        async with ConductorAI() as conductor:
            coding = CodingAgent("coding-01", _config(), llm_provider=provider)
            review = ReviewAgent("review-01", _config(), llm_provider=provider)

            await conductor.register_agent(coding)
            await conductor.register_agent(review)

    async def test_register_without_initialize_raises(self) -> None:
        """Registering without initialize should raise RuntimeError."""
        conductor = ConductorAI()
        agent = _coding_agent(_provider())

        with pytest.raises(RuntimeError, match="not been initialized"):
            await conductor.register_agent(agent)


# =============================================================================
# Tests: Workflow Execution
# =============================================================================
class TestConductorAIWorkflow:
    """Tests for workflow execution through the facade."""

    async def test_run_simple_workflow(self) -> None:
        """Should execute a simple single-phase workflow."""
        provider = _provider()
        async with ConductorAI() as conductor:
            agent = _coding_agent(provider)
            await conductor.register_agent(agent)

            definition = WorkflowDefinition(
                name="Simple Workflow",
                phases=[WorkflowPhase.DEVELOPMENT],
                tasks=[_coding_task()],
            )

            state = await conductor.run_workflow(definition)
            assert state.status == TaskStatus.COMPLETED

    async def test_run_workflow_without_initialize_raises(self) -> None:
        """Running workflow without initialize should raise RuntimeError."""
        conductor = ConductorAI()
        definition = WorkflowDefinition(
            name="Test",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[_coding_task()],
        )

        with pytest.raises(RuntimeError, match="not been initialized"):
            await conductor.run_workflow(definition)


# =============================================================================
# Tests: Task Dispatch
# =============================================================================
class TestConductorAITaskDispatch:
    """Tests for single task dispatch through the facade."""

    async def test_dispatch_task(self) -> None:
        """Should dispatch a single task to an agent."""
        provider = _provider()
        async with ConductorAI() as conductor:
            agent = _coding_agent(provider)
            await conductor.register_agent(agent)

            task = _coding_task()
            result = await conductor.dispatch_task(task)

            assert result.status == TaskStatus.COMPLETED
            assert result.agent_id == "coding-01"

    async def test_dispatch_without_initialize_raises(self) -> None:
        """Dispatching without initialize should raise RuntimeError."""
        conductor = ConductorAI()
        with pytest.raises(RuntimeError, match="not been initialized"):
            await conductor.dispatch_task(_coding_task())


# =============================================================================
# Tests: Artifact Management
# =============================================================================
class TestConductorAIArtifacts:
    """Tests for artifact management through the facade."""

    async def test_save_and_get_artifact(self) -> None:
        """Should save and retrieve artifacts."""
        async with ConductorAI() as conductor:
            artifact = Artifact(
                workflow_id="wf-001",
                task_id="task-abc",
                agent_id="coding-01",
                artifact_type="code",
                content="def hello(): pass",
            )

            await conductor.save_artifact(artifact)
            retrieved = await conductor.get_artifact(artifact.artifact_id)

            assert retrieved is not None
            assert retrieved.content == "def hello(): pass"

    async def test_get_workflow_artifacts(self) -> None:
        """Should return all artifacts for a workflow."""
        async with ConductorAI() as conductor:
            a1 = Artifact(
                workflow_id="wf-001", task_id="t1", agent_id="a1",
                artifact_type="code", content="code 1",
            )
            a2 = Artifact(
                workflow_id="wf-001", task_id="t2", agent_id="a2",
                artifact_type="test", content="test 1",
            )

            await conductor.save_artifact(a1)
            await conductor.save_artifact(a2)

            artifacts = await conductor.get_workflow_artifacts("wf-001")
            assert len(artifacts) == 2


# =============================================================================
# Tests: Property Access
# =============================================================================
class TestConductorAIProperties:
    """Tests for property access to internal components."""

    def test_properties_accessible(self) -> None:
        """All internal components should be accessible via properties."""
        conductor = ConductorAI()

        assert conductor.config is not None
        assert conductor.coordinator is not None
        assert conductor.workflow_engine is not None
        assert conductor.message_bus is not None
        assert conductor.state_manager is not None
        assert conductor.artifact_store is not None
        assert conductor.error_handler is not None
        assert conductor.policy_engine is not None

    def test_custom_artifact_store(self) -> None:
        """Custom artifact store should be used when provided."""
        store = InMemoryArtifactStore()
        conductor = ConductorAI(artifact_store=store)
        assert conductor.artifact_store is store

    def test_repr(self) -> None:
        """repr should include initialization status."""
        conductor = ConductorAI()
        r = repr(conductor)
        assert "ConductorAI" in r
        assert "initialized=False" in r
