"""
Tests for conductor.orchestration.agent_coordinator
=====================================================

These tests verify the AgentCoordinator — the central registry and dispatcher
that manages agent lifecycle and task assignment.

What's Being Tested:
    - Agent registration/unregistration lifecycle
    - Agent queries (by type, by availability)
    - Task dispatch (happy path, no agents, policy violations)
    - State synchronization with StateManager
    - Error handler integration
    - Coordinator start/stop lifecycle

All tests use a MockAgent (concrete BaseAgent subclass) for isolation.
"""

import pytest

from conductor.agents.base import BaseAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentStatus, AgentType, TaskStatus
from conductor.core.exceptions import AgentError
from conductor.core.models import TaskDefinition, TaskResult
from conductor.orchestration.agent_coordinator import AgentCoordinator
from conductor.orchestration.error_handler import ErrorHandler
from conductor.orchestration.message_bus import InMemoryMessageBus
from conductor.orchestration.policy_engine import (
    AgentAvailabilityPolicy,
    MaxConcurrentTasksPolicy,
    PolicyEngine,
)
from conductor.orchestration.state_manager import InMemoryStateManager


# =============================================================================
# Mock Agent: Concrete BaseAgent for Testing
# =============================================================================
class MockAgent(BaseAgent):
    """A simple mock agent that always succeeds.

    Accepts any task and returns a COMPLETED result with the input_data
    echoed in the output. Used for testing coordinator dispatch logic
    without needing real LLM calls.
    """

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Accept all tasks."""
        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Return a successful result echoing the input."""
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={"echo": task.input_data},
        )


class FailingAgent(BaseAgent):
    """A mock agent that always fails execution."""

    async def _validate_task(self, task: TaskDefinition) -> bool:
        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        raise RuntimeError("Agent execution failed!")


class RejectingAgent(BaseAgent):
    """A mock agent that rejects all tasks during validation."""

    async def _validate_task(self, task: TaskDefinition) -> bool:
        return False

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={},
        )


# =============================================================================
# Fixtures
# =============================================================================
def _config() -> ConductorConfig:
    return ConductorConfig()


async def _create_coordinator(
    with_policy_engine: bool = False,
    with_error_handler: bool = False,
) -> tuple[AgentCoordinator, InMemoryMessageBus, InMemoryStateManager]:
    """Create a connected AgentCoordinator with fresh dependencies."""
    bus = InMemoryMessageBus()
    sm = InMemoryStateManager()
    await bus.connect()
    await sm.connect()

    pe = PolicyEngine() if with_policy_engine else None
    eh = ErrorHandler(bus, sm) if with_error_handler else None

    coordinator = AgentCoordinator(bus, sm, pe, eh)
    await coordinator.start()
    return coordinator, bus, sm


# =============================================================================
# Tests: Coordinator Lifecycle
# =============================================================================
class TestCoordinatorLifecycle:
    """Tests for coordinator start/stop."""

    async def test_start(self) -> None:
        """Coordinator should be started after start()."""
        coordinator, bus, sm = await _create_coordinator()
        assert coordinator.is_started is True
        assert coordinator.agent_count == 0
        await coordinator.stop()
        await bus.disconnect()

    async def test_stop_clears_agents(self) -> None:
        """stop() should stop all agents and clear the registry."""
        coordinator, bus, sm = await _create_coordinator()

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)
        assert coordinator.agent_count == 1

        await coordinator.stop()
        assert coordinator.agent_count == 0
        assert coordinator.is_started is False

        await bus.disconnect()


