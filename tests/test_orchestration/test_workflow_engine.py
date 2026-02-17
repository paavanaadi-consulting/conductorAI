"""
Tests for conductor.orchestration.workflow_engine
===================================================

These tests verify the WorkflowEngine — the top-level orchestrator that
executes multi-phase workflows from start to finish.

What's Being Tested:
    - Single-phase workflow execution
    - Multi-phase workflow execution (DEVELOPMENT → DEVOPS)
    - Phase-to-agent-type mapping
    - Task failure recording in workflow state
    - Phase gate checks via PolicyEngine
    - Feedback loop triggering and max-loop enforcement
    - Workflow state persistence
    - Empty workflow / empty phase handling

All tests use MockAgent for isolation — no real LLM calls.
"""

import pytest

from conductor.agents.base import BaseAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, TaskStatus, WorkflowPhase
from conductor.core.exceptions import WorkflowError
from conductor.core.models import TaskDefinition, TaskResult, WorkflowDefinition
from conductor.orchestration.agent_coordinator import AgentCoordinator
from conductor.orchestration.message_bus import InMemoryMessageBus
from conductor.orchestration.policy_engine import PhaseGatePolicy, PolicyEngine
from conductor.orchestration.state_manager import InMemoryStateManager
from conductor.orchestration.workflow_engine import PHASE_AGENT_TYPES, WorkflowEngine


# =============================================================================
# Mock Agent
# =============================================================================
class MockAgent(BaseAgent):
    """Simple mock agent that succeeds with echoed input."""

    async def _validate_task(self, task: TaskDefinition) -> bool:
        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={"result": f"done-{task.name}"},
        )


class FailingMockAgent(BaseAgent):
    """Mock agent that always fails."""

    async def _validate_task(self, task: TaskDefinition) -> bool:
        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        raise RuntimeError(f"Failed: {task.name}")


# =============================================================================
# Helpers
# =============================================================================
def _config() -> ConductorConfig:
    return ConductorConfig()


async def _create_engine(
    agents: list[tuple[str, AgentType]] | None = None,
    with_policy_engine: bool = False,
    max_feedback_loops: int = 3,
    use_failing_agent: bool = False,
) -> tuple[WorkflowEngine, AgentCoordinator, InMemoryMessageBus, InMemoryStateManager]:
    """Create a fully wired WorkflowEngine with coordinator and agents."""
    bus = InMemoryMessageBus()
    sm = InMemoryStateManager()
    await bus.connect()
    await sm.connect()

    pe = PolicyEngine() if with_policy_engine else None
    coordinator = AgentCoordinator(bus, sm, policy_engine=None)
    await coordinator.start()

    engine = WorkflowEngine(
        coordinator=coordinator,
        state_manager=sm,
        policy_engine=pe,
        max_feedback_loops=max_feedback_loops,
    )

    # Register agents
    if agents:
        for agent_id, agent_type in agents:
            agent_cls = FailingMockAgent if use_failing_agent else MockAgent
            agent = agent_cls(agent_id, agent_type, _config())
            await coordinator.register_agent(agent)

    return engine, coordinator, bus, sm


# =============================================================================
# Tests: Phase-Agent Mapping
# =============================================================================
class TestPhaseAgentMapping:
    """Tests for the PHASE_AGENT_TYPES constant."""

    def test_development_phase_agents(self) -> None:
        """DEVELOPMENT should include CODING, REVIEW, TEST_DATA, TEST."""
        dev_types = PHASE_AGENT_TYPES[WorkflowPhase.DEVELOPMENT]
        assert AgentType.CODING in dev_types
        assert AgentType.REVIEW in dev_types
        assert AgentType.TEST_DATA in dev_types
        assert AgentType.TEST in dev_types

    def test_devops_phase_agents(self) -> None:
        """DEVOPS should include DEVOPS and DEPLOYING."""
        devops_types = PHASE_AGENT_TYPES[WorkflowPhase.DEVOPS]
        assert AgentType.DEVOPS in devops_types
        assert AgentType.DEPLOYING in devops_types

    def test_monitoring_phase_agents(self) -> None:
        """MONITORING should include MONITOR."""
        mon_types = PHASE_AGENT_TYPES[WorkflowPhase.MONITORING]
        assert AgentType.MONITOR in mon_types


