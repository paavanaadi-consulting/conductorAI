"""
Tests for conductor.core.state
================================

These tests verify the dynamic state models:
    - AgentState: Agent lifecycle tracking, properties (is_available, success_rate)
    - WorkflowState: Workflow lifecycle tracking, phase management

All tests are unit tests — pure data model validation.
"""

from datetime import datetime, timezone

import pytest

from conductor.core.enums import AgentStatus, AgentType, TaskStatus, WorkflowPhase
from conductor.core.models import TaskResult
from conductor.core.state import AgentState, WorkflowState


# =============================================================================
# Test: AgentState
# =============================================================================
class TestAgentState:
    """Tests for the AgentState model."""

    def test_create_minimal_state(self) -> None:
        """AgentState should create with just agent_id and agent_type."""
        state = AgentState(
            agent_id="coding-01",
            agent_type=AgentType.CODING,
        )
        assert state.agent_id == "coding-01"
        assert state.agent_type == AgentType.CODING
        assert state.status == AgentStatus.IDLE

    def test_default_values(self) -> None:
        """Default values should represent a fresh, idle agent."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.REVIEW,
        )
        assert state.current_task_id is None
        assert state.completed_tasks == []
        assert state.failed_tasks == []
        assert state.error_count == 0
        assert state.last_heartbeat is None
        assert state.metadata == {}

    def test_auto_generates_timestamps(self) -> None:
        """created_at and updated_at should be auto-generated."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.TEST,
        )
        assert isinstance(state.created_at, datetime)
        assert isinstance(state.updated_at, datetime)

    def test_is_available_when_idle(self) -> None:
        """Agent should be available when IDLE."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.CODING,
            status=AgentStatus.IDLE,
        )
        assert state.is_available is True

    def test_is_not_available_when_running(self) -> None:
        """Agent should NOT be available when RUNNING."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.CODING,
            status=AgentStatus.RUNNING,
        )
        assert state.is_available is False

    def test_is_not_available_when_failed(self) -> None:
        """Agent should NOT be available when FAILED."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.CODING,
            status=AgentStatus.FAILED,
        )
        assert state.is_available is False

    def test_total_tasks(self) -> None:
        """total_tasks should sum completed and failed tasks."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.CODING,
            completed_tasks=["t1", "t2", "t3"],
            failed_tasks=["t4"],
        )
        assert state.total_tasks == 4

    def test_success_rate_all_success(self) -> None:
        """success_rate should be 1.0 when all tasks completed."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.CODING,
            completed_tasks=["t1", "t2"],
            failed_tasks=[],
        )
        assert state.success_rate == 1.0

    def test_success_rate_mixed(self) -> None:
        """success_rate should reflect the ratio correctly."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.CODING,
            completed_tasks=["t1", "t2", "t3"],
            failed_tasks=["t4"],
        )
        assert state.success_rate == 0.75

    def test_success_rate_no_tasks(self) -> None:
        """success_rate should be 1.0 when no tasks attempted."""
        state = AgentState(
            agent_id="a1",
            agent_type=AgentType.CODING,
        )
        assert state.success_rate == 1.0

    def test_model_copy_update(self) -> None:
        """model_copy() should create updated state without mutating original."""
        original = AgentState(
            agent_id="a1",
            agent_type=AgentType.CODING,
            status=AgentStatus.IDLE,
        )
        updated = original.model_copy(
            update={"status": AgentStatus.RUNNING, "current_task_id": "t1"}
        )

        # Original unchanged
        assert original.status == AgentStatus.IDLE
        assert original.current_task_id is None

        # Updated has new values
        assert updated.status == AgentStatus.RUNNING
        assert updated.current_task_id == "t1"

    def test_serialization_roundtrip(self) -> None:
        """AgentState should serialize to dict and back."""
        original = AgentState(
            agent_id="a1",
            agent_type=AgentType.DEVOPS,
            status=AgentStatus.RUNNING,
            completed_tasks=["t1"],
            error_count=2,
        )
        data = original.model_dump()
        restored = AgentState(**data)
        assert restored.agent_id == original.agent_id
        assert restored.status == original.status
        assert restored.completed_tasks == original.completed_tasks


