"""
End-to-End Integration Tests for ConductorAI
==============================================

These tests exercise the full ConductorAI pipeline from the facade layer
down through all internal components. Unlike unit tests (which mock
dependencies), integration tests verify that real components work together.

Test Scenarios:
    1. Single-phase workflow (DEVELOPMENT only)
    2. Full 3-phase workflow (DEVELOPMENT → DEVOPS → MONITORING)
    3. Single task dispatch (no workflow)
    4. Artifact management through the facade
    5. Multiple agents of the same type
    6. Workflow with task failure handling
    7. Facade lifecycle management
"""

from __future__ import annotations

import pytest

from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.development.test_data_agent import TestDataAgent
from conductor.agents.devops.deploying_agent import DeployingAgent
from conductor.agents.devops.devops_agent import DevOpsAgent
from conductor.agents.monitoring.monitor_agent import MonitorAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, TaskStatus, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.facade import ConductorAI
from conductor.infrastructure.artifact_store import Artifact, InMemoryArtifactStore
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def config():
    return ConductorConfig()


@pytest.fixture
def mock_provider():
    return MockLLMProvider()


# =============================================================================
# Test: Single-Phase Workflow (DEVELOPMENT only)
# =============================================================================

class TestSinglePhaseWorkflow:
    """Tests for workflows that only run the DEVELOPMENT phase."""

    async def test_coding_only_workflow(self, config, mock_provider):
        """Run a workflow with just one CodingAgent task."""
        mock_provider.queue_response("def hello(): return 'Hello!'")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )

            workflow = WorkflowDefinition(
                name="Coding Only",
                phases=[WorkflowPhase.DEVELOPMENT],
                tasks=[
                    TaskDefinition(
                        name="Generate Code",
                        assigned_to=AgentType.CODING,
                        input_data={
                            "specification": "Hello function",
                            "language": "python",
                        },
                    ),
                ],
            )

            state = await conductor.run_workflow(workflow)

            assert state.status == TaskStatus.COMPLETED
            assert state.completed_task_count == 1
            assert state.failed_task_count == 0
            assert len(state.phase_history) == 1
            assert state.phase_history[0]["phase"] == "development"

    async def test_development_phase_multiple_agents(self, config, mock_provider):
        """Run DEVELOPMENT with CodingAgent + ReviewAgent."""
        mock_provider.queue_response("def add(a, b): return a + b")
        mock_provider.queue_response("APPROVED. Code looks good.")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                ReviewAgent("review-01", config, llm_provider=mock_provider)
            )

            workflow = WorkflowDefinition(
                name="Code + Review",
                phases=[WorkflowPhase.DEVELOPMENT],
                tasks=[
                    TaskDefinition(
                        name="Generate Code",
                        assigned_to=AgentType.CODING,
                        input_data={
                            "specification": "Add function",
                            "language": "python",
                        },
                    ),
                    TaskDefinition(
                        name="Review Code",
                        assigned_to=AgentType.REVIEW,
                        input_data={
                            "code": "def add(a, b): return a + b",
                            "review_criteria": ["correctness"],
                        },
                    ),
                ],
            )

            state = await conductor.run_workflow(workflow)

            assert state.status == TaskStatus.COMPLETED
            assert state.completed_task_count == 2
            assert state.failed_task_count == 0

    async def test_all_development_agents(self, config, mock_provider):
        """Run all 4 DEVELOPMENT phase agents together."""
        # Queue 4 responses for coding, review, test_data, test
        mock_provider.queue_response("def process(): pass")
        mock_provider.queue_response("APPROVED")
        mock_provider.queue_response("test_data = [{'input': 1}]")
        mock_provider.queue_response("def test_process(): assert True")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                ReviewAgent("review-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                TestDataAgent("testdata-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                TestAgent("test-01", config, llm_provider=mock_provider)
            )

            workflow = WorkflowDefinition(
                name="Full Dev Phase",
                phases=[WorkflowPhase.DEVELOPMENT],
                tasks=[
                    TaskDefinition(
                        name="Generate Code",
                        assigned_to=AgentType.CODING,
                        input_data={"specification": "Process data", "language": "python"},
                    ),
                    TaskDefinition(
                        name="Review Code",
                        assigned_to=AgentType.REVIEW,
                        input_data={"code": "def process(): pass", "review_criteria": ["style"]},
                    ),
                    TaskDefinition(
                        name="Generate Test Data",
                        assigned_to=AgentType.TEST_DATA,
                        input_data={"code": "def process(): pass"},
                    ),
                    TaskDefinition(
                        name="Generate Tests",
                        assigned_to=AgentType.TEST,
                        input_data={"code": "def process(): pass"},
                    ),
                ],
            )

            state = await conductor.run_workflow(workflow)

            assert state.status == TaskStatus.COMPLETED
            assert state.completed_task_count == 4
            assert state.failed_task_count == 0