# =============================================================================
# Tests: Agent Registration
# =============================================================================
class TestAgentRegistration:
    """Tests for register_agent and unregister_agent."""

    async def test_register_agent(self) -> None:
        """register_agent should add the agent and start it."""
        coordinator, bus, sm = await _create_coordinator()

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        assert coordinator.agent_count == 1
        assert coordinator.get_agent("coding-01") is agent
        assert agent.status == AgentStatus.IDLE

        await coordinator.stop()
        await bus.disconnect()

    async def test_register_persists_state(self) -> None:
        """register_agent should persist the agent state to StateManager."""
        coordinator, bus, sm = await _create_coordinator()

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        # State should be in StateManager
        persisted = await sm.get_agent_state("coding-01")
        assert persisted is not None
        assert persisted.agent_id == "coding-01"
        assert persisted.status == AgentStatus.IDLE

        await coordinator.stop()
        await bus.disconnect()

    async def test_register_duplicate_raises(self) -> None:
        """Registering the same agent_id twice should raise AgentError."""
        coordinator, bus, sm = await _create_coordinator()

        agent1 = MockAgent("coding-01", AgentType.CODING, _config())
        agent2 = MockAgent("coding-01", AgentType.CODING, _config())

        await coordinator.register_agent(agent1)

        with pytest.raises(AgentError) as exc_info:
            await coordinator.register_agent(agent2)
        assert exc_info.value.error_code == "AGENT_ALREADY_REGISTERED"

        await coordinator.stop()
        await bus.disconnect()

    async def test_register_multiple_agents(self) -> None:
        """Multiple agents of different types should register independently."""
        coordinator, bus, sm = await _create_coordinator()

        coding = MockAgent("coding-01", AgentType.CODING, _config())
        review = MockAgent("review-01", AgentType.REVIEW, _config())
        test = MockAgent("test-01", AgentType.TEST, _config())

        await coordinator.register_agent(coding)
        await coordinator.register_agent(review)
        await coordinator.register_agent(test)

        assert coordinator.agent_count == 3

        await coordinator.stop()
        await bus.disconnect()

    async def test_unregister_agent(self) -> None:
        """unregister_agent should remove the agent and clean up state."""
        coordinator, bus, sm = await _create_coordinator()

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        result = await coordinator.unregister_agent("coding-01")

        assert result is True
        assert coordinator.agent_count == 0
        assert coordinator.get_agent("coding-01") is None

        # State should be removed from StateManager
        persisted = await sm.get_agent_state("coding-01")
        assert persisted is None

        await coordinator.stop()
        await bus.disconnect()

    async def test_unregister_nonexistent_returns_false(self) -> None:
        """Unregistering an unknown agent_id should return False."""
        coordinator, bus, sm = await _create_coordinator()

        result = await coordinator.unregister_agent("nonexistent")
        assert result is False

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: Agent Queries
# =============================================================================
class TestAgentQueries:
    """Tests for agent lookup and filtering."""

    async def test_get_agents_by_type(self) -> None:
        """get_agents_by_type should return agents matching the type."""
        coordinator, bus, sm = await _create_coordinator()

        c1 = MockAgent("coding-01", AgentType.CODING, _config())
        c2 = MockAgent("coding-02", AgentType.CODING, _config())
        r1 = MockAgent("review-01", AgentType.REVIEW, _config())

        await coordinator.register_agent(c1)
        await coordinator.register_agent(c2)
        await coordinator.register_agent(r1)

        coding_agents = coordinator.get_agents_by_type(AgentType.CODING)
        assert len(coding_agents) == 2

        review_agents = coordinator.get_agents_by_type(AgentType.REVIEW)
        assert len(review_agents) == 1

        devops_agents = coordinator.get_agents_by_type(AgentType.DEVOPS)
        assert len(devops_agents) == 0

        await coordinator.stop()
        await bus.disconnect()

    async def test_get_available_agents(self) -> None:
        """get_available_agents should return only IDLE agents."""
        coordinator, bus, sm = await _create_coordinator()

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        # Agent starts IDLE → should be available
        available = coordinator.get_available_agents(AgentType.CODING)
        assert len(available) == 1

        await coordinator.stop()
        await bus.disconnect()

    async def test_get_available_agents_filters_by_type(self) -> None:
        """get_available_agents with type filter should only return that type."""
        coordinator, bus, sm = await _create_coordinator()

        coding = MockAgent("coding-01", AgentType.CODING, _config())
        review = MockAgent("review-01", AgentType.REVIEW, _config())

        await coordinator.register_agent(coding)
        await coordinator.register_agent(review)

        coding_avail = coordinator.get_available_agents(AgentType.CODING)
        assert len(coding_avail) == 1
        assert coding_avail[0].agent_id == "coding-01"

        await coordinator.stop()
        await bus.disconnect()

    async def test_list_agents(self) -> None:
        """list_agents should return all registered agents."""
        coordinator, bus, sm = await _create_coordinator()

        c = MockAgent("coding-01", AgentType.CODING, _config())
        r = MockAgent("review-01", AgentType.REVIEW, _config())
        await coordinator.register_agent(c)
        await coordinator.register_agent(r)

        all_agents = coordinator.list_agents()
        assert len(all_agents) == 2

        await coordinator.stop()
        await bus.disconnect()


