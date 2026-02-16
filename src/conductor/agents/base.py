"""
conductor.agents.base - Abstract Base Agent
=============================================

This module defines the BaseAgent abstract class — the foundation that ALL
specialized agents in ConductorAI inherit from. It implements the Template
Method pattern to ensure consistent agent behavior while allowing each
specialized agent to define its own execution logic.

Template Method Pattern:
    The key insight is that all agents share the same lifecycle:
    1. Validate the task
    2. Update status to RUNNING
    3. Execute the task-specific logic
    4. Update status to COMPLETED or FAILED
    5. Return a TaskResult

    BaseAgent handles steps 1, 2, 4, 5 (the "template").
    Subclasses only implement step 3 (the "hook method" _execute).

    ┌─────────────────────────────────────────────────────┐
    │  BaseAgent.execute_task(task)   ← Public API        │
    │  ┌──────────────────────────────────────────────┐   │
    │  │ 1. _validate_task(task)      ← Override this │   │
    │  │ 2. Set status → RUNNING                      │   │
    │  │ 3. _execute(task)            ← Override this │   │
    │  │ 4. Set status → COMPLETED/FAILED             │   │
    │  │ 5. Return TaskResult                          │   │
    │  └──────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────┘

Agent Lifecycle:
    ┌───────┐     start()     ┌──────┐   execute_task()  ┌─────────┐
    │Created│ ──────────────→ │ IDLE │ ────────────────→ │ RUNNING │
    └───────┘                 └──────┘                    └────┬────┘
                                 ↑                             │
                                 │     ┌───────────┐           │
                                 └─────│ COMPLETED │ ←─────────┤ (success)
                                 │     └───────────┘           │
                                 │     ┌───────────┐           │
                                 └─────│  FAILED   │ ←─────────┘ (error)
                                       └───────────┘

Subclass Contract:
    To create a new agent, subclass BaseAgent and implement:
    - _execute(task) → TaskResult     # Your agent's core logic
    - _validate_task(task) → bool     # What tasks can your agent handle?
    - Optionally: _on_start(), _on_stop() for lifecycle hooks

Usage:
    class MyCoolAgent(BaseAgent):
        async def _validate_task(self, task):
            return "specification" in task.input_data

        async def _execute(self, task):
            # Do your thing...
            return self._create_result(task.task_id, TaskStatus.COMPLETED, {"output": "..."})
"""

from __future__ import annotations

import logging
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentStatus, AgentType, MessageType, TaskStatus
from conductor.core.exceptions import AgentError
from conductor.core.messages import AgentMessage
from conductor.core.models import AgentIdentity, TaskDefinition, TaskResult
from conductor.core.state import AgentState


# =============================================================================
# Logger Setup
# =============================================================================
# We use structlog for structured logging. Each agent binds its identity
# (agent_id, agent_type) to the logger so every log line includes context.
# =============================================================================
logger = structlog.get_logger()


