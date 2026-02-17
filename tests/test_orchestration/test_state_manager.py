"""
Tests for conductor.orchestration.state_manager — InMemoryStateManager
========================================================================

These tests verify the InMemoryStateManager implementation, which provides
the persistent state storage layer for ConductorAI during development/testing.

What's Being Tested:
    - Agent state CRUD:      save, get, delete, list operations
    - Workflow state CRUD:   save, get operations
    - Task result CRUD:      save, get operations
    - Connection lifecycle:  connect, disconnect, state cleanup
    - Edge cases:            missing keys, overwrite behavior, isolation

All tests are async (pytest-asyncio with asyncio_mode=auto).
No external dependencies required (pure in-memory).

Architecture Context:
    The State Manager sits alongside the Message Bus in the orchestration
    layer. While the Message Bus handles communication (write-heavy),
    the State Manager handles persistence (read-heavy):

        ┌──────────────┐     save/get      ┌──────────────────┐
        │  Agent        │ ──────────────→  │                   │
        │               │                   │  State Manager   │
        │               │ ←─────────────   │                   │
        └──────────────┘    AgentState     └──────────────────┘

    Key Schema:
        agent:{agent_id}          → AgentState
        workflow:{workflow_id}    → WorkflowState
        task_result:{task_id}     → TaskResult
"""

import pytest

from conductor.core.enums import AgentStatus, AgentType, TaskStatus, WorkflowPhase
from conductor.core.models import TaskResult
from conductor.core.state import AgentState, WorkflowState
from conductor.orchestration.state_manager import InMemoryStateManager, StateManager


# =============================================================================
# Helper: Factory functions for test entities
# =============================================================================
# These helpers create minimal, valid instances of each entity type for
# testing. They provide sensible defaults that can be overridden as needed.
# =============================================================================


def _make_agent_state(
    agent_id: str = "coding-01",
    agent_type: AgentType = AgentType.CODING,
    status: AgentStatus = AgentStatus.IDLE,
    **kwargs,
) -> AgentState:
    """Create an AgentState for testing.

    Args:
        agent_id: Unique agent identifier.
        agent_type: The type of agent (CODING, REVIEW, etc.).
        status: Current agent status (default: IDLE).
        **kwargs: Additional fields to set on the AgentState.

    Returns:
        A fresh AgentState instance.
    """
    return AgentState(
        agent_id=agent_id,
        agent_type=agent_type,
        status=status,
        **kwargs,
    )


def _make_workflow_state(
    workflow_id: str = "wf-01",
    current_phase: WorkflowPhase = WorkflowPhase.DEVELOPMENT,
    status: TaskStatus = TaskStatus.PENDING,
    **kwargs,
) -> WorkflowState:
    """Create a WorkflowState for testing.

    Args:
        workflow_id: Unique workflow identifier.
        current_phase: The current workflow phase (default: DEVELOPMENT).
        status: Current workflow status (default: PENDING).
        **kwargs: Additional fields to set on the WorkflowState.

    Returns:
        A fresh WorkflowState instance.
    """
    return WorkflowState(
        workflow_id=workflow_id,
        current_phase=current_phase,
        status=status,
        **kwargs,
    )


def _make_task_result(
    task_id: str = "task-01",
    agent_id: str = "coding-01",
    status: TaskStatus = TaskStatus.COMPLETED,
    **kwargs,
) -> TaskResult:
    """Create a TaskResult for testing.

    Args:
        task_id: Unique task identifier.
        agent_id: The agent that executed this task.
        status: Task execution status (default: COMPLETED).
        **kwargs: Additional fields to set on the TaskResult.

    Returns:
        A fresh TaskResult instance.
    """
    return TaskResult(
        task_id=task_id,
        agent_id=agent_id,
        status=status,
        **kwargs,
    )