# =============================================================================
# Test: Full 3-Phase Workflow
# =============================================================================

class TestFullPipelineWorkflow:
    """Tests for workflows spanning all 3 phases."""

    async def test_full_pipeline(self, config, mock_provider):
        """Run a full DEVELOPMENT → DEVOPS → MONITORING workflow."""
        # Queue 7 responses (one per agent)
        mock_provider.queue_response("def api(): pass")          # coding
        mock_provider.queue_response("APPROVED")                 # review
        mock_provider.queue_response("[{'test': 'data'}]")       # test_data
        mock_provider.queue_response("def test_api(): pass")     # test
        mock_provider.queue_response("FROM python:3.12")         # devops
        mock_provider.queue_response("replicas: 2")              # deploying
        mock_provider.queue_response(                            # monitor
            "Severity: none\n\n"
            "### Issues Found\n(none)\n\n"
            "### Recommendations\n1. Add logging\n\n"
            "### Feedback for Development\nAll good."
        )

        async with ConductorAI(config) as conductor:
            # Register all 7 agents
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                ReviewAgent("review-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                TestDataAgent("testdata-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                TestAgent("test-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                DevOpsAgent("devops-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                DeployingAgent("deploying-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                MonitorAgent("monitor-01", config, llm_provider=mock_provider)
            )

            workflow = WorkflowDefinition(
                name="Full Pipeline",
                phases=[
                    WorkflowPhase.DEVELOPMENT,
                    WorkflowPhase.DEVOPS,
                    WorkflowPhase.MONITORING,
                ],
                tasks=[
                    # Development
                    TaskDefinition(
                        name="Generate Code",
                        assigned_to=AgentType.CODING,
                        input_data={"specification": "REST API", "language": "python"},
                    ),
                    TaskDefinition(
                        name="Review Code",
                        assigned_to=AgentType.REVIEW,
                        input_data={"code": "def api(): pass", "review_criteria": ["style"]},
                    ),
                    TaskDefinition(
                        name="Generate Test Data",
                        assigned_to=AgentType.TEST_DATA,
                        input_data={"code": "def api(): pass"},
                    ),
                    TaskDefinition(
                        name="Generate Tests",
                        assigned_to=AgentType.TEST,
                        input_data={"code": "def api(): pass"},
                    ),
                    # DevOps
                    TaskDefinition(
                        name="Create Docker Config",
                        assigned_to=AgentType.DEVOPS,
                        input_data={"code": "def api(): pass", "platform": "docker"},
                    ),
                    TaskDefinition(
                        name="Create Deployment",
                        assigned_to=AgentType.DEPLOYING,
                        input_data={"target_environment": "staging", "deployment_type": "docker"},
                    ),
                    # Monitoring
                    TaskDefinition(
                        name="Monitor Deployment",
                        assigned_to=AgentType.MONITOR,
                        input_data={"deployment_result": "Deployment successful"},
                    ),
                ],
            )

            state = await conductor.run_workflow(workflow)

            assert state.status == TaskStatus.COMPLETED
            assert state.completed_task_count == 7
            assert state.failed_task_count == 0
            assert len(state.phase_history) == 3
            assert state.phase_history[0]["phase"] == "development"
            assert state.phase_history[1]["phase"] == "devops"
            assert state.phase_history[2]["phase"] == "monitoring"

    async def test_two_phase_workflow(self, config, mock_provider):
        """Run DEVELOPMENT → DEVOPS (skip MONITORING)."""
        mock_provider.queue_response("def service(): pass")
        mock_provider.queue_response("Dockerfile contents")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                DevOpsAgent("devops-01", config, llm_provider=mock_provider)
            )

            workflow = WorkflowDefinition(
                name="Dev + DevOps",
                phases=[WorkflowPhase.DEVELOPMENT, WorkflowPhase.DEVOPS],
                tasks=[
                    TaskDefinition(
                        name="Generate Code",
                        assigned_to=AgentType.CODING,
                        input_data={"specification": "Service", "language": "python"},
                    ),
                    TaskDefinition(
                        name="Create Docker Config",
                        assigned_to=AgentType.DEVOPS,
                        input_data={"code": "def service(): pass", "platform": "docker"},
                    ),
                ],
            )

            state = await conductor.run_workflow(workflow)

            assert state.status == TaskStatus.COMPLETED
            assert state.completed_task_count == 2
            assert len(state.phase_history) == 2


# =============================================================================
# Test: Single Task Dispatch
# =============================================================================

class TestSingleTaskDispatch:
    """Tests for dispatch_task() — single task without a workflow."""

    async def test_dispatch_single_coding_task(self, config, mock_provider):
        """Dispatch one task directly to a CodingAgent."""
        mock_provider.queue_response("def greet(name): return f'Hi, {name}!'")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )

            task = TaskDefinition(
                name="Generate Greeting",
                assigned_to=AgentType.CODING,
                input_data={"specification": "Greeting function", "language": "python"},
            )

            result = await conductor.dispatch_task(task)

            assert result.status == TaskStatus.COMPLETED
            assert result.agent_id == "coding-01"
            assert "code" in result.output_data
            assert result.duration_seconds is not None

    async def test_dispatch_to_review_agent(self, config, mock_provider):
        """Dispatch one task directly to a ReviewAgent."""
        mock_provider.queue_response("APPROVED with minor feedback.")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                ReviewAgent("review-01", config, llm_provider=mock_provider)
            )

            task = TaskDefinition(
                name="Review Code",
                assigned_to=AgentType.REVIEW,
                input_data={
                    "code": "def hello(): return 'world'",
                    "review_criteria": ["style"],
                },
            )

            result = await conductor.dispatch_task(task)

            assert result.status == TaskStatus.COMPLETED
            assert result.agent_id == "review-01"

    async def test_dispatch_to_monitor_agent(self, config, mock_provider):
        """Dispatch a monitoring task directly."""
        mock_provider.queue_response(
            "Severity: low\n\n"
            "### Issues Found\n1. High memory usage\n\n"
            "### Recommendations\n1. Optimize caching\n\n"
            "### Feedback for Development\nConsider memory optimization."
        )

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                MonitorAgent("monitor-01", config, llm_provider=mock_provider)
            )

            task = TaskDefinition(
                name="Analyze Deployment",
                assigned_to=AgentType.MONITOR,
                input_data={"deployment_result": "Deployed with high memory usage"},
            )

            result = await conductor.dispatch_task(task)

            assert result.status == TaskStatus.COMPLETED
            assert result.output_data.get("has_issues") is True
            assert result.output_data.get("severity") == "low"