# =============================================================================
# Test: WorkflowState
# =============================================================================
class TestWorkflowState:
    """Tests for the WorkflowState model."""

    def test_create_minimal_state(self) -> None:
        """WorkflowState should create with just workflow_id."""
        state = WorkflowState(workflow_id="wf-01")
        assert state.workflow_id == "wf-01"
        assert state.current_phase == WorkflowPhase.DEVELOPMENT
        assert state.status == TaskStatus.PENDING

    def test_default_values(self) -> None:
        """Defaults should represent a fresh, pending workflow."""
        state = WorkflowState(workflow_id="wf-01")
        assert state.phase_history == []
        assert state.agent_states == {}
        assert state.task_results == {}
        assert state.completed_at is None
        assert state.error_log == []
        assert state.feedback_count == 0

    def test_is_running(self) -> None:
        """is_running should be True when status is IN_PROGRESS."""
        state = WorkflowState(
            workflow_id="wf-01",
            status=TaskStatus.IN_PROGRESS,
        )
        assert state.is_running is True

    def test_is_not_running_when_pending(self) -> None:
        """is_running should be False when PENDING."""
        state = WorkflowState(workflow_id="wf-01")
        assert state.is_running is False

    def test_is_complete_when_completed(self) -> None:
        """is_complete should be True when COMPLETED."""
        state = WorkflowState(
            workflow_id="wf-01",
            status=TaskStatus.COMPLETED,
        )
        assert state.is_complete is True

    def test_is_complete_when_failed(self) -> None:
        """is_complete should be True when FAILED (finished, just not successfully)."""
        state = WorkflowState(
            workflow_id="wf-01",
            status=TaskStatus.FAILED,
        )
        assert state.is_complete is True

    def test_duration_when_completed(self) -> None:
        """duration_seconds should be calculated when workflow is complete."""
        from datetime import timedelta

        start = datetime.now(timezone.utc)
        end = start + timedelta(seconds=42.5)

        state = WorkflowState(
            workflow_id="wf-01",
            started_at=start,
            completed_at=end,
        )
        assert state.duration_seconds == pytest.approx(42.5, abs=0.1)

    def test_duration_when_running(self) -> None:
        """duration_seconds should be None when workflow is still running."""
        state = WorkflowState(workflow_id="wf-01")
        assert state.duration_seconds is None

    def test_completed_task_count(self) -> None:
        """completed_task_count should count COMPLETED tasks."""
        state = WorkflowState(
            workflow_id="wf-01",
            task_results={
                "t1": TaskResult(
                    task_id="t1", agent_id="a1", status=TaskStatus.COMPLETED
                ),
                "t2": TaskResult(
                    task_id="t2", agent_id="a2", status=TaskStatus.COMPLETED
                ),
                "t3": TaskResult(
                    task_id="t3", agent_id="a3", status=TaskStatus.FAILED
                ),
            },
        )
        assert state.completed_task_count == 2

    def test_failed_task_count(self) -> None:
        """failed_task_count should count FAILED tasks."""
        state = WorkflowState(
            workflow_id="wf-01",
            task_results={
                "t1": TaskResult(
                    task_id="t1", agent_id="a1", status=TaskStatus.COMPLETED
                ),
                "t2": TaskResult(
                    task_id="t2", agent_id="a2", status=TaskStatus.FAILED
                ),
            },
        )
        assert state.failed_task_count == 1

    def test_workflow_with_agent_states(self) -> None:
        """WorkflowState should hold agent states for all participants."""
        agent_state = AgentState(
            agent_id="coding-01",
            agent_type=AgentType.CODING,
            status=AgentStatus.RUNNING,
        )
        state = WorkflowState(
            workflow_id="wf-01",
            agent_states={"coding-01": agent_state},
        )
        assert "coding-01" in state.agent_states
        assert state.agent_states["coding-01"].status == AgentStatus.RUNNING

    def test_serialization_roundtrip(self) -> None:
        """WorkflowState should serialize to dict and back."""
        original = WorkflowState(
            workflow_id="wf-01",
            current_phase=WorkflowPhase.DEVOPS,
            status=TaskStatus.IN_PROGRESS,
            feedback_count=1,
        )
        data = original.model_dump()
        restored = WorkflowState(**data)
        assert restored.workflow_id == original.workflow_id
        assert restored.current_phase == original.current_phase
        assert restored.feedback_count == 1