# =============================================================================
# Test Class: InMemoryStateManager
# =============================================================================
class TestInMemoryStateManager:
    """Tests for the InMemoryStateManager implementation.

    Each test creates a fresh state manager instance to ensure isolation.
    Tests are organized by entity type: Agent State, Workflow State,
    Task Result, then Connection Lifecycle.
    """

    # -------------------------------------------------------------------------
    # Test: ABC conformance
    # -------------------------------------------------------------------------

    def test_is_state_manager(self) -> None:
        """InMemoryStateManager should be a subclass of StateManager ABC."""
        sm = InMemoryStateManager()
        assert isinstance(sm, StateManager), (
            "InMemoryStateManager must implement the StateManager interface"
        )

    # =========================================================================
    # Agent State Operations
    # =========================================================================

    # -------------------------------------------------------------------------
    # Test: save_agent_state + get_agent_state
    # -------------------------------------------------------------------------

    async def test_save_and_get_agent_state(self) -> None:
        """Saving an AgentState should make it retrievable by agent_id.

        Scenario:
            1. Create a state manager and connect
            2. Save an AgentState for "coding-01"
            3. Retrieve it using get_agent_state("coding-01")
            4. Verify the retrieved state matches the saved one

        This is the fundamental read-after-write test for agent state.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        state = _make_agent_state(
            agent_id="coding-01",
            agent_type=AgentType.CODING,
            status=AgentStatus.RUNNING,
        )
        await sm.save_agent_state(state)

        retrieved = await sm.get_agent_state("coding-01")

        assert retrieved is not None, "State should be retrievable after saving"
        assert retrieved.agent_id == "coding-01"
        assert retrieved.agent_type == AgentType.CODING
        assert retrieved.status == AgentStatus.RUNNING

        await sm.disconnect()

    async def test_get_agent_state_missing(self) -> None:
        """get_agent_state should return None for unknown agent_id.

        This is important for checking whether an agent has been registered
        before attempting to interact with it.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        result = await sm.get_agent_state("nonexistent-agent")

        assert result is None, (
            "get_agent_state should return None for unknown agent_id, "
            "not raise an exception"
        )

        await sm.disconnect()

    async def test_save_agent_state_overwrites(self) -> None:
        """Saving an AgentState with the same agent_id should overwrite.

        The state manager uses last-write-wins semantics. This is the
        expected behavior for agent state updates (e.g., status changes).
        """
        sm = InMemoryStateManager()
        await sm.connect()

        # Save initial state (IDLE)
        initial = _make_agent_state(
            agent_id="coding-01",
            status=AgentStatus.IDLE,
        )
        await sm.save_agent_state(initial)

        # Overwrite with updated state (RUNNING)
        updated = _make_agent_state(
            agent_id="coding-01",
            status=AgentStatus.RUNNING,
        )
        await sm.save_agent_state(updated)

        # The latest save should win
        retrieved = await sm.get_agent_state("coding-01")
        assert retrieved is not None
        assert retrieved.status == AgentStatus.RUNNING, (
            "State should reflect the most recent save (last-write-wins)"
        )

        await sm.disconnect()

    async def test_save_multiple_agents(self) -> None:
        """Multiple agents' states should be stored independently.

        Saving state for one agent should not affect another agent's state.
        This validates key-based isolation in the state store.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        state_a = _make_agent_state(agent_id="coding-01", agent_type=AgentType.CODING)
        state_b = _make_agent_state(agent_id="review-01", agent_type=AgentType.REVIEW)
        state_c = _make_agent_state(agent_id="test-01", agent_type=AgentType.TEST)

        await sm.save_agent_state(state_a)
        await sm.save_agent_state(state_b)
        await sm.save_agent_state(state_c)

        # Each agent's state should be independently retrievable
        retrieved_a = await sm.get_agent_state("coding-01")
        retrieved_b = await sm.get_agent_state("review-01")
        retrieved_c = await sm.get_agent_state("test-01")

        assert retrieved_a is not None and retrieved_a.agent_type == AgentType.CODING
        assert retrieved_b is not None and retrieved_b.agent_type == AgentType.REVIEW
        assert retrieved_c is not None and retrieved_c.agent_type == AgentType.TEST

        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: delete_agent_state
    # -------------------------------------------------------------------------

    async def test_delete_agent_state_existing(self) -> None:
        """Deleting an existing agent state should return True and remove it.

        After deletion, get_agent_state should return None for that agent_id.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        state = _make_agent_state(agent_id="coding-01")
        await sm.save_agent_state(state)

        # Delete should succeed and return True
        deleted = await sm.delete_agent_state("coding-01")
        assert deleted is True, "delete should return True for existing state"

        # State should no longer be retrievable
        retrieved = await sm.get_agent_state("coding-01")
        assert retrieved is None, (
            "State should be gone after deletion"
        )

        await sm.disconnect()

    async def test_delete_agent_state_nonexistent(self) -> None:
        """Deleting a nonexistent agent state should return False.

        This ensures the method is safe to call even for agents that
        were never registered (idempotent behavior).
        """
        sm = InMemoryStateManager()
        await sm.connect()

        deleted = await sm.delete_agent_state("nonexistent-agent")
        assert deleted is False, (
            "delete should return False when agent_id is not found"
        )

        await sm.disconnect()

    async def test_delete_does_not_affect_other_agents(self) -> None:
        """Deleting one agent's state should not affect other agents.

        This validates that deletion is scoped to the specified agent_id.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        state_a = _make_agent_state(agent_id="agent-a")
        state_b = _make_agent_state(agent_id="agent-b")
        await sm.save_agent_state(state_a)
        await sm.save_agent_state(state_b)

        # Delete only agent-a
        await sm.delete_agent_state("agent-a")

        # agent-a should be gone
        assert await sm.get_agent_state("agent-a") is None
        # agent-b should still exist
        assert await sm.get_agent_state("agent-b") is not None

        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: list_agent_states
    # -------------------------------------------------------------------------

    async def test_list_agent_states_empty(self) -> None:
        """list_agent_states should return an empty list when no agents stored."""
        sm = InMemoryStateManager()
        await sm.connect()

        states = await sm.list_agent_states()

        assert states == [], "Should return empty list when no agents exist"

        await sm.disconnect()

    async def test_list_agent_states_multiple(self) -> None:
        """list_agent_states should return all stored agent states.

        The returned list should contain exactly the states that were saved,
        regardless of order.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        state_a = _make_agent_state(agent_id="coding-01", agent_type=AgentType.CODING)
        state_b = _make_agent_state(agent_id="review-01", agent_type=AgentType.REVIEW)
        state_c = _make_agent_state(agent_id="test-01", agent_type=AgentType.TEST)

        await sm.save_agent_state(state_a)
        await sm.save_agent_state(state_b)
        await sm.save_agent_state(state_c)

        states = await sm.list_agent_states()

        assert len(states) == 3, "Should return all 3 stored agent states"

        # Verify all agent_ids are present (order not guaranteed)
        agent_ids = {s.agent_id for s in states}
        assert agent_ids == {"coding-01", "review-01", "test-01"}

        await sm.disconnect()

    async def test_list_agent_states_reflects_deletions(self) -> None:
        """list_agent_states should not include deleted agents."""
        sm = InMemoryStateManager()
        await sm.connect()

        await sm.save_agent_state(_make_agent_state(agent_id="agent-a"))
        await sm.save_agent_state(_make_agent_state(agent_id="agent-b"))

        # Delete one
        await sm.delete_agent_state("agent-a")

        states = await sm.list_agent_states()
        assert len(states) == 1
        assert states[0].agent_id == "agent-b"

        await sm.disconnect()

    # =========================================================================
    # Workflow State Operations
    # =========================================================================

    async def test_save_and_get_workflow_state(self) -> None:
        """Saving a WorkflowState should make it retrievable by workflow_id.

        Scenario:
            1. Save a WorkflowState for "wf-01"
            2. Retrieve it using get_workflow_state("wf-01")
            3. Verify all fields match

        This is the fundamental read-after-write test for workflow state.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        state = _make_workflow_state(
            workflow_id="wf-01",
            current_phase=WorkflowPhase.DEVOPS,
            status=TaskStatus.IN_PROGRESS,
        )
        await sm.save_workflow_state(state)

        retrieved = await sm.get_workflow_state("wf-01")

        assert retrieved is not None, "Workflow state should be retrievable"
        assert retrieved.workflow_id == "wf-01"
        assert retrieved.current_phase == WorkflowPhase.DEVOPS
        assert retrieved.status == TaskStatus.IN_PROGRESS

        await sm.disconnect()

    async def test_get_workflow_state_missing(self) -> None:
        """get_workflow_state should return None for unknown workflow_id."""
        sm = InMemoryStateManager()
        await sm.connect()

        result = await sm.get_workflow_state("nonexistent-wf")

        assert result is None, (
            "get_workflow_state should return None for unknown workflow_id"
        )

        await sm.disconnect()

    async def test_save_workflow_state_overwrites(self) -> None:
        """Saving a WorkflowState with the same ID should overwrite.

        This is used when advancing workflow phases or updating status.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        # Save initial state (DEVELOPMENT phase)
        initial = _make_workflow_state(
            workflow_id="wf-01",
            current_phase=WorkflowPhase.DEVELOPMENT,
            status=TaskStatus.IN_PROGRESS,
        )
        await sm.save_workflow_state(initial)

        # Overwrite with updated state (DEVOPS phase)
        updated = _make_workflow_state(
            workflow_id="wf-01",
            current_phase=WorkflowPhase.DEVOPS,
            status=TaskStatus.IN_PROGRESS,
        )
        await sm.save_workflow_state(updated)

        retrieved = await sm.get_workflow_state("wf-01")
        assert retrieved is not None
        assert retrieved.current_phase == WorkflowPhase.DEVOPS, (
            "Workflow state should reflect the most recent save"
        )

        await sm.disconnect()

    async def test_multiple_workflows_independent(self) -> None:
        """Multiple workflows' states should be stored independently."""
        sm = InMemoryStateManager()
        await sm.connect()

        state_a = _make_workflow_state(workflow_id="wf-a", status=TaskStatus.PENDING)
        state_b = _make_workflow_state(workflow_id="wf-b", status=TaskStatus.IN_PROGRESS)

        await sm.save_workflow_state(state_a)
        await sm.save_workflow_state(state_b)

        retrieved_a = await sm.get_workflow_state("wf-a")
        retrieved_b = await sm.get_workflow_state("wf-b")

        assert retrieved_a is not None and retrieved_a.status == TaskStatus.PENDING
        assert retrieved_b is not None and retrieved_b.status == TaskStatus.IN_PROGRESS

        await sm.disconnect()

    # =========================================================================
    # Task Result Operations
    # =========================================================================

    async def test_save_and_get_task_result(self) -> None:
        """Saving a TaskResult should make it retrievable by task_id.

        Scenario:
            1. Save a TaskResult for "task-01"
            2. Retrieve it using get_task_result("task-01")
            3. Verify all fields match

        Task results are stored after each agent completes a task,
        allowing the workflow engine to track progress.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        result = _make_task_result(
            task_id="task-01",
            agent_id="coding-01",
            status=TaskStatus.COMPLETED,
            output_data={"code": "def hello(): pass"},
        )
        await sm.save_task_result(result)

        retrieved = await sm.get_task_result("task-01")

        assert retrieved is not None, "Task result should be retrievable"
        assert retrieved.task_id == "task-01"
        assert retrieved.agent_id == "coding-01"
        assert retrieved.status == TaskStatus.COMPLETED
        assert retrieved.output_data["code"] == "def hello(): pass"

        await sm.disconnect()

    async def test_get_task_result_missing(self) -> None:
        """get_task_result should return None for unknown task_id."""
        sm = InMemoryStateManager()
        await sm.connect()

        result = await sm.get_task_result("nonexistent-task")

        assert result is None, (
            "get_task_result should return None for unknown task_id"
        )

        await sm.disconnect()

    async def test_save_task_result_overwrites(self) -> None:
        """Saving a TaskResult with the same task_id should overwrite.

        This allows updating a task result (e.g., after a retry).
        """
        sm = InMemoryStateManager()
        await sm.connect()

        # Save initial result (FAILED)
        initial = _make_task_result(
            task_id="task-01",
            status=TaskStatus.FAILED,
        )
        await sm.save_task_result(initial)

        # Overwrite with successful result after retry
        updated = _make_task_result(
            task_id="task-01",
            status=TaskStatus.COMPLETED,
        )
        await sm.save_task_result(updated)

        retrieved = await sm.get_task_result("task-01")
        assert retrieved is not None
        assert retrieved.status == TaskStatus.COMPLETED, (
            "Task result should reflect the most recent save"
        )

        await sm.disconnect()

    async def test_multiple_task_results_independent(self) -> None:
        """Multiple task results should be stored independently."""
        sm = InMemoryStateManager()
        await sm.connect()

        result_a = _make_task_result(task_id="task-a", agent_id="coding-01")
        result_b = _make_task_result(task_id="task-b", agent_id="review-01")

        await sm.save_task_result(result_a)
        await sm.save_task_result(result_b)

        retrieved_a = await sm.get_task_result("task-a")
        retrieved_b = await sm.get_task_result("task-b")

        assert retrieved_a is not None and retrieved_a.agent_id == "coding-01"
        assert retrieved_b is not None and retrieved_b.agent_id == "review-01"

        await sm.disconnect()

    # =========================================================================
    # Connection Lifecycle
    # =========================================================================

    async def test_connect_sets_connected(self) -> None:
        """connect() should mark the state manager as connected."""
        sm = InMemoryStateManager()

        # Start disconnected
        assert sm._connected is False

        await sm.connect()
        assert sm._connected is True

        await sm.disconnect()

    async def test_disconnect_clears_all_state(self) -> None:
        """disconnect() should clear all stored state.

        After disconnecting, all agent states, workflow states, and task
        results should be gone. This prevents stale data from persisting
        across sessions.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        # Store some data in all three categories
        await sm.save_agent_state(_make_agent_state(agent_id="agent-01"))
        await sm.save_workflow_state(_make_workflow_state(workflow_id="wf-01"))
        await sm.save_task_result(_make_task_result(task_id="task-01"))

        # Disconnect should clear everything
        await sm.disconnect()

        assert sm._connected is False

        # Reconnect and verify all state is gone
        await sm.connect()

        assert await sm.get_agent_state("agent-01") is None, (
            "Agent state should be cleared after disconnect"
        )
        assert await sm.get_workflow_state("wf-01") is None, (
            "Workflow state should be cleared after disconnect"
        )
        assert await sm.get_task_result("task-01") is None, (
            "Task result should be cleared after disconnect"
        )
        assert await sm.list_agent_states() == [], (
            "Agent state list should be empty after disconnect"
        )

        await sm.disconnect()

    async def test_connect_is_idempotent(self) -> None:
        """Calling connect() multiple times should be safe.

        Each connect() call should work without error. The state manager
        preserves existing data when reconnecting (unlike the message bus
        which resets on reconnect).
        """
        sm = InMemoryStateManager()

        await sm.connect()
        assert sm._connected is True

        # Second connect should also work
        await sm.connect()
        assert sm._connected is True

        await sm.disconnect()

    async def test_disconnect_is_idempotent(self) -> None:
        """Calling disconnect() multiple times should be safe.

        Disconnecting an already-disconnected state manager should not
        raise an error.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        # First disconnect
        await sm.disconnect()
        assert sm._connected is False

        # Second disconnect should also work
        await sm.disconnect()
        assert sm._connected is False

    # =========================================================================
    # Cross-Entity Isolation
    # =========================================================================

    async def test_entity_types_are_isolated(self) -> None:
        """Agent states, workflow states, and task results should be isolated.

        Saving an agent state should not affect workflow states or task
        results, and vice versa. This verifies that the three entity types
        use independent storage dicts.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        # Save one entity of each type
        await sm.save_agent_state(
            _make_agent_state(agent_id="shared-id-01")
        )
        await sm.save_workflow_state(
            _make_workflow_state(workflow_id="shared-id-01")
        )
        await sm.save_task_result(
            _make_task_result(task_id="shared-id-01")
        )

        # Each should be independently retrievable via its own method
        agent = await sm.get_agent_state("shared-id-01")
        workflow = await sm.get_workflow_state("shared-id-01")
        task = await sm.get_task_result("shared-id-01")

        assert agent is not None, "Agent state should exist"
        assert workflow is not None, "Workflow state should exist"
        assert task is not None, "Task result should exist"

        # They should be different types even though they share an ID
        assert isinstance(agent, AgentState)
        assert isinstance(workflow, WorkflowState)
        assert isinstance(task, TaskResult)

        # Deleting the agent state should NOT affect workflow or task
        await sm.delete_agent_state("shared-id-01")

        assert await sm.get_agent_state("shared-id-01") is None
        assert await sm.get_workflow_state("shared-id-01") is not None
        assert await sm.get_task_result("shared-id-01") is not None

        await sm.disconnect()

    # =========================================================================
    # State with Rich Data
    # =========================================================================

    async def test_save_agent_state_with_task_history(self) -> None:
        """AgentState with completed/failed task lists should persist correctly.

        This validates that list fields and computed properties survive
        the save-retrieve cycle.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        state = _make_agent_state(
            agent_id="coding-01",
            agent_type=AgentType.CODING,
            status=AgentStatus.IDLE,
            completed_tasks=["task-1", "task-2", "task-3"],
            failed_tasks=["task-4"],
            error_count=1,
        )
        await sm.save_agent_state(state)

        retrieved = await sm.get_agent_state("coding-01")
        assert retrieved is not None
        assert retrieved.completed_tasks == ["task-1", "task-2", "task-3"]
        assert retrieved.failed_tasks == ["task-4"]
        assert retrieved.error_count == 1
        # Computed properties should work on retrieved state
        assert retrieved.total_tasks == 4
        assert retrieved.success_rate == 0.75

        await sm.disconnect()

    async def test_save_workflow_state_with_task_results(self) -> None:
        """WorkflowState with embedded task results should persist correctly.

        This validates that nested Pydantic models (TaskResult inside
        WorkflowState.task_results dict) survive the save-retrieve cycle.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        state = _make_workflow_state(
            workflow_id="wf-01",
            current_phase=WorkflowPhase.MONITORING,
            status=TaskStatus.IN_PROGRESS,
        )
        # Add task results to the workflow state
        state_with_results = state.model_copy(
            update={
                "task_results": {
                    "t1": TaskResult(
                        task_id="t1",
                        agent_id="coding-01",
                        status=TaskStatus.COMPLETED,
                    ),
                    "t2": TaskResult(
                        task_id="t2",
                        agent_id="review-01",
                        status=TaskStatus.FAILED,
                    ),
                },
                "feedback_count": 2,
            }
        )
        await sm.save_workflow_state(state_with_results)

        retrieved = await sm.get_workflow_state("wf-01")
        assert retrieved is not None
        assert retrieved.current_phase == WorkflowPhase.MONITORING
        assert len(retrieved.task_results) == 2
        assert retrieved.completed_task_count == 1
        assert retrieved.failed_task_count == 1
        assert retrieved.feedback_count == 2

        await sm.disconnect()

    async def test_save_task_result_with_output_data(self) -> None:
        """TaskResult with complex output_data should persist correctly.

        The output_data dict can contain any JSON-serializable data,
        including nested dicts and lists.
        """
        sm = InMemoryStateManager()
        await sm.connect()

        result = _make_task_result(
            task_id="task-code-01",
            agent_id="coding-01",
            status=TaskStatus.COMPLETED,
            output_data={
                "files_created": ["src/api.py", "src/models.py"],
                "lines_of_code": 150,
                "review_needed": True,
            },
        )
        await sm.save_task_result(result)

        retrieved = await sm.get_task_result("task-code-01")
        assert retrieved is not None
        assert retrieved.output_data["files_created"] == [
            "src/api.py", "src/models.py"
        ]
        assert retrieved.output_data["lines_of_code"] == 150
        assert retrieved.output_data["review_needed"] is True

        await sm.disconnect()