# =============================================================================
# Test: Artifact Management
# =============================================================================

class TestArtifactManagement:
    """Tests for artifact save/get/list through the facade."""

    async def test_save_and_retrieve_artifact(self, config):
        """Save an artifact and retrieve it by ID."""
        async with ConductorAI(config) as conductor:
            artifact = Artifact(
                workflow_id="wf-001",
                task_id="task-001",
                agent_id="coding-01",
                artifact_type="code",
                content="def hello(): return 'world'",
            )

            await conductor.save_artifact(artifact)
            retrieved = await conductor.get_artifact(artifact.artifact_id)

            assert retrieved is not None
            assert retrieved.content == artifact.content
            assert retrieved.artifact_type == "code"

    async def test_get_workflow_artifacts(self, config):
        """Save multiple artifacts and list by workflow ID."""
        async with ConductorAI(config) as conductor:
            for i in range(3):
                artifact = Artifact(
                    workflow_id="wf-002",
                    task_id=f"task-{i}",
                    agent_id=f"agent-{i}",
                    artifact_type="code",
                    content=f"content-{i}",
                )
                await conductor.save_artifact(artifact)

            artifacts = await conductor.get_workflow_artifacts("wf-002")
            assert len(artifacts) == 3

    async def test_artifact_not_found(self, config):
        """Get a non-existent artifact returns None."""
        async with ConductorAI(config) as conductor:
            result = await conductor.get_artifact("nonexistent")
            assert result is None


# =============================================================================
# Test: Error Handling
# =============================================================================

class TestErrorHandling:
    """Tests for error scenarios in the integration layer."""

    async def test_llm_failure_results_in_failed_task(self, config, mock_provider):
        """When the LLM provider fails, the task result should be FAILED."""
        mock_provider.set_should_fail(True, "Simulated LLM API outage")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )

            workflow = WorkflowDefinition(
                name="Failing Workflow",
                phases=[WorkflowPhase.DEVELOPMENT],
                tasks=[
                    TaskDefinition(
                        name="Generate Code",
                        assigned_to=AgentType.CODING,
                        input_data={"specification": "Test", "language": "python"},
                    ),
                ],
            )

            state = await conductor.run_workflow(workflow)

            # The workflow engine catches task dispatch failures and
            # records them as failed results, but the workflow itself
            # still completes (with failed tasks recorded).
            assert state.completed_task_count == 0
            assert state.failed_task_count >= 1

    async def test_uninitialized_facade_raises(self, config):
        """Calling methods before initialize() raises RuntimeError."""
        conductor = ConductorAI(config)

        with pytest.raises(RuntimeError, match="has not been initialized"):
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=MockLLMProvider())
            )

    async def test_uninitialized_dispatch_raises(self, config):
        """Dispatching before initialize() raises RuntimeError."""
        conductor = ConductorAI(config)

        with pytest.raises(RuntimeError, match="has not been initialized"):
            await conductor.dispatch_task(
                TaskDefinition(
                    name="Test",
                    assigned_to=AgentType.CODING,
                    input_data={"specification": "x", "language": "python"},
                )
            )

    async def test_uninitialized_workflow_raises(self, config):
        """Running a workflow before initialize() raises RuntimeError."""
        conductor = ConductorAI(config)

        with pytest.raises(RuntimeError, match="has not been initialized"):
            await conductor.run_workflow(
                WorkflowDefinition(name="Test", tasks=[])
            )


