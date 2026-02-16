"""
Tests for conductor.agents.base - BaseAgent
=============================================

These tests use a MockAgent implementation to verify BaseAgent's
template method pattern:
    - Agent lifecycle (start → execute → stop)
    - Task execution success and failure paths
    - State transitions (IDLE → RUNNING → IDLE)
    - Heartbeat functionality
    - Message handling

Since BaseAgent is abstract, we create a concrete MockAgent for testing.
"""

from datetime import datetime, timezone

import pytest

from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentStatus, AgentType, MessageType, TaskStatus
from conductor.core.exceptions import AgentError
from conductor.core.messages import AgentMessage, TaskAssignmentPayload
from conductor.core.models import TaskDefinition, TaskResult
from conductor.agents.base import BaseAgent


# =============================================================================
# MockAgent: Concrete implementation for testing
# =============================================================================
# This agent has configurable behavior so we can test both success and
# failure scenarios.
# =============================================================================
class MockAgent(BaseAgent):
    """A mock agent for testing BaseAgent behavior.

    Configuration:
        should_fail: If True, _execute() raises an exception.
        validate_result: What _validate_task() returns (True/False).
        execute_output: The output dict that _execute() returns on success.
        on_start_called: Flag to verify _on_start() was called.
        on_stop_called: Flag to verify _on_stop() was called.
    """

    def __init__(
        self,
        agent_id: str = "mock-01",
        agent_type: AgentType = AgentType.CODING,
        should_fail: bool = False,
        validate_result: bool = True,
        execute_output: dict | None = None,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=agent_type,
            config=ConductorConfig(),
            name="Test Mock Agent",
            description="A mock agent for unit testing",
        )
        self.should_fail = should_fail
        self.validate_result = validate_result
        self.execute_output = execute_output or {"result": "mock output"}
        self.on_start_called = False
        self.on_stop_called = False

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Return the configured validation result."""
        return self.validate_result

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Execute with configurable success/failure."""
        if self.should_fail:
            raise RuntimeError("Mock agent intentional failure")
        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output=self.execute_output,
        )

    async def _on_start(self) -> None:
        """Track that _on_start was called."""
        self.on_start_called = True

    async def _on_stop(self) -> None:
        """Track that _on_stop was called."""
        self.on_stop_called = True


# =============================================================================
# Test: Agent Initialization
# =============================================================================
class TestAgentInitialization:
    """Tests for BaseAgent.__init__ and properties."""

    def test_agent_creates_with_identity(self) -> None:
        """Agent should have identity with correct type and ID."""
        agent = MockAgent(agent_id="test-01", agent_type=AgentType.REVIEW)
        assert agent.agent_id == "test-01"
        assert agent.agent_type == AgentType.REVIEW
        assert agent.identity.name == "Test Mock Agent"

    def test_agent_starts_in_idle_state(self) -> None:
        """New agent should have IDLE status."""
        agent = MockAgent()
        assert agent.status == AgentStatus.IDLE

    def test_agent_state_has_correct_type(self) -> None:
        """Agent state should have the same type as identity."""
        agent = MockAgent(agent_type=AgentType.DEVOPS)
        assert agent.state.agent_type == AgentType.DEVOPS

    def test_agent_repr(self) -> None:
        """__repr__ should include useful debugging information."""
        agent = MockAgent(agent_id="coding-01", agent_type=AgentType.CODING)
        repr_str = repr(agent)
        assert "MockAgent" in repr_str
        assert "coding-01" in repr_str
        assert "coding" in repr_str


# =============================================================================
# Test: Agent Lifecycle (start / stop)
# =============================================================================
class TestAgentLifecycle:
    """Tests for agent start() and stop() methods."""

    async def test_start_sets_idle_and_calls_hook(self) -> None:
        """start() should set status to IDLE and call _on_start()."""
        agent = MockAgent()
        await agent.start()
        assert agent.status == AgentStatus.IDLE
        assert agent.on_start_called is True

    async def test_stop_sets_cancelled_and_calls_hook(self) -> None:
        """stop() should set status to CANCELLED and call _on_stop()."""
        agent = MockAgent()
        await agent.start()
        await agent.stop()
        assert agent.status == AgentStatus.CANCELLED
        assert agent.on_stop_called is True