# =============================================================================
# Tests: Task Dispatch
# =============================================================================
class TestTaskDispatch:
    """Tests for dispatch_task — the core coordination logic."""

    async def test_dispatch_task_success(self) -> None:
        """dispatch_task should execute the task and return a result."""
        coordinator, bus, sm = await _create_coordinator()

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        task = TaskDefinition(
            name="Generate API",
            assigned_to=AgentType.CODING,
            input_data={"spec": "REST API"},
        )

        result = await coordinator.dispatch_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "coding-01"
        assert result.output_data["echo"] == {"spec": "REST API"}

        await coordinator.stop()
        await bus.disconnect()

    async def test_dispatch_saves_task_result(self) -> None:
        """dispatch_task should persist the TaskResult to StateManager."""
        coordinator, bus, sm = await _create_coordinator()

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        task = TaskDefinition(name="Test", assigned_to=AgentType.CODING)
        result = await coordinator.dispatch_task(task)

        # Result should be in StateManager
        persisted = await sm.get_task_result(task.task_id)
        assert persisted is not None
        assert persisted.status == TaskStatus.COMPLETED

        await coordinator.stop()
        await bus.disconnect()

    async def test_dispatch_no_agent_type_raises(self) -> None:
        """dispatch_task with no assigned_to should raise AgentError."""
        coordinator, bus, sm = await _create_coordinator()

        task = TaskDefinition(name="No type", assigned_to=None)

        with pytest.raises(AgentError) as exc_info:
            await coordinator.dispatch_task(task)
        assert exc_info.value.error_code == "NO_AGENT_TYPE"

        await coordinator.stop()
        await bus.disconnect()

    async def test_dispatch_no_available_agent_raises(self) -> None:
        """dispatch_task with no available agents should raise AgentError."""
        coordinator, bus, sm = await _create_coordinator()

        # No agents registered
        task = TaskDefinition(name="Test", assigned_to=AgentType.CODING)

        with pytest.raises(AgentError) as exc_info:
            await coordinator.dispatch_task(task)
        assert exc_info.value.error_code == "NO_AVAILABLE_AGENT"

        await coordinator.stop()
        await bus.disconnect()

    async def test_dispatch_agent_failure_returns_failed_result(self) -> None:
        """dispatch_task should return a FAILED result when agent execution fails.

        BaseAgent's Template Method pattern catches non-AgentError exceptions
        in _execute() and wraps them into a FAILED TaskResult instead of
        re-raising. This is by design: the agent layer converts raw exceptions
        into structured results so the orchestration layer can handle them
        uniformly without try/except around every dispatch.
        """
        coordinator, bus, sm = await _create_coordinator()

        agent = FailingAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        task = TaskDefinition(name="Fail", assigned_to=AgentType.CODING)

        # FailingAgent raises RuntimeError in _execute(), but BaseAgent catches
        # it and returns a FAILED TaskResult — no exception propagates.
        result = await coordinator.dispatch_task(task)

        assert result.status == TaskStatus.FAILED
        assert "Agent execution failed!" in result.error_message
        assert result.agent_id == "coding-01"

        # The result should also be persisted to StateManager
        persisted = await sm.get_task_result(task.task_id)
        assert persisted is not None
        assert persisted.status == TaskStatus.FAILED

        await coordinator.stop()
        await bus.disconnect()

    async def test_dispatch_syncs_state_after_success(self) -> None:
        """After successful dispatch, agent state should be synced."""
        coordinator, bus, sm = await _create_coordinator()

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        task = TaskDefinition(name="Test", assigned_to=AgentType.CODING)
        await coordinator.dispatch_task(task)

        # Agent should be back to IDLE and have the task in completed_tasks
        persisted = await sm.get_agent_state("coding-01")
        assert persisted is not None
        assert persisted.status == AgentStatus.IDLE
        assert task.task_id in persisted.completed_tasks

        await coordinator.stop()
        await bus.disconnect()

    async def test_dispatch_with_policy_engine(self) -> None:
        """dispatch_task should respect PolicyEngine checks."""
        coordinator, bus, sm = await _create_coordinator(with_policy_engine=True)

        # Register a policy that limits to 0 concurrent tasks
        coordinator._policy_engine.register_policy(
            MaxConcurrentTasksPolicy(max_tasks=0)
        )

        agent = MockAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        task = TaskDefinition(name="Test", assigned_to=AgentType.CODING)

        with pytest.raises(AgentError) as exc_info:
            await coordinator.dispatch_task(task)
        assert exc_info.value.error_code == "POLICY_VIOLATION"

        await coordinator.stop()
        await bus.disconnect()

    async def test_dispatch_with_error_handler_on_failed_result(self) -> None:
        """dispatch_task with error_handler returns FAILED result for agent failures.

        When a FailingAgent's _execute() raises RuntimeError, BaseAgent catches
        it and returns a FAILED TaskResult. The coordinator's try block processes
        this result normally (no exception reaches the except block).

        The error handler is NOT invoked here because no exception propagates
        to the coordinator — the failure is contained within the TaskResult.
        The error handler only fires for exceptions that escape execute_task()
        (like AgentError from validation failures).

        This test verifies the coordinator correctly:
        1. Returns a FAILED TaskResult (not an exception).
        2. Persists the result to StateManager.
        3. The agent's internal error_count is incremented by BaseAgent.
        """
        coordinator, bus, sm = await _create_coordinator(with_error_handler=True)

        agent = FailingAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        task = TaskDefinition(name="Fail", assigned_to=AgentType.CODING)

        # No exception — BaseAgent catches RuntimeError, returns FAILED result
        result = await coordinator.dispatch_task(task)
        assert result.status == TaskStatus.FAILED

        # The agent's internal state tracks the failure (BaseAgent increments)
        assert agent.state.error_count == 1
        assert task.task_id in agent.state.failed_tasks

        # The result is persisted
        persisted = await sm.get_task_result(task.task_id)
        assert persisted.status == TaskStatus.FAILED

        await coordinator.stop()
        await bus.disconnect()

    async def test_dispatch_validation_failure_raises(self) -> None:
        """Task validation failure should raise AgentError."""
        coordinator, bus, sm = await _create_coordinator()

        agent = RejectingAgent("coding-01", AgentType.CODING, _config())
        await coordinator.register_agent(agent)

        task = TaskDefinition(name="Test", assigned_to=AgentType.CODING)

        with pytest.raises(AgentError) as exc_info:
            await coordinator.dispatch_task(task)
        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"

        await coordinator.stop()
        await bus.disconnect()