# =============================================================================
# Test: Facade Lifecycle
# =============================================================================

class TestFacadeLifecycle:
    """Tests for ConductorAI initialization and shutdown."""

    async def test_context_manager_initializes_and_shuts_down(self, config):
        """Context manager handles full lifecycle."""
        conductor = ConductorAI(config)
        assert not conductor.is_initialized

        async with conductor:
            assert conductor.is_initialized

        assert not conductor.is_initialized

    async def test_double_initialize_is_idempotent(self, config):
        """Calling initialize() twice is safe."""
        async with ConductorAI(config) as conductor:
            await conductor.initialize()  # Second call
            assert conductor.is_initialized

    async def test_shutdown_without_init_is_safe(self, config):
        """Calling shutdown() without initialize() is safe."""
        conductor = ConductorAI(config)
        await conductor.shutdown()  # Should not raise

    async def test_custom_artifact_store(self, config):
        """Facade accepts a custom artifact store."""
        custom_store = InMemoryArtifactStore()
        conductor = ConductorAI(config, artifact_store=custom_store)

        assert conductor.artifact_store is custom_store

    async def test_properties_accessible(self, config):
        """All facade properties are accessible after init."""
        async with ConductorAI(config) as conductor:
            assert conductor.config is not None
            assert conductor.coordinator is not None
            assert conductor.workflow_engine is not None
            assert conductor.message_bus is not None
            assert conductor.state_manager is not None
            assert conductor.artifact_store is not None
            assert conductor.error_handler is not None
            assert conductor.policy_engine is not None

    async def test_register_and_unregister_agent(self, config, mock_provider):
        """Register then unregister an agent."""
        async with ConductorAI(config) as conductor:
            agent = CodingAgent("coding-01", config, llm_provider=mock_provider)
            await conductor.register_agent(agent)
            assert conductor.coordinator.agent_count == 1

            await conductor.unregister_agent("coding-01")
            assert conductor.coordinator.agent_count == 0


# =============================================================================
# Test: LLM Call Tracking
# =============================================================================

class TestLLMCallTracking:
    """Verify that agents correctly interact with the LLM provider."""

    async def test_coding_agent_makes_one_llm_call(self, config, mock_provider):
        """Each agent task should make exactly one LLM call."""
        mock_provider.queue_response("def func(): pass")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )

            task = TaskDefinition(
                name="Generate Code",
                assigned_to=AgentType.CODING,
                input_data={"specification": "Function", "language": "python"},
            )
            await conductor.dispatch_task(task)

            assert mock_provider.call_count == 1

    async def test_multi_agent_workflow_call_count(self, config, mock_provider):
        """A 3-task workflow should make 3 LLM calls total."""
        mock_provider.queue_response("def func(): pass")
        mock_provider.queue_response("APPROVED")
        mock_provider.queue_response("[{'data': 1}]")

        async with ConductorAI(config) as conductor:
            await conductor.register_agent(
                CodingAgent("coding-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                ReviewAgent("review-01", config, llm_provider=mock_provider)
            )
            await conductor.register_agent(
                TestDataAgent("testdata-01", config, llm_provider=mock_provider)
            )

            workflow = WorkflowDefinition(
                name="3-Agent Dev",
                phases=[WorkflowPhase.DEVELOPMENT],
                tasks=[
                    TaskDefinition(
                        name="Code", assigned_to=AgentType.CODING,
                        input_data={"specification": "X", "language": "python"},
                    ),
                    TaskDefinition(
                        name="Review", assigned_to=AgentType.REVIEW,
                        input_data={"code": "X", "review_criteria": ["style"]},
                    ),
                    TaskDefinition(
                        name="Test Data", assigned_to=AgentType.TEST_DATA,
                        input_data={"code": "X"},
                    ),
                ],
            )

            await conductor.run_workflow(workflow)
            assert mock_provider.call_count == 3
