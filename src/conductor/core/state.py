"""
conductor.core.state - Agent and Workflow State Models
=======================================================

This module defines the dynamic state models that track what agents and
workflows are DOING at any given moment. These are distinct from the
static identity/definition models in models.py:

    models.py:  WHO the agent is (AgentIdentity) — doesn't change
    state.py:   WHAT the agent is doing (AgentState) — changes constantly

State Architecture:
    The StateManager (orchestration/state_manager.py) persists these state
    objects to Redis (production) or an in-memory dict (development/testing).
    Every state change is saved, creating a history of the system's behavior.

    ┌─────────────────┐          ┌─────────────────┐
    │   AgentState    │          │  WorkflowState   │
    │ (per agent)     │  N:1     │ (per workflow)   │
    │                 │ ───────→ │                  │
    │ status: RUNNING │          │ phase: DEVOPS    │
    │ task: "abc"     │          │ agents: {...}    │
    └─────────────────┘          │ results: {...}   │
                                 └─────────────────┘

State Lifecycle:
    AgentState:
        IDLE → RUNNING → COMPLETED/FAILED → IDLE (next task)

    WorkflowState:
        PENDING → IN_PROGRESS → COMPLETED/FAILED
        (with phase transitions: DEVELOPMENT → DEVOPS → MONITORING)

Design Decision - Immutable Snapshots:
    State objects are Pydantic models (immutable by convention). When you
    want to update state, create a new state object with the changes.
    The StateManager handles atomic writes to prevent race conditions.

Usage:
    >>> state = AgentState(
    ...     agent_id="coding-01",
    ...     agent_type=AgentType.CODING,
    ...     status=AgentStatus.RUNNING,
    ...     current_task_id="task-abc",
    ... )
    >>> await state_manager.save_agent_state(state)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from conductor.core.enums import AgentStatus, AgentType, TaskStatus, WorkflowPhase
from conductor.core.models import TaskResult


# =============================================================================
# Helper Functions
# =============================================================================
def _now() -> datetime:
    """Get the current UTC timestamp."""
    return datetime.now(timezone.utc)


# =============================================================================
# Agent State
# =============================================================================
# Tracks the dynamic state of a single agent instance. This is the primary
# model used by the StateManager to persist and query agent states.
#
# Key Difference from AgentIdentity:
#   AgentIdentity: Static metadata (type, name, version) — set once at creation
#   AgentState: Dynamic runtime data (status, current task, error counts) — changes constantly
# =============================================================================
class AgentState(BaseModel):
    """Dynamic runtime state of a single agent instance.

    This model is updated every time an agent's state changes:
    - Task assigned → status changes to RUNNING, current_task_id set
    - Task completed → status changes to COMPLETED, task added to completed_tasks
    - Task failed → status changes to FAILED, error_count incremented
    - Heartbeat → last_heartbeat updated

    The StateManager persists these updates to Redis (or in-memory).
    The Coordinator reads agent states to make task dispatch decisions
    (e.g., "find me an IDLE CODING agent").

    Attributes:
        agent_id: Unique agent identifier (matches AgentIdentity.agent_id).
        agent_type: The agent's role (matches AgentIdentity.agent_type).
            Stored here for query convenience (filter by type without joining).
        status: Current lifecycle state (IDLE, RUNNING, FAILED, etc.).
            Updated by BaseAgent during task execution.
        current_task_id: ID of the task currently being executed.
            None when the agent is IDLE or between tasks.
        completed_tasks: List of task IDs this agent has successfully completed.
            Used for tracking agent productivity and history.
        failed_tasks: List of task IDs this agent has failed.
            Used by the ErrorHandler for per-agent failure tracking.
        error_count: Running count of errors this agent has encountered.
            Used by CircuitBreaker to decide when to stop sending tasks.
        last_heartbeat: Last time this agent reported being alive.
            Used by the Coordinator to detect dead/stuck agents.
        metadata: Arbitrary key-value pairs for agent-specific data.
        created_at: When this agent state was first created.
        updated_at: When this state was last modified.
            Updated automatically on every state change.

    Example:
        >>> state = AgentState(
        ...     agent_id="coding-01",
        ...     agent_type=AgentType.CODING,
        ...     status=AgentStatus.IDLE,
        ... )
        >>> # Agent starts a task:
        >>> state = state.model_copy(update={
        ...     "status": AgentStatus.RUNNING,
        ...     "current_task_id": "task-abc",
        ...     "updated_at": datetime.now(timezone.utc),
        ... })
    """

    agent_id: str = Field(
        description="Unique agent identifier (matches AgentIdentity.agent_id)",
    )
    agent_type: AgentType = Field(
        description="Agent role type (for query convenience)",
    )
    status: AgentStatus = Field(
        default=AgentStatus.IDLE,
        description="Current agent lifecycle state",
    )
    current_task_id: Optional[str] = Field(
        default=None,
        description="ID of the task currently being executed (None if idle)",
    )
    completed_tasks: list[str] = Field(
        default_factory=list,
        description="List of successfully completed task IDs",
    )
    failed_tasks: list[str] = Field(
        default_factory=list,
        description="List of failed task IDs",
    )
    error_count: int = Field(
        default=0,
        ge=0,
        description="Running count of errors encountered",
    )
    last_heartbeat: Optional[datetime] = Field(
        default=None,
        description="Last heartbeat timestamp (None if never reported)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary agent-specific metadata",
    )
    created_at: datetime = Field(
        default_factory=_now,
        description="State creation timestamp (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=_now,
        description="Last state modification timestamp (UTC)",
    )

    @property
    def is_available(self) -> bool:
        """Check if the agent is available to accept a new task.

        An agent is available when it's IDLE (not working on anything)
        and hasn't been cancelled.

        Returns:
            True if the agent can accept a new task.
        """
        return self.status == AgentStatus.IDLE

    @property
    def total_tasks(self) -> int:
        """Total number of tasks this agent has attempted.

        Returns:
            Sum of completed and failed tasks.
        """
        return len(self.completed_tasks) + len(self.failed_tasks)

    @property
    def success_rate(self) -> float:
        """Calculate the agent's task success rate.

        Returns:
            Success rate as a float between 0.0 and 1.0.
            Returns 1.0 if no tasks have been attempted (no failures).
        """
        total = self.total_tasks
        if total == 0:
            return 1.0
        return len(self.completed_tasks) / total


# =============================================================================
# Workflow State
# =============================================================================
# Tracks the overall state of a multi-phase workflow execution.
# This is the "master record" for a workflow run — it aggregates
# agent states and task results into a single queryable object.
#
# The WorkflowEngine reads and updates this state as it executes
# phases and steps. The feedback loop modifies the phase_history
# when the Monitor triggers a return to Development.
# =============================================================================
class WorkflowState(BaseModel):
    """Complete runtime state of a workflow execution.

    This is the "master record" for a workflow. It aggregates:
    - Which phase is currently executing
    - All agent states participating in this workflow
    - All task results produced so far
    - Error log and phase transition history

    The WorkflowEngine creates this when a workflow starts and updates
    it as the workflow progresses through phases.

    State Transitions:
        status: PENDING → IN_PROGRESS → COMPLETED/FAILED
        current_phase: DEVELOPMENT → DEVOPS → MONITORING
                       ↑                          │
                       └── (feedback loop) ────────┘

    Attributes:
        workflow_id: Unique workflow execution identifier.
        current_phase: Which phase is currently executing.
        phase_history: Ordered record of phase transitions.
            Each entry is a dict with phase, started_at, completed_at, result.
            Used for debugging and auditing the workflow execution path.
        agent_states: Map of agent_id → AgentState for all participating agents.
            Provides a snapshot of every agent involved in this workflow.
        task_results: Map of task_id → TaskResult for all completed tasks.
            Used by the WorkflowEngine to pass outputs between dependent tasks.
        started_at: When the workflow execution began.
        completed_at: When the workflow finished (None if still running).
        status: Overall workflow status (PENDING, IN_PROGRESS, COMPLETED, FAILED).
        error_log: Chronological list of errors that occurred during execution.
            Each entry includes timestamp, error message, and context.
        feedback_count: Number of times the feedback loop has triggered.
            Used to prevent infinite feedback loops (configurable limit).
        metadata: Arbitrary workflow-level metadata.

    Example:
        >>> state = WorkflowState(
        ...     workflow_id="wf-123",
        ...     current_phase=WorkflowPhase.DEVELOPMENT,
        ...     status=TaskStatus.IN_PROGRESS,
        ... )
    """

    workflow_id: str = Field(
        description="Unique workflow execution identifier",
    )
    current_phase: WorkflowPhase = Field(
        default=WorkflowPhase.DEVELOPMENT,
        description="Currently executing workflow phase",
    )
    phase_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ordered record of phase transitions with timestamps",
    )
    agent_states: dict[str, AgentState] = Field(
        default_factory=dict,
        description="Map of agent_id → AgentState for participating agents",
    )
    task_results: dict[str, TaskResult] = Field(
        default_factory=dict,
        description="Map of task_id → TaskResult for completed tasks",
    )
    started_at: datetime = Field(
        default_factory=_now,
        description="Workflow execution start timestamp (UTC)",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Workflow completion timestamp (UTC, None if running)",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Overall workflow execution status",
    )
    error_log: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Chronological list of errors during execution",
    )
    feedback_count: int = Field(
        default=0,
        ge=0,
        description="Number of times the feedback loop has triggered",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary workflow-level metadata",
    )

    @property
    def is_running(self) -> bool:
        """Check if the workflow is currently executing.

        Returns:
            True if the workflow status is IN_PROGRESS.
        """
        return self.status == TaskStatus.IN_PROGRESS

    @property
    def is_complete(self) -> bool:
        """Check if the workflow has finished (successfully or not).

        Returns:
            True if the workflow status is COMPLETED or FAILED.
        """
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate the workflow execution duration.

        Returns:
            Duration in seconds if workflow has completed, None otherwise.
        """
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def completed_task_count(self) -> int:
        """Count of successfully completed tasks.

        Returns:
            Number of tasks with COMPLETED status in task_results.
        """
        return sum(
            1 for result in self.task_results.values()
            if result.status == TaskStatus.COMPLETED
        )

    @property
    def failed_task_count(self) -> int:
        """Count of failed tasks.

        Returns:
            Number of tasks with FAILED status in task_results.
        """
        return sum(
            1 for result in self.task_results.values()
            if result.status == TaskStatus.FAILED
        )