# =============================================================================
# Test: Task Execution (Success Path)
# =============================================================================
class TestTaskExecutionSuccess:
    """Tests for successful task execution."""

    async def test_execute_task_returns_result(self) -> None:
        """execute_task() should return a TaskResult on success."""
        agent = MockAgent()
        await agent.start()

        task = TaskDefinition(name="Test task")
        result = await agent.execute_task(task)

        assert isinstance(result, TaskResult)
        assert result.status == TaskStatus.COMPLETED
        assert result.agent_id == "mock-01"
        assert result.task_id == task.task_id

    async def test_execute_task_populates_output(self) -> None:
        """execute_task() should include agent's output in result."""
        agent = MockAgent(execute_output={"code": "print('hello')"})
        await agent.start()

        task = TaskDefinition(name="Test task")
        result = await agent.execute_task(task)

        assert result.output_data == {"code": "print('hello')"}

    async def test_execute_task_records_timing(self) -> None:
        """execute_task() should populate timing information."""
        agent = MockAgent()
        await agent.start()

        task = TaskDefinition(name="Test task")
        result = await agent.execute_task(task)

        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    async def test_execute_task_returns_to_idle(self) -> None:
        """After successful execution, agent should return to IDLE."""
        agent = MockAgent()
        await agent.start()

        task = TaskDefinition(name="Test task")
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE
        assert agent.state.current_task_id is None

    async def test_execute_task_tracks_completed(self) -> None:
        """Completed task ID should be added to completed_tasks list."""
        agent = MockAgent()
        await agent.start()

        task = TaskDefinition(name="Test task")
        await agent.execute_task(task)

        assert task.task_id in agent.state.completed_tasks

    async def test_multiple_tasks_tracked(self) -> None:
        """Multiple executed tasks should all appear in completed_tasks."""
        agent = MockAgent()
        await agent.start()

        task1 = TaskDefinition(name="Task 1")
        task2 = TaskDefinition(name="Task 2")
        await agent.execute_task(task1)
        await agent.execute_task(task2)

        assert len(agent.state.completed_tasks) == 2
        assert task1.task_id in agent.state.completed_tasks
        assert task2.task_id in agent.state.completed_tasks


# =============================================================================
# Test: Task Execution (Failure Path)
# =============================================================================
class TestTaskExecutionFailure:
    """Tests for task execution error handling."""

    async def test_validation_failure_raises_agent_error(self) -> None:
        """Invalid task should raise AgentError."""
        agent = MockAgent(validate_result=False)
        await agent.start()

        task = TaskDefinition(name="Invalid task")

        with pytest.raises(AgentError) as exc_info:
            await agent.execute_task(task)

        assert exc_info.value.error_code == "TASK_VALIDATION_FAILED"
        assert exc_info.value.agent_id == "mock-01"

    async def test_execution_error_returns_failed_result(self) -> None:
        """Runtime error during _execute() should return FAILED result."""
        agent = MockAgent(should_fail=True)
        await agent.start()

        task = TaskDefinition(name="Failing task")
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        assert result.error_message is not None
        assert "intentional failure" in result.error_message

    async def test_execution_error_tracks_failed_task(self) -> None:
        """Failed task ID should be added to failed_tasks list."""
        agent = MockAgent(should_fail=True)
        await agent.start()

        task = TaskDefinition(name="Failing task")
        await agent.execute_task(task)

        assert task.task_id in agent.state.failed_tasks

    async def test_execution_error_increments_error_count(self) -> None:
        """Error count should increase on task failure."""
        agent = MockAgent(should_fail=True)
        await agent.start()

        assert agent.state.error_count == 0

        task = TaskDefinition(name="Failing task")
        await agent.execute_task(task)

        assert agent.state.error_count == 1

    async def test_execution_error_returns_to_idle(self) -> None:
        """After failure, agent should return to IDLE (ready for next task)."""
        agent = MockAgent(should_fail=True)
        await agent.start()

        task = TaskDefinition(name="Failing task")
        await agent.execute_task(task)

        assert agent.status == AgentStatus.IDLE


# =============================================================================
# Test: Heartbeat
# =============================================================================
class TestHeartbeat:
    """Tests for agent heartbeat functionality."""

    async def test_heartbeat_updates_timestamp(self) -> None:
        """send_heartbeat() should update last_heartbeat timestamp."""
        agent = MockAgent()
        assert agent.state.last_heartbeat is None

        await agent.send_heartbeat()

        assert agent.state.last_heartbeat is not None
        assert isinstance(agent.state.last_heartbeat, datetime)

    async def test_heartbeat_updates_each_call(self) -> None:
        """Multiple heartbeats should update the timestamp each time."""
        agent = MockAgent()

        await agent.send_heartbeat()
        first = agent.state.last_heartbeat

        # Small delay to ensure different timestamps
        import asyncio
        await asyncio.sleep(0.01)

        await agent.send_heartbeat()
        second = agent.state.last_heartbeat

        assert second > first


# =============================================================================
# Test: Message Handling
# =============================================================================
class TestMessageHandling:
    """Tests for agent message handling."""

    async def test_handle_task_assignment_message(self) -> None:
        """Agent should execute task from TASK_ASSIGNMENT message."""
        agent = MockAgent()
        await agent.start()

        task = TaskDefinition(name="Assigned Task")
        payload = TaskAssignmentPayload(task=task)
        msg = AgentMessage(
            message_type=MessageType.TASK_ASSIGNMENT,
            sender_id="coordinator",
            recipient_id="mock-01",
            payload=payload.model_dump(),
        )

        response = await agent.handle_message(msg)

        assert response is not None
        assert response.message_type == MessageType.TASK_RESULT
        assert response.sender_id == "mock-01"
        assert response.recipient_id == "coordinator"

    async def test_handle_control_stop_message(self) -> None:
        """Agent should stop when receiving a CONTROL:stop message."""
        agent = MockAgent()
        await agent.start()

        msg = AgentMessage(
            message_type=MessageType.CONTROL,
            sender_id="coordinator",
            payload={"command": "stop"},
        )

        await agent.handle_message(msg)
        assert agent.status == AgentStatus.CANCELLED
