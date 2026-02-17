"""
conductor.orchestration.agent_coordinator - Agent Lifecycle & Task Dispatch
============================================================================

This module implements the Agent Coordinator — the central registry and dispatcher
that manages all agents in the ConductorAI system. It is the single point of
contact for agent registration, task assignment, and lifecycle management.

Architecture Context:
    The Coordinator sits between the WorkflowEngine and the Agent Layer.
    It translates high-level "execute this task" requests into specific
    agent assignments, respecting policies and circuit breakers.

    ┌────────────────┐    dispatch_task()    ┌────────────────────────┐
    │ WorkflowEngine │ ─────────────────→   │   AgentCoordinator     │
    │                │                       │                        │
    │                │ ←──── TaskResult ──── │   ┌─ Agent Registry ─┐ │
    └────────────────┘                       │   │ coding-01: IDLE  │ │
                                             │   │ review-01: BUSY  │ │
         ┌──────────────┐                    │   │ test-01: IDLE    │ │
         │ PolicyEngine │ ←── check ──────── │   └─────────────────┘ │
         └──────────────┘                    │                        │
                                             │   ┌─ ErrorHandler ──┐ │
         ┌──────────────┐                    │   │ CircuitBreakers │ │
         │  MessageBus  │ ←── publish ────── │   └─────────────────┘ │
         └──────────────┘                    │                        │
                                             │   ┌─ StateManager ──┐ │
         ┌──────────────┐                    │   │ Agent states    │ │
         │ StateManager │ ←── save ───────── │   └─────────────────┘ │
         └──────────────┘                    └────────────────────────┘

Coordinator Responsibilities:
    1. **Agent Registry**: Register/unregister agents with the system
    2. **Task Dispatch**: Find the best available agent for a task and assign it
    3. **State Sync**: Keep the StateManager up-to-date with agent states
    4. **Policy Check**: Consult the PolicyEngine before dispatching tasks
    5. **Error Routing**: Route failures to the ErrorHandler for retry/escalate

Task Dispatch Algorithm:
    1. Caller requests dispatch_task(task).
    2. Coordinator determines the target agent_type from the task.
    3. Finds agents of that type with status == IDLE.
    4. Checks PolicyEngine (concurrent task limits, agent availability).
    5. Assigns task to the first available agent.
    6. Agent executes via execute_task() → returns TaskResult.
    7. Coordinator saves the result and returns it to the caller.

    If no agent is available: raises AgentError with "NO_AVAILABLE_AGENT".

Usage:
    >>> coordinator = AgentCoordinator(bus, state_manager, policy_engine, error_handler)
    >>> await coordinator.start()
    >>>
    >>> # Register agents
    >>> coding_agent = CodingAgent("coding-01", config=config)
    >>> await coordinator.register_agent(coding_agent)
    >>>
    >>> # Dispatch a task
    >>> task = TaskDefinition(name="Generate API", assigned_to=AgentType.CODING)
    >>> result = await coordinator.dispatch_task(task)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from conductor.agents.base import BaseAgent
from conductor.core.enums import AgentStatus, AgentType, MessageType, TaskStatus
from conductor.core.exceptions import AgentError
from conductor.core.messages import AgentMessage
from conductor.core.models import TaskDefinition, TaskResult
from conductor.core.state import AgentState
from conductor.orchestration.error_handler import ErrorAction, ErrorHandler
from conductor.orchestration.message_bus import MessageBus
from conductor.orchestration.policy_engine import PolicyEngine
from conductor.orchestration.state_manager import StateManager


# =============================================================================
# Logger Setup
# =============================================================================
logger = structlog.get_logger()


class AgentCoordinator:
    """Central coordinator for agent lifecycle and task dispatch.

    The AgentCoordinator is the nerve center of ConductorAI. It:
    1. Maintains a registry of all active agents.
    2. Dispatches tasks to the best available agent.
    3. Syncs agent state to the StateManager after every change.
    4. Enforces policies before task assignment.
    5. Routes errors to the ErrorHandler for retry/escalate.

    The coordinator does NOT decide WHAT tasks to run (that's the
    WorkflowEngine's job). It only decides HOW and WHERE to run them
    (which specific agent instance gets the task).

    Attributes:
        _agents: Registry of all active agents, keyed by agent_id.
        _message_bus: For publishing status updates and error notifications.
        _state_manager: For persisting agent state changes.
        _policy_engine: For enforcing dispatch policies (concurrency, availability).
        _error_handler: For handling task execution failures.
        _started: Whether the coordinator has been started.

    Example:
        >>> coordinator = AgentCoordinator(bus, sm, pe, eh)
        >>> await coordinator.start()
        >>> await coordinator.register_agent(coding_agent)
        >>> result = await coordinator.dispatch_task(task)
    """

    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager,
        policy_engine: Optional[PolicyEngine] = None,
        error_handler: Optional[ErrorHandler] = None,
    ) -> None:
        """Initialize the Agent Coordinator.

        Args:
            message_bus: The message bus for publishing status updates.
            state_manager: The state manager for persisting agent states.
            policy_engine: Optional policy engine for enforcing dispatch rules.
                If None, no policy checks are performed (useful for testing).
            error_handler: Optional error handler for managing task failures.
                If None, errors are raised directly to the caller.
        """
        # --- Dependencies ---
        self._message_bus = message_bus
        self._state_manager = state_manager
        self._policy_engine = policy_engine
        self._error_handler = error_handler

        # --- Agent Registry ---
        # Maps agent_id → BaseAgent instance. This is the in-memory registry
        # of all active agents. Agents are added via register_agent() and
        # removed via unregister_agent().
        self._agents: dict[str, BaseAgent] = {}

        # --- Lifecycle flag ---
        self._started: bool = False

        # --- Logger ---
        self._logger = logger.bind(component="agent_coordinator")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def agent_count(self) -> int:
        """Return the number of registered agents."""
        return len(self._agents)

    @property
    def is_started(self) -> bool:
        """Return whether the coordinator has been started."""
        return self._started

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start the coordinator.

        This initializes the coordinator and marks it as ready to accept
        agent registrations and task dispatches.
        """
        self._started = True
        self._logger.info("coordinator_started")

    async def stop(self) -> None:
        """Stop the coordinator and all registered agents.

        Gracefully shuts down all agents by calling their stop() method,
        then clears the registry.
        """
        self._logger.info("coordinator_stopping", agent_count=len(self._agents))

        # Stop all agents in registration order
        for agent_id, agent in list(self._agents.items()):
            try:
                await agent.stop()
                # Sync the stopped state
                await self._sync_agent_state(agent)
                self._logger.debug("agent_stopped", agent_id=agent_id)
            except Exception as e:
                self._logger.error(
                    "agent_stop_failed",
                    agent_id=agent_id,
                    error=str(e),
                )

        self._agents.clear()
        self._started = False
        self._logger.info("coordinator_stopped")

    # =========================================================================
    # Agent Registration
    # =========================================================================

    async def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the coordinator.

        Registration performs these steps:
            1. Validates no agent with the same ID is already registered.
            2. Starts the agent (calls agent.start()).
            3. Adds the agent to the registry.
            4. Syncs the agent's initial state to the StateManager.
            5. Publishes a status update to the message bus.

        Args:
            agent: The BaseAgent instance to register. Must have a unique
                agent_id not already in the registry.

        Raises:
            AgentError: If an agent with the same ID is already registered.
        """
        if agent.agent_id in self._agents:
            raise AgentError(
                message=f"Agent '{agent.agent_id}' is already registered",
                agent_id=agent.agent_id,
                error_code="AGENT_ALREADY_REGISTERED",
            )

        # Start the agent (sets status to IDLE, calls _on_start hook)
        await agent.start()

        # Add to the registry
        self._agents[agent.agent_id] = agent

        # Persist the agent's initial state
        await self._sync_agent_state(agent)

        self._logger.info(
            "agent_registered",
            agent_id=agent.agent_id,
            agent_type=agent.agent_type.value,
            total_agents=len(self._agents),
        )

    async def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the coordinator.

        Unregistration performs these steps:
            1. Looks up the agent by ID.
            2. Stops the agent (calls agent.stop()).
            3. Removes the agent from the registry.
            4. Deletes the agent's state from the StateManager.

        Args:
            agent_id: The ID of the agent to unregister.

        Returns:
            True if the agent was found and unregistered, False if not found.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            self._logger.warning(
                "agent_not_found_for_unregister",
                agent_id=agent_id,
            )
            return False

        # Stop the agent gracefully
        await agent.stop()

        # Remove from registry
        del self._agents[agent_id]

        # Remove persisted state
        await self._state_manager.delete_agent_state(agent_id)

        self._logger.info(
            "agent_unregistered",
            agent_id=agent_id,
            total_agents=len(self._agents),
        )
        return True

    # =========================================================================
    # Agent Queries
    # =========================================================================

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Look up a registered agent by ID.

        Args:
            agent_id: The unique agent identifier.

        Returns:
            The BaseAgent instance, or None if not registered.
        """
        return self._agents.get(agent_id)

    def get_agents_by_type(self, agent_type: AgentType) -> list[BaseAgent]:
        """Find all registered agents of a specific type.

        Args:
            agent_type: The AgentType to filter by.

        Returns:
            List of agents matching the type (may be empty).
        """
        return [
            agent for agent in self._agents.values()
            if agent.agent_type == agent_type
        ]

    def get_available_agents(
        self,
        agent_type: Optional[AgentType] = None,
    ) -> list[BaseAgent]:
        """Find agents that are available to accept tasks.

        An agent is "available" if its status is IDLE. Optionally filter
        by agent_type.

        Args:
            agent_type: Optional type filter. None means all types.

        Returns:
            List of available agents (may be empty).
        """
        available = []
        for agent in self._agents.values():
            if agent.status != AgentStatus.IDLE:
                continue
            if agent_type is not None and agent.agent_type != agent_type:
                continue
            available.append(agent)
        return available

    def list_agents(self) -> list[BaseAgent]:
        """Return all registered agents.

        Returns:
            List of all registered BaseAgent instances.
        """
        return list(self._agents.values())

    # =========================================================================
    # Task Dispatch
    # =========================================================================

    async def dispatch_task(self, task: TaskDefinition) -> TaskResult:
        """Dispatch a task to the best available agent.

        This is the main entry point for task execution. The coordinator:
        1. Determines the target agent type from the task.
        2. Finds available agents of that type.
        3. Checks policies (if a PolicyEngine is configured).
        4. Assigns the task to the first available agent.
        5. Executes the task and returns the result.
        6. Handles failures via the ErrorHandler (if configured).

        Args:
            task: The task to dispatch. The ``assigned_to`` field determines
                which agent type handles it. If None, raises AgentError.

        Returns:
            TaskResult with the execution outcome.

        Raises:
            AgentError: If no agent type is specified (assigned_to is None).
            AgentError: If no available agent of the required type exists.
            AgentError: If policy checks fail and no error handler is configured.
        """
        self._logger.info(
            "dispatching_task",
            task_id=task.task_id,
            task_name=task.name,
            assigned_to=task.assigned_to.value if task.assigned_to else None,
        )

        # --- Step 1: Determine the target agent type ---
        if task.assigned_to is None:
            raise AgentError(
                message="Task has no assigned_to agent type",
                agent_id="coordinator",
                task_id=task.task_id,
                error_code="NO_AGENT_TYPE",
            )

        # --- Step 2: Find available agents of the target type ---
        available = self.get_available_agents(agent_type=task.assigned_to)

        if not available:
            raise AgentError(
                message=(
                    f"No available agent of type '{task.assigned_to.value}'. "
                    f"Registered agents of this type: "
                    f"{len(self.get_agents_by_type(task.assigned_to))}"
                ),
                agent_id="coordinator",
                task_id=task.task_id,
                error_code="NO_AVAILABLE_AGENT",
            )

        # --- Step 3: Policy check (if engine is configured) ---
        if self._policy_engine is not None:
            agent_states = [a.state for a in self._agents.values()]
            target_agent = available[0]
            context = {
                "task": task,
                "agent_state": target_agent.state,
                "agent_states": agent_states,
            }

            is_allowed = await self._policy_engine.check(context)
            if not is_allowed:
                raise AgentError(
                    message=(
                        f"Policy check failed for task '{task.name}' "
                        f"dispatched to '{target_agent.agent_id}'"
                    ),
                    agent_id=target_agent.agent_id,
                    task_id=task.task_id,
                    error_code="POLICY_VIOLATION",
                )

        # --- Step 4: Assign to the first available agent ---
        agent = available[0]

        self._logger.info(
            "task_assigned",
            task_id=task.task_id,
            agent_id=agent.agent_id,
            agent_type=agent.agent_type.value,
        )

        # --- Step 5: Execute the task ---
        try:
            result = await agent.execute_task(task)

            # Sync state after execution
            await self._sync_agent_state(agent)

            # Save the task result
            await self._state_manager.save_task_result(result)

            self._logger.info(
                "task_completed",
                task_id=task.task_id,
                agent_id=agent.agent_id,
                status=result.status.value,
            )

            return result

        except Exception as e:
            # Sync the agent state (may now be IDLE with error_count incremented)
            await self._sync_agent_state(agent)

            # --- Step 6: Error handling ---
            if self._error_handler is not None:
                action = await self._error_handler.handle_error(e, {
                    "agent_id": agent.agent_id,
                    "task_id": task.task_id,
                    "attempt": 0,
                })
                self._logger.warning(
                    "task_dispatch_error_handled",
                    task_id=task.task_id,
                    agent_id=agent.agent_id,
                    error_action=action.value,
                    error=str(e),
                )

            # Re-raise so the caller (WorkflowEngine) can decide what to do
            raise

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    async def _sync_agent_state(self, agent: BaseAgent) -> None:
        """Persist an agent's current state to the StateManager.

        Called after every state change (registration, task completion,
        failure, unregistration) to keep the StateManager in sync.

        Args:
            agent: The agent whose state should be persisted.
        """
        await self._state_manager.save_agent_state(agent.state)
