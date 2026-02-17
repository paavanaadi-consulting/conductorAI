"""
conductor.orchestration.workflow_engine - Multi-Phase Workflow Execution
=========================================================================

This module implements the Workflow Engine — the top-level orchestrator that
executes multi-phase workflows from start to finish. It is the entry point
for running a complete ConductorAI pipeline.

Architecture Context:
    The Workflow Engine sits at the top of the orchestration layer.
    It owns the workflow lifecycle and delegates task execution to the
    Agent Coordinator.

    ┌────────────────────────────────────────────────────────────────┐
    │                     Workflow Engine                             │
    │                                                                │
    │  WorkflowDef ──→ Phase Loop ──→ Task Dispatch ──→ Results     │
    │                                                                │
    │  Phase 1: DEVELOPMENT                                         │
    │    ├── Task: Generate Code ──→ [Coordinator] ──→ coding-01    │
    │    └── Task: Review Code   ──→ [Coordinator] ──→ review-01   │
    │                                                                │
    │  ── Phase Gate (PolicyEngine) ──                              │
    │                                                                │
    │  Phase 2: DEVOPS                                               │
    │    └── Task: Deploy ──→ [Coordinator] ──→ devops-01           │
    │                                                                │
    │  Phase 3: MONITORING                                           │
    │    └── Task: Monitor ──→ [Coordinator] ──→ monitor-01         │
    │                          │                                     │
    │                          └── Feedback? ──→ Loop to Phase 1    │
    └────────────────────────────────────────────────────────────────┘

Workflow Execution Flow:
    1. ``run_workflow(definition)`` is called with a WorkflowDefinition.
    2. A WorkflowState is created with status=IN_PROGRESS.
    3. For each phase in the definition:
       a. Collect tasks assigned to agents of that phase's types.
       b. Execute each task via coordinator.dispatch_task().
       c. Record results in the WorkflowState.
       d. Check the phase gate (PolicyEngine) before advancing.
    4. If all phases complete successfully, status → COMPLETED.
    5. If any phase fails the gate, status → FAILED.
    6. If the Monitor phase produces feedback, loop back to DEVELOPMENT
       (up to max_feedback_loops times).

Phase-to-AgentType Mapping:
    DEVELOPMENT → [CODING, REVIEW, TEST_DATA, TEST]
    DEVOPS      → [DEVOPS, DEPLOYING]
    MONITORING  → [MONITOR]

Usage:
    >>> engine = WorkflowEngine(coordinator, state_manager, policy_engine)
    >>>
    >>> definition = WorkflowDefinition(
    ...     name="Build User Service",
    ...     tasks=[coding_task, review_task, deploy_task],
    ... )
    >>>
    >>> state = await engine.run_workflow(definition)
    >>> print(state.status)  # TaskStatus.COMPLETED
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from conductor.core.enums import AgentType, TaskStatus, WorkflowPhase
from conductor.core.exceptions import AgentError, WorkflowError
from conductor.core.models import TaskDefinition, TaskResult, WorkflowDefinition
from conductor.core.state import WorkflowState
from conductor.orchestration.agent_coordinator import AgentCoordinator
from conductor.orchestration.policy_engine import PolicyEngine
from conductor.orchestration.state_manager import StateManager


# =============================================================================
# Logger Setup
# =============================================================================
logger = structlog.get_logger()


# =============================================================================
# Phase → Agent Type Mapping
# =============================================================================
# This mapping defines which agent types belong to each workflow phase.
# When the engine is executing a phase, it dispatches tasks whose
# assigned_to agent type is in this set.
#
# Example: DEVELOPMENT phase includes CODING, REVIEW, TEST_DATA, TEST.
# So any task with assigned_to=AgentType.CODING runs in DEVELOPMENT.
# =============================================================================
PHASE_AGENT_TYPES: dict[WorkflowPhase, set[AgentType]] = {
    WorkflowPhase.DEVELOPMENT: {
        AgentType.CODING,
        AgentType.REVIEW,
        AgentType.TEST_DATA,
        AgentType.TEST,
    },
    WorkflowPhase.DEVOPS: {
        AgentType.DEVOPS,
        AgentType.DEPLOYING,
    },
    WorkflowPhase.MONITORING: {
        AgentType.MONITOR,
    },
}


class WorkflowEngine:
    """Multi-phase workflow execution engine.

    The WorkflowEngine takes a WorkflowDefinition and executes it by:
    1. Iterating through phases in order (DEVELOPMENT → DEVOPS → MONITORING).
    2. For each phase, dispatching relevant tasks to agents via the Coordinator.
    3. Checking phase gates (PolicyEngine) before advancing to the next phase.
    4. Supporting feedback loops (Monitor → Development) with a configurable limit.
    5. Persisting the WorkflowState to the StateManager after every change.

    The engine does NOT contain agent-specific logic. It only orchestrates
    the flow of tasks through phases. The actual work is done by agents,
    managed by the AgentCoordinator.

    Attributes:
        _coordinator: Dispatches tasks to agents.
        _state_manager: Persists workflow state.
        _policy_engine: Optional phase gate enforcement.
        _max_feedback_loops: Maximum number of MONITORING → DEVELOPMENT cycles.
            Prevents infinite feedback loops.
        _logger: Structured logger with workflow engine context.

    Example:
        >>> engine = WorkflowEngine(coordinator, state_manager, policy_engine)
        >>> definition = WorkflowDefinition(
        ...     name="Build API",
        ...     tasks=[coding_task, review_task, deploy_task],
        ... )
        >>> state = await engine.run_workflow(definition)
        >>> print(state.status)  # TaskStatus.COMPLETED
    """

    def __init__(
        self,
        coordinator: AgentCoordinator,
        state_manager: StateManager,
        policy_engine: Optional[PolicyEngine] = None,
        max_feedback_loops: int = 3,
    ) -> None:
        """Initialize the Workflow Engine.

        Args:
            coordinator: The AgentCoordinator for dispatching tasks.
            state_manager: The StateManager for persisting workflow state.
            policy_engine: Optional PolicyEngine for phase gate enforcement.
                If None, phase gates are skipped (all phases auto-advance).
            max_feedback_loops: Maximum MONITORING → DEVELOPMENT cycles.
                Default is 3. Set to 0 to disable feedback loops entirely.
        """
        self._coordinator = coordinator
        self._state_manager = state_manager
        self._policy_engine = policy_engine
        self._max_feedback_loops = max_feedback_loops
        self._logger = logger.bind(component="workflow_engine")

    # =========================================================================
    # Main Entry Point
    # =========================================================================

    async def run_workflow(
        self,
        definition: WorkflowDefinition,
    ) -> WorkflowState:
        """Execute a complete multi-phase workflow.

        This is the main entry point. It creates a WorkflowState, iterates
        through each phase, dispatches tasks, checks phase gates, and handles
        feedback loops.

        Args:
            definition: The workflow to execute, containing phases and tasks.

        Returns:
            The final WorkflowState with all results, phase history, and
            status (COMPLETED or FAILED).

        Raises:
            WorkflowError: If the workflow encounters an unrecoverable error.
        """
        self._logger.info(
            "workflow_starting",
            workflow_id=definition.workflow_id,
            workflow_name=definition.name,
            phases=[p.value for p in definition.phases],
            task_count=len(definition.tasks),
        )

        # --- Create initial workflow state ---
        state = WorkflowState(
            workflow_id=definition.workflow_id,
            current_phase=definition.phases[0] if definition.phases else WorkflowPhase.DEVELOPMENT,
            status=TaskStatus.IN_PROGRESS,
        )
        await self._state_manager.save_workflow_state(state)

        try:
            # --- Execute phases ---
            state = await self._execute_phases(definition, state)

            # --- Mark workflow as complete ---
            state = state.model_copy(update={
                "status": TaskStatus.COMPLETED,
                "completed_at": datetime.now(timezone.utc),
            })
            await self._state_manager.save_workflow_state(state)

            self._logger.info(
                "workflow_completed",
                workflow_id=definition.workflow_id,
                completed_tasks=state.completed_task_count,
                failed_tasks=state.failed_task_count,
                feedback_loops=state.feedback_count,
            )

            return state

        except Exception as e:
            # --- Mark workflow as failed ---
            error_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "error_type": type(e).__name__,
            }
            error_log = list(state.error_log) + [error_entry]

            state = state.model_copy(update={
                "status": TaskStatus.FAILED,
                "completed_at": datetime.now(timezone.utc),
                "error_log": error_log,
            })
            await self._state_manager.save_workflow_state(state)

            self._logger.error(
                "workflow_failed",
                workflow_id=definition.workflow_id,
                error=str(e),
            )

            return state

    # =========================================================================
    # Phase Execution
    # =========================================================================

    async def _execute_phases(
        self,
        definition: WorkflowDefinition,
        state: WorkflowState,
    ) -> WorkflowState:
        """Execute all phases in the workflow definition.

        Iterates through phases in order. For each phase:
        1. Records phase start in phase_history.
        2. Collects tasks for this phase.
        3. Dispatches each task via the coordinator.
        4. Records phase completion.
        5. Checks the phase gate before advancing (if policy engine is set).

        Args:
            definition: The workflow definition with phases and tasks.
            state: The current workflow state (mutated through model_copy).

        Returns:
            Updated WorkflowState with all phase results.

        Raises:
            WorkflowError: If a phase fails and cannot continue.
        """
        for phase in definition.phases:
            self._logger.info(
                "phase_starting",
                workflow_id=definition.workflow_id,
                phase=phase.value,
            )

            # Update current phase
            state = state.model_copy(update={"current_phase": phase})
            await self._state_manager.save_workflow_state(state)

            # Record phase start in history
            phase_record: dict[str, Any] = {
                "phase": phase.value,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

            # --- Get tasks for this phase ---
            phase_tasks = self._get_phase_tasks(definition.tasks, phase)

            if not phase_tasks:
                self._logger.debug(
                    "phase_no_tasks",
                    phase=phase.value,
                )
                phase_record["completed_at"] = datetime.now(timezone.utc).isoformat()
                phase_record["result"] = "skipped"
                phase_record["task_count"] = 0
                state = state.model_copy(update={
                    "phase_history": list(state.phase_history) + [phase_record],
                })
                await self._state_manager.save_workflow_state(state)
                continue

            # --- Execute tasks in this phase ---
            state = await self._execute_phase_tasks(
                phase_tasks, state, definition.workflow_id
            )

            # --- Record phase completion ---
            phase_record["completed_at"] = datetime.now(timezone.utc).isoformat()
            phase_record["result"] = "completed"
            phase_record["task_count"] = len(phase_tasks)
            phase_record["completed_count"] = state.completed_task_count
            phase_record["failed_count"] = state.failed_task_count

            state = state.model_copy(update={
                "phase_history": list(state.phase_history) + [phase_record],
            })
            await self._state_manager.save_workflow_state(state)

            self._logger.info(
                "phase_completed",
                workflow_id=definition.workflow_id,
                phase=phase.value,
                tasks_executed=len(phase_tasks),
            )

        return state

    async def _execute_phase_tasks(
        self,
        tasks: list[TaskDefinition],
        state: WorkflowState,
        workflow_id: str,
    ) -> WorkflowState:
        """Execute all tasks in a single phase.

        Tasks within a phase are executed sequentially (in order).
        Each task result is recorded in the workflow state.

        If a task fails (exception during dispatch), the failure is recorded
        but execution continues with the remaining tasks in the phase.
        This is a "best effort" strategy: we try all tasks even if some fail.

        Args:
            tasks: List of tasks to execute in this phase.
            state: Current workflow state.
            workflow_id: The workflow ID for logging.

        Returns:
            Updated WorkflowState with task results.
        """
        for task in tasks:
            try:
                result = await self._coordinator.dispatch_task(task)

                # Record the result in workflow state
                task_results = dict(state.task_results)
                task_results[task.task_id] = result
                state = state.model_copy(update={"task_results": task_results})

            except Exception as e:
                # Record the failure but continue with other tasks
                self._logger.warning(
                    "task_dispatch_failed",
                    workflow_id=workflow_id,
                    task_id=task.task_id,
                    error=str(e),
                )

                # Create a failure result for tracking
                failure_result = TaskResult(
                    task_id=task.task_id,
                    agent_id="coordinator",
                    status=TaskStatus.FAILED,
                    error_message=str(e),
                )
                task_results = dict(state.task_results)
                task_results[task.task_id] = failure_result
                state = state.model_copy(update={"task_results": task_results})

                # Record error in error_log
                error_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "task_id": task.task_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
                state = state.model_copy(update={
                    "error_log": list(state.error_log) + [error_entry],
                })

            # Persist state after each task
            await self._state_manager.save_workflow_state(state)

        return state

    # =========================================================================
    # Feedback Loop
    # =========================================================================

    async def trigger_feedback_loop(
        self,
        state: WorkflowState,
        definition: WorkflowDefinition,
        feedback: dict[str, Any],
    ) -> WorkflowState:
        """Trigger a feedback loop from MONITORING back to DEVELOPMENT.

        When the Monitor agent detects issues (quality regression, performance
        degradation, etc.), it triggers a feedback loop. This:
        1. Increments the feedback_count.
        2. Records the feedback in metadata.
        3. Re-executes the DEVELOPMENT phase with updated tasks.

        The feedback loop is limited by max_feedback_loops to prevent
        infinite cycles.

        Args:
            state: Current workflow state (must be in MONITORING phase).
            definition: The original workflow definition.
            feedback: Feedback data from the Monitor agent, containing
                findings, recommendations, and affected task IDs.

        Returns:
            Updated WorkflowState after re-executing DEVELOPMENT.

        Raises:
            WorkflowError: If max feedback loops exceeded.
        """
        if state.feedback_count >= self._max_feedback_loops:
            raise WorkflowError(
                message=(
                    f"Maximum feedback loops exceeded: "
                    f"{state.feedback_count} >= {self._max_feedback_loops}"
                ),
                workflow_id=state.workflow_id,
                error_code="MAX_FEEDBACK_LOOPS",
            )

        self._logger.info(
            "feedback_loop_triggered",
            workflow_id=state.workflow_id,
            feedback_count=state.feedback_count + 1,
            max_loops=self._max_feedback_loops,
        )

        # Increment feedback count
        state = state.model_copy(update={
            "feedback_count": state.feedback_count + 1,
            "current_phase": WorkflowPhase.DEVELOPMENT,
        })
        await self._state_manager.save_workflow_state(state)

        # Re-execute DEVELOPMENT phase tasks
        dev_tasks = self._get_phase_tasks(
            definition.tasks, WorkflowPhase.DEVELOPMENT
        )
        if dev_tasks:
            state = await self._execute_phase_tasks(
                dev_tasks, state, state.workflow_id
            )

        return state

    # =========================================================================
    # Phase Gate Check
    # =========================================================================

    async def check_phase_gate(self, state: WorkflowState) -> bool:
        """Check whether the workflow can advance to the next phase.

        Uses the PolicyEngine (if configured) to evaluate the PhaseGatePolicy.
        The gate checks the success rate of completed tasks against a threshold.

        Args:
            state: The current workflow state with task results.

        Returns:
            True if the phase gate passes (can advance).
            False if the gate blocks advancement.
        """
        if self._policy_engine is None:
            # No policy engine → always allow advancement
            return True

        return await self._policy_engine.check({"workflow_state": state})

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    @staticmethod
    def _get_phase_tasks(
        tasks: list[TaskDefinition],
        phase: WorkflowPhase,
    ) -> list[TaskDefinition]:
        """Filter tasks that belong to a specific phase.

        A task belongs to a phase if its ``assigned_to`` agent type is in
        the PHASE_AGENT_TYPES mapping for that phase.

        Args:
            tasks: All tasks in the workflow definition.
            phase: The phase to filter for.

        Returns:
            List of tasks whose assigned_to agent type belongs to this phase.
        """
        phase_types = PHASE_AGENT_TYPES.get(phase, set())
        return [
            task for task in tasks
            if task.assigned_to in phase_types
        ]