class BaseAgent(ABC):
    """Abstract base class for all ConductorAI agents.

    This class implements the Template Method pattern: it defines the
    skeleton of the agent execution lifecycle, deferring specific steps
    to subclass implementations.

    What BaseAgent Handles (you get this for free):
        - Agent identity management (ID, type, name)
        - State tracking (status, current task, error counts)
        - Task execution lifecycle (validate → run → report)
        - Error handling and status transitions
        - Heartbeat support
        - Structured logging with agent context

    What Subclasses Must Implement:
        - _execute(task): The agent's core logic (what it actually does)
        - _validate_task(task): Checks if a task is valid for this agent

    What Subclasses Can Optionally Override:
        - _on_start(): Custom initialization logic (called during start())
        - _on_stop(): Custom cleanup logic (called during stop())

    Attributes:
        _identity: The agent's static identity (AgentIdentity model).
        _state: The agent's dynamic runtime state (AgentState model).
        _config: ConductorAI configuration.
        _logger: Structured logger bound with agent context.

    Example:
        >>> class SimpleCodingAgent(BaseAgent):
        ...     async def _validate_task(self, task):
        ...         return "specification" in task.input_data
        ...
        ...     async def _execute(self, task):
        ...         code = generate_code(task.input_data["specification"])
        ...         return self._create_result(
        ...             task.task_id, TaskStatus.COMPLETED,
        ...             {"code": code, "language": "python"},
        ...         )
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
        config: ConductorConfig,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Initialize the base agent.

        Args:
            agent_id: Unique identifier for this agent instance.
                Convention: "{type}-{sequence}" like "coding-01", "review-01".
            agent_type: The specialized role this agent plays.
                Determines which tasks the coordinator routes to this agent.
            config: ConductorAI configuration (passed down from ConductorAI facade).
            name: Human-readable name for logging. Defaults to agent_id.
            description: Optional description of this agent's purpose.
        """
        # -----------------------------------------------------------------
        # Identity: WHO this agent is (static, doesn't change)
        # -----------------------------------------------------------------
        self._identity = AgentIdentity(
            agent_id=agent_id,
            agent_type=agent_type,
            name=name or agent_id,
            description=description,
        )

        # -----------------------------------------------------------------
        # State: WHAT this agent is doing (dynamic, changes frequently)
        # -----------------------------------------------------------------
        self._state = AgentState(
            agent_id=agent_id,
            agent_type=agent_type,
            status=AgentStatus.IDLE,
        )

        # -----------------------------------------------------------------
        # Configuration
        # -----------------------------------------------------------------
        self._config = config

        # -----------------------------------------------------------------
        # Logger: Structured logger with agent context bound
        # Every log line from this agent automatically includes:
        #   {"agent_id": "coding-01", "agent_type": "coding"}
        # -----------------------------------------------------------------
        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type=agent_type.value,
        )

    # =========================================================================
    # Properties (read-only access to internal state)
    # =========================================================================

    @property
    def identity(self) -> AgentIdentity:
        """Get the agent's static identity information.

        Returns:
            AgentIdentity with agent_id, agent_type, name, version.
        """
        return self._identity

    @property
    def agent_id(self) -> str:
        """Shortcut to get the agent's unique identifier.

        Returns:
            The agent_id string.
        """
        return self._identity.agent_id

    @property
    def agent_type(self) -> AgentType:
        """Shortcut to get the agent's type.

        Returns:
            The AgentType enum value.
        """
        return self._identity.agent_type

    @property
    def state(self) -> AgentState:
        """Get the agent's current dynamic state.

        Returns:
            AgentState with status, current_task, error_count, etc.
        """
        return self._state

    @property
    def status(self) -> AgentStatus:
        """Shortcut to get the agent's current status.

        Returns:
            The current AgentStatus enum value.
        """
        return self._state.status

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    async def start(self) -> None:
        """Initialize the agent and set it to IDLE status.

        This is called once when the agent is registered with the Coordinator.
        Subclasses can override _on_start() for custom initialization
        (e.g., establishing connections, loading models).

        After start():
            - Agent status is IDLE
            - Agent is ready to receive tasks
        """
        self._logger.info("agent_starting")
        self._update_state(status=AgentStatus.IDLE)
        await self._on_start()
        self._logger.info("agent_started")

    async def stop(self) -> None:
        """Gracefully shut down the agent.

        This is called when the agent is unregistered or the system shuts down.
        Subclasses can override _on_stop() for custom cleanup
        (e.g., closing connections, flushing buffers).

        After stop():
            - Agent status is CANCELLED
            - Agent should not receive new tasks
        """
        self._logger.info("agent_stopping")
        await self._on_stop()
        self._update_state(status=AgentStatus.CANCELLED)
        self._logger.info("agent_stopped")

    # =========================================================================
    # Task Execution (Template Method)
    # =========================================================================
    # This is the core of the Template Method pattern. execute_task() defines
    # the algorithm skeleton. Subclasses fill in _validate_task() and _execute().
    # =========================================================================

    async def execute_task(self, task: TaskDefinition) -> TaskResult:
        """Execute a task using the template method pattern.

        This method orchestrates the full task execution lifecycle:
        1. Validate the task (can this agent handle it?)
        2. Set status to RUNNING
        3. Call _execute() for agent-specific logic
        4. Set status to COMPLETED or FAILED
        5. Return the TaskResult

        Subclasses should NOT override this method. Instead, override
        _execute() and _validate_task().

        Args:
            task: The task definition to execute.

        Returns:
            TaskResult with the execution outcome (success or failure).

        Raises:
            AgentError: If task validation fails (task not suitable for agent).
        """
        self._logger.info(
            "task_execution_starting",
            task_id=task.task_id,
            task_name=task.name,
        )

        # --- Step 1: Validate the task ---
        # Each agent type knows what tasks it can handle.
        # For example, CodingAgent checks for "specification" in input_data.
        is_valid = await self._validate_task(task)
        if not is_valid:
            self._logger.warning(
                "task_validation_failed",
                task_id=task.task_id,
                task_name=task.name,
            )
            raise AgentError(
                message=f"Task validation failed for agent {self.agent_id}",
                agent_id=self.agent_id,
                task_id=task.task_id,
                error_code="TASK_VALIDATION_FAILED",
                details={
                    "task_name": task.name,
                    "agent_type": self.agent_type.value,
                },
            )

        # --- Step 2: Transition to RUNNING ---
        started_at = datetime.now(timezone.utc)
        self._update_state(
            status=AgentStatus.RUNNING,
            current_task_id=task.task_id,
        )

        try:
            # --- Step 3: Execute agent-specific logic ---
            # This is the abstract method that each specialized agent implements.
            # CodingAgent calls the LLM to generate code.
            # ReviewAgent calls the LLM to review code.
            # TestAgent generates and runs tests.
            # etc.
            result = await self._execute(task)

            # --- Step 4a: Transition to COMPLETED ---
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()

            # Enrich the result with timing information
            result.completed_at = completed_at
            result.duration_seconds = duration

            # Update agent state to reflect success
            completed_tasks = list(self._state.completed_tasks) + [task.task_id]
            self._update_state(
                status=AgentStatus.IDLE,
                current_task_id=None,
                completed_tasks=completed_tasks,
            )

            self._logger.info(
                "task_execution_completed",
                task_id=task.task_id,
                duration_seconds=round(duration, 3),
                status=result.status.value,
            )

            return result

        except AgentError:
            # Re-raise AgentErrors (they already have context)
            raise

        except Exception as e:
            # --- Step 4b: Transition to FAILED ---
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()

            # Update agent state to reflect failure
            failed_tasks = list(self._state.failed_tasks) + [task.task_id]
            self._update_state(
                status=AgentStatus.IDLE,
                current_task_id=None,
                failed_tasks=failed_tasks,
                error_count=self._state.error_count + 1,
            )

            self._logger.error(
                "task_execution_failed",
                task_id=task.task_id,
                error=str(e),
                duration_seconds=round(duration, 3),
            )

            # Create a failure result with error details
            return self._create_result(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                output={},
                error=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration=duration,
            )

    # =========================================================================
    # Abstract Methods (Subclasses MUST implement these)
    # =========================================================================

    @abstractmethod
    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Execute the agent's core logic for a given task.

        This is where the agent does its actual work. Each specialized agent
        implements this differently:
        - CodingAgent: Calls LLM to generate code
        - ReviewAgent: Calls LLM to review code quality
        - TestAgent: Generates and runs tests
        - DevOpsAgent: Creates CI/CD configurations
        - DeployingAgent: Performs deployment
        - MonitorAgent: Analyzes metrics and generates feedback

        Args:
            task: The validated task definition with input_data.

        Returns:
            TaskResult with output_data containing the agent's work product.
            Use self._create_result() to construct the result.

        Note:
            This method is called AFTER _validate_task() succeeds and the
            agent status has been set to RUNNING. It should NOT handle
            status transitions — BaseAgent does that.
        """
        ...

    @abstractmethod
    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate whether this agent can handle the given task.

        Each agent type requires different input data. This method checks
        that the task's input_data contains everything needed for execution.

        Examples:
            - CodingAgent: requires "specification" and "language"
            - ReviewAgent: requires "code" and "review_criteria"
            - TestAgent: requires "code"

        Args:
            task: The task definition to validate.

        Returns:
            True if the task is valid for this agent, False otherwise.
            Returning False causes execute_task() to raise AgentError.
        """
        ...

    # =========================================================================
    # Optional Lifecycle Hooks (Subclasses CAN override these)
    # =========================================================================

    async def _on_start(self) -> None:
        """Hook called during agent startup.

        Override this for custom initialization logic:
        - Establishing connections to external services
        - Loading ML models or embeddings
        - Warming up caches

        Default implementation does nothing.
        """
        pass

    async def _on_stop(self) -> None:
        """Hook called during agent shutdown.

        Override this for custom cleanup logic:
        - Closing connections
        - Flushing buffers
        - Saving state

        Default implementation does nothing.
        """
        pass

    # =========================================================================
    # Message Handling
    # =========================================================================

    async def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Process an incoming message from the Message Bus.

        This method dispatches messages to appropriate handlers based on
        message_type. The default implementation handles:
        - TASK_ASSIGNMENT: Extracts task and calls execute_task()
        - CONTROL: Handles pause/resume/cancel commands

        Subclasses can override for custom message handling.

        Args:
            message: The incoming AgentMessage to process.

        Returns:
            Optional response message. None if no response needed.
        """
        self._logger.debug(
            "message_received",
            message_id=message.message_id,
            message_type=message.message_type.value,
            sender_id=message.sender_id,
        )

        if message.message_type == MessageType.TASK_ASSIGNMENT:
            # Extract the task from the payload and execute it
            from conductor.core.messages import TaskAssignmentPayload

            assignment = TaskAssignmentPayload(**message.payload)
            result = await self.execute_task(assignment.task)

            # Create response message with the task result
            from conductor.core.messages import TaskResultPayload

            return message.create_response(
                sender_id=self.agent_id,
                message_type=MessageType.TASK_RESULT,
                payload=TaskResultPayload(result=result).model_dump(),
            )

        elif message.message_type == MessageType.CONTROL:
            # Handle control commands (stop, pause, etc.)
            command = message.payload.get("command")
            if command == "stop":
                await self.stop()

        return None

    # =========================================================================
    # Heartbeat
    # =========================================================================

    async def send_heartbeat(self) -> None:
        """Update the agent's heartbeat timestamp.

        Called periodically by the Coordinator to verify the agent is alive.
        If an agent's heartbeat is stale (too old), the Coordinator considers
        it dead and may reassign its tasks.
        """
        self._update_state(last_heartbeat=datetime.now(timezone.utc))

    # =========================================================================
    # Internal Helper Methods
    # =========================================================================

    def _update_state(self, **kwargs: Any) -> None:
        """Update the agent's state with the given field values.

        This creates a new AgentState with the updated fields and always
        refreshes the updated_at timestamp.

        Args:
            **kwargs: Field names and values to update on the state.
                Example: _update_state(status=AgentStatus.RUNNING)
        """
        # Always update the timestamp when state changes
        kwargs["updated_at"] = datetime.now(timezone.utc)
        self._state = self._state.model_copy(update=kwargs)

    def _create_result(
        self,
        task_id: str,
        status: TaskStatus,
        output: dict[str, Any],
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        duration: Optional[float] = None,
    ) -> TaskResult:
        """Factory method for creating TaskResult instances.

        This is a convenience method for subclasses to create results
        without needing to specify the agent_id every time.

        Args:
            task_id: ID of the task that was executed.
            status: Final task status (COMPLETED or FAILED).
            output: Task-specific output data (dict).
            error: Error message if status is FAILED (optional).
            started_at: Task start time (defaults to now).
            completed_at: Task end time (optional).
            duration: Execution duration in seconds (optional).

        Returns:
            A TaskResult populated with the given values and this agent's ID.
        """
        return TaskResult(
            task_id=task_id,
            agent_id=self.agent_id,
            status=status,
            output_data=output,
            error_message=error,
            started_at=started_at or datetime.now(timezone.utc),
            completed_at=completed_at,
            duration_seconds=duration,
        )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"agent_id={self.agent_id!r}, "
            f"type={self.agent_type.value!r}, "
            f"status={self.status.value!r})"
        )