# =============================================================================
# Tests: Single-Phase Workflow
# =============================================================================
class TestSinglePhaseWorkflow:
    """Tests for executing a workflow with one phase."""

    async def test_single_task_workflow(self) -> None:
        """A workflow with one task should complete successfully."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[("coding-01", AgentType.CODING)],
        )

        task = TaskDefinition(
            name="Generate Code",
            assigned_to=AgentType.CODING,
        )
        definition = WorkflowDefinition(
            name="Simple Workflow",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[task],
        )

        state = await engine.run_workflow(definition)

        assert state.status == TaskStatus.COMPLETED
        assert state.completed_task_count == 1
        assert state.failed_task_count == 0
        assert task.task_id in state.task_results
        assert state.completed_at is not None

        await coordinator.stop()
        await bus.disconnect()

    async def test_multiple_tasks_in_phase(self) -> None:
        """Multiple tasks in one phase should all execute."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[
                ("coding-01", AgentType.CODING),
                ("review-01", AgentType.REVIEW),
            ],
        )

        tasks = [
            TaskDefinition(name="Generate Code", assigned_to=AgentType.CODING),
            TaskDefinition(name="Review Code", assigned_to=AgentType.REVIEW),
        ]
        definition = WorkflowDefinition(
            name="Dev Workflow",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=tasks,
        )

        state = await engine.run_workflow(definition)

        assert state.status == TaskStatus.COMPLETED
        assert state.completed_task_count == 2
        assert len(state.task_results) == 2

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: Multi-Phase Workflow
# =============================================================================
class TestMultiPhaseWorkflow:
    """Tests for workflows spanning multiple phases."""

    async def test_two_phase_workflow(self) -> None:
        """DEVELOPMENT + DEVOPS phases should execute in sequence."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[
                ("coding-01", AgentType.CODING),
                ("devops-01", AgentType.DEVOPS),
            ],
        )

        tasks = [
            TaskDefinition(name="Code", assigned_to=AgentType.CODING),
            TaskDefinition(name="Deploy", assigned_to=AgentType.DEVOPS),
        ]
        definition = WorkflowDefinition(
            name="Full Pipeline",
            phases=[WorkflowPhase.DEVELOPMENT, WorkflowPhase.DEVOPS],
            tasks=tasks,
        )

        state = await engine.run_workflow(definition)

        assert state.status == TaskStatus.COMPLETED
        assert state.completed_task_count == 2
        assert len(state.phase_history) == 2
        assert state.phase_history[0]["phase"] == "development"
        assert state.phase_history[1]["phase"] == "devops"

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: Task Failure Handling
# =============================================================================
class TestTaskFailureHandling:
    """Tests for how the engine handles task failures."""

    async def test_task_failure_recorded_in_state(self) -> None:
        """A failing task should be recorded as FAILED in workflow state.

        The workflow engine uses best-effort strategy: failing tasks are
        recorded but execution continues with remaining tasks.
        """
        engine, coordinator, bus, sm = await _create_engine(
            agents=[("coding-01", AgentType.CODING)],
            use_failing_agent=True,
        )

        task = TaskDefinition(name="Fail Task", assigned_to=AgentType.CODING)
        definition = WorkflowDefinition(
            name="Failing Workflow",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[task],
        )

        state = await engine.run_workflow(definition)

        # Workflow completes (best-effort) but the task is FAILED
        assert state.status == TaskStatus.COMPLETED
        assert state.failed_task_count == 1
        assert task.task_id in state.task_results
        assert state.task_results[task.task_id].status == TaskStatus.FAILED
        assert len(state.error_log) >= 1

        await coordinator.stop()
        await bus.disconnect()

    async def test_no_agent_failure_recorded(self) -> None:
        """If no agent exists for a task type, the failure should be recorded."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[],  # No agents registered
        )

        task = TaskDefinition(name="Orphan", assigned_to=AgentType.CODING)
        definition = WorkflowDefinition(
            name="No Agents",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[task],
        )

        state = await engine.run_workflow(definition)

        # Task should be recorded as FAILED (no available agent)
        assert task.task_id in state.task_results
        assert state.task_results[task.task_id].status == TaskStatus.FAILED
        assert len(state.error_log) >= 1

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: Empty Workflow / Phase
# =============================================================================
class TestEmptyWorkflow:
    """Tests for edge cases with empty workflows and phases."""

    async def test_empty_tasks_workflow(self) -> None:
        """A workflow with no tasks should still complete."""
        engine, coordinator, bus, sm = await _create_engine()

        definition = WorkflowDefinition(
            name="Empty Workflow",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[],
        )

        state = await engine.run_workflow(definition)

        assert state.status == TaskStatus.COMPLETED
        assert state.completed_task_count == 0

        await coordinator.stop()
        await bus.disconnect()

    async def test_phase_with_no_matching_tasks(self) -> None:
        """A phase with no matching tasks should be skipped."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[("coding-01", AgentType.CODING)],
        )

        # DEVOPS phase has no tasks (only CODING tasks exist)
        tasks = [TaskDefinition(name="Code", assigned_to=AgentType.CODING)]
        definition = WorkflowDefinition(
            name="Dev Only",
            phases=[WorkflowPhase.DEVELOPMENT, WorkflowPhase.DEVOPS],
            tasks=tasks,
        )

        state = await engine.run_workflow(definition)

        assert state.status == TaskStatus.COMPLETED
        assert len(state.phase_history) == 2
        # DEVOPS phase should be marked as skipped
        devops_phase = state.phase_history[1]
        assert devops_phase["phase"] == "devops"
        assert devops_phase["result"] == "skipped"

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: Workflow State Persistence
# =============================================================================
class TestWorkflowStatePersistence:
    """Tests for state persistence to StateManager."""

    async def test_workflow_state_persisted(self) -> None:
        """run_workflow should persist the final state to StateManager."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[("coding-01", AgentType.CODING)],
        )

        task = TaskDefinition(name="Code", assigned_to=AgentType.CODING)
        definition = WorkflowDefinition(
            name="Persist Test",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[task],
        )

        state = await engine.run_workflow(definition)

        # State should be in StateManager
        persisted = await sm.get_workflow_state(definition.workflow_id)
        assert persisted is not None
        assert persisted.status == TaskStatus.COMPLETED
        assert persisted.completed_task_count == 1

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: Phase Gate Check
# =============================================================================
class TestPhaseGateCheck:
    """Tests for the check_phase_gate method."""

    async def test_phase_gate_no_policy_engine(self) -> None:
        """Without a policy engine, phase gate should always pass."""
        engine, coordinator, bus, sm = await _create_engine()

        from conductor.core.state import WorkflowState
        state = WorkflowState(
            workflow_id="wf-01",
            status=TaskStatus.IN_PROGRESS,
        )

        result = await engine.check_phase_gate(state)
        assert result is True

        await coordinator.stop()
        await bus.disconnect()

    async def test_phase_gate_with_policy_engine(self) -> None:
        """With a PhaseGatePolicy, gate should check success rate."""
        engine, coordinator, bus, sm = await _create_engine(
            with_policy_engine=True,
        )
        engine._policy_engine.register_policy(
            PhaseGatePolicy(required_success_rate=0.8)
        )

        # Create a state with 100% success rate
        from conductor.core.state import WorkflowState
        state = WorkflowState(
            workflow_id="wf-01",
            status=TaskStatus.IN_PROGRESS,
            task_results={
                "t1": TaskResult(task_id="t1", agent_id="a", status=TaskStatus.COMPLETED),
                "t2": TaskResult(task_id="t2", agent_id="a", status=TaskStatus.COMPLETED),
            },
        )

        result = await engine.check_phase_gate(state)
        assert result is True

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: Feedback Loop
# =============================================================================
class TestFeedbackLoop:
    """Tests for the feedback loop mechanism."""

    async def test_feedback_loop_triggers(self) -> None:
        """trigger_feedback_loop should re-execute DEVELOPMENT phase."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[("coding-01", AgentType.CODING)],
        )

        # First run the workflow to get a state
        task = TaskDefinition(name="Code", assigned_to=AgentType.CODING)
        definition = WorkflowDefinition(
            name="Feedback Test",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[task],
        )
        state = await engine.run_workflow(definition)

        # Trigger feedback loop
        state = await engine.trigger_feedback_loop(
            state, definition, {"finding": "quality issue"}
        )

        assert state.feedback_count == 1
        assert state.current_phase == WorkflowPhase.DEVELOPMENT

        await coordinator.stop()
        await bus.disconnect()

    async def test_feedback_loop_max_exceeded(self) -> None:
        """Exceeding max feedback loops should raise WorkflowError."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[("coding-01", AgentType.CODING)],
            max_feedback_loops=2,
        )

        from conductor.core.state import WorkflowState
        state = WorkflowState(
            workflow_id="wf-01",
            status=TaskStatus.IN_PROGRESS,
            feedback_count=2,  # Already at max
        )

        definition = WorkflowDefinition(name="Test", tasks=[])

        with pytest.raises(WorkflowError) as exc_info:
            await engine.trigger_feedback_loop(state, definition, {})
        assert exc_info.value.error_code == "MAX_FEEDBACK_LOOPS"

        await coordinator.stop()
        await bus.disconnect()

    async def test_feedback_loop_increments_count(self) -> None:
        """Each feedback loop should increment the feedback_count."""
        engine, coordinator, bus, sm = await _create_engine(
            agents=[("coding-01", AgentType.CODING)],
            max_feedback_loops=5,
        )

        task = TaskDefinition(name="Code", assigned_to=AgentType.CODING)
        definition = WorkflowDefinition(
            name="Multi-Feedback",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[task],
        )
        state = await engine.run_workflow(definition)

        # Trigger two feedback loops
        state = await engine.trigger_feedback_loop(state, definition, {})
        assert state.feedback_count == 1

        state = await engine.trigger_feedback_loop(state, definition, {})
        assert state.feedback_count == 2

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: _get_phase_tasks
# =============================================================================
class TestGetPhaseTasks:
    """Tests for the static phase task filtering method."""

    def test_filters_coding_to_development(self) -> None:
        """CODING tasks should be in the DEVELOPMENT phase."""
        tasks = [
            TaskDefinition(name="Code", assigned_to=AgentType.CODING),
            TaskDefinition(name="Deploy", assigned_to=AgentType.DEVOPS),
        ]

        dev_tasks = WorkflowEngine._get_phase_tasks(tasks, WorkflowPhase.DEVELOPMENT)
        assert len(dev_tasks) == 1
        assert dev_tasks[0].name == "Code"

    def test_filters_devops_to_devops_phase(self) -> None:
        """DEVOPS tasks should be in the DEVOPS phase."""
        tasks = [
            TaskDefinition(name="Code", assigned_to=AgentType.CODING),
            TaskDefinition(name="Deploy", assigned_to=AgentType.DEVOPS),
        ]

        devops_tasks = WorkflowEngine._get_phase_tasks(tasks, WorkflowPhase.DEVOPS)
        assert len(devops_tasks) == 1
        assert devops_tasks[0].name == "Deploy"

    def test_empty_tasks_returns_empty(self) -> None:
        """Empty task list should return empty."""
        result = WorkflowEngine._get_phase_tasks([], WorkflowPhase.DEVELOPMENT)
        assert result == []

    def test_no_matching_tasks(self) -> None:
        """If no tasks match the phase, return empty list."""
        tasks = [TaskDefinition(name="Code", assigned_to=AgentType.CODING)]
        result = WorkflowEngine._get_phase_tasks(tasks, WorkflowPhase.MONITORING)
        assert result == []
