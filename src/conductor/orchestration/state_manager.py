"""
conductor.orchestration.state_manager - State Persistence Infrastructure
==========================================================================

This module implements the State Manager — the persistent storage layer
for agent states, workflow states, and task results in ConductorAI.

Architecture:
    The State Manager sits alongside the Message Bus in the orchestration layer:

    ┌──────────────┐     save/get      ┌──────────────────┐
    │  Agent        │ ──────────────→  │                   │
    │               │                   │  State Manager   │
    │               │ ←─────────────   │                   │
    └──────────────┘    AgentState     └──────────────────┘
                                             │
    ┌──────────────┐     save/get            │  Stores:
    │  Workflow     │ ──────────────→        │  - AgentState
    │  Engine       │                        │  - WorkflowState
    │               │ ←─────────────        │  - TaskResult
    └──────────────┘  WorkflowState          │

Key Schema:
    State is stored using a key-value pattern:
        - agent:{agent_id}          → AgentState (JSON)
        - workflow:{workflow_id}    → WorkflowState (JSON)
        - task_result:{task_id}     → TaskResult (JSON)

Implementations:
    - StateManager (ABC):          Abstract interface
    - InMemoryStateManager:        Dict-based for dev/testing
    - (Future) RedisStateManager:  Redis-backed for production
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from conductor.core.models import TaskResult
from conductor.core.state import AgentState, WorkflowState

logger = logging.getLogger(__name__)


# =============================================================================
# Abstract Base Class: StateManager
# =============================================================================
# Defines the contract for all state persistence implementations.
# Every method operates on one of three entity types:
#   1. AgentState   — per-agent dynamic state
#   2. WorkflowState — per-workflow aggregate state
#   3. TaskResult    — per-task execution results
#
# Design Decision: Why separate from the Message Bus?
#   - Different access patterns: state is read-heavy, messages are write-heavy
#   - Different durability needs: state MUST persist, messages can be transient
#   - Different backends: state uses Redis hashes, messages use Redis pub/sub
# =============================================================================
class StateManager(ABC):
    """Abstract base class for state persistence implementations.

    All state manager implementations (InMemory, Redis, etc.) must implement
    these methods. Components should type-hint against this ABC.

    Example:
        >>> async def save_progress(sm: StateManager, state: AgentState):
        ...     await sm.save_agent_state(state)
        ...     retrieved = await sm.get_agent_state(state.agent_id)
    """

    # -------------------------------------------------------------------------
    # Connection Lifecycle
    # -------------------------------------------------------------------------
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the state storage backend.

        Raises:
            StateError: If connection cannot be established.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully disconnect from the state storage backend.

        Raises:
            StateError: If disconnection fails.
        """

    # -------------------------------------------------------------------------
    # Agent State Operations
    # -------------------------------------------------------------------------
    @abstractmethod
    async def save_agent_state(self, state: AgentState) -> None:
        """Save or update an agent's state.

        If state for this agent_id already exists, it is overwritten.

        Args:
            state: The AgentState to persist.

        Raises:
            StateError: If the write operation fails.
        """

    @abstractmethod
    async def get_agent_state(self, agent_id: str) -> Optional[AgentState]:
        """Retrieve an agent's state by its ID.

        Args:
            agent_id: The unique agent identifier.

        Returns:
            The AgentState if found, None otherwise.

        Raises:
            StateError: If the read operation fails.
        """

    @abstractmethod
    async def delete_agent_state(self, agent_id: str) -> bool:
        """Delete an agent's state.

        Args:
            agent_id: The unique agent identifier.

        Returns:
            True if the state was found and deleted, False if not found.

        Raises:
            StateError: If the delete operation fails.
        """

    @abstractmethod
    async def list_agent_states(self) -> list[AgentState]:
        """List all stored agent states.

        Returns:
            A list of all AgentState objects currently stored.

        Raises:
            StateError: If the read operation fails.
        """

    # -------------------------------------------------------------------------
    # Workflow State Operations
    # -------------------------------------------------------------------------
    @abstractmethod
    async def save_workflow_state(self, state: WorkflowState) -> None:
        """Save or update a workflow's state.

        Args:
            state: The WorkflowState to persist.

        Raises:
            StateError: If the write operation fails.
        """

    @abstractmethod
    async def get_workflow_state(
        self, workflow_id: str
    ) -> Optional[WorkflowState]:
        """Retrieve a workflow's state by its ID.

        Args:
            workflow_id: The unique workflow identifier.

        Returns:
            The WorkflowState if found, None otherwise.

        Raises:
            StateError: If the read operation fails.
        """

    # -------------------------------------------------------------------------
    # Task Result Operations
    # -------------------------------------------------------------------------
    @abstractmethod
    async def save_task_result(self, result: TaskResult) -> None:
        """Save a task execution result.

        Args:
            result: The TaskResult to persist.

        Raises:
            StateError: If the write operation fails.
        """

    @abstractmethod
    async def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """Retrieve a task result by its task ID.

        Args:
            task_id: The unique task identifier.

        Returns:
            The TaskResult if found, None otherwise.

        Raises:
            StateError: If the read operation fails.
        """


# =============================================================================
# InMemoryStateManager Implementation
# =============================================================================
# Development and testing implementation using Python dicts.
# Provides the same interface as a Redis-backed implementation but
# stores everything in process memory.
#
# Key Data Structures:
#   _agent_states:    dict[agent_id, AgentState]
#   _workflow_states: dict[workflow_id, WorkflowState]
#   _task_results:    dict[task_id, TaskResult]
# =============================================================================
class InMemoryStateManager(StateManager):
    """In-memory state manager for development and testing.

    Stores all state in Python dicts. Data is lost when the process ends.
    NOT suitable for production (no persistence, single-process only).

    Example:
        >>> sm = InMemoryStateManager()
        >>> await sm.connect()
        >>> await sm.save_agent_state(my_agent_state)
        >>> state = await sm.get_agent_state("coding-01")
        >>> await sm.disconnect()
    """

    def __init__(self) -> None:
        # Primary storage dicts keyed by entity ID
        self._agent_states: dict[str, AgentState] = {}
        self._workflow_states: dict[str, WorkflowState] = {}
        self._task_results: dict[str, TaskResult] = {}

        # Connection state flag
        self._connected: bool = False

    # -------------------------------------------------------------------------
    # Connection Lifecycle
    # -------------------------------------------------------------------------
    async def connect(self) -> None:
        """Mark the state manager as connected."""
        self._connected = True
        logger.info("InMemoryStateManager connected")

    async def disconnect(self) -> None:
        """Clear all stored state and mark as disconnected."""
        self._agent_states.clear()
        self._workflow_states.clear()
        self._task_results.clear()
        self._connected = False
        logger.info("InMemoryStateManager disconnected")

    # -------------------------------------------------------------------------
    # Agent State Operations
    # -------------------------------------------------------------------------
    async def save_agent_state(self, state: AgentState) -> None:
        """Save or update an agent's state in the in-memory dict.

        Uses agent_id as the key. If the agent already has a stored state,
        it is replaced with the new one (last-write-wins).

        Args:
            state: The AgentState to store.
        """
        self._agent_states[state.agent_id] = state
        logger.debug(
            "Saved agent state: %s (status=%s)", state.agent_id, state.status
        )

    async def get_agent_state(self, agent_id: str) -> Optional[AgentState]:
        """Retrieve an agent's state by ID.

        Args:
            agent_id: The agent's unique identifier.

        Returns:
            The AgentState if found, None if no state exists for this ID.
        """
        return self._agent_states.get(agent_id)

    async def delete_agent_state(self, agent_id: str) -> bool:
        """Delete an agent's state from the in-memory dict.

        Args:
            agent_id: The agent's unique identifier.

        Returns:
            True if the state was found and deleted, False if not found.
        """
        if agent_id in self._agent_states:
            del self._agent_states[agent_id]
            logger.debug("Deleted agent state: %s", agent_id)
            return True
        return False

    async def list_agent_states(self) -> list[AgentState]:
        """Return all stored agent states as a list.

        Returns:
            A list of all AgentState objects. Order is not guaranteed.
        """
        return list(self._agent_states.values())

    # -------------------------------------------------------------------------
    # Workflow State Operations
    # -------------------------------------------------------------------------
    async def save_workflow_state(self, state: WorkflowState) -> None:
        """Save or update a workflow's state.

        Args:
            state: The WorkflowState to store.
        """
        self._workflow_states[state.workflow_id] = state
        logger.debug(
            "Saved workflow state: %s (phase=%s, status=%s)",
            state.workflow_id,
            state.current_phase,
            state.status,
        )

    async def get_workflow_state(
        self, workflow_id: str
    ) -> Optional[WorkflowState]:
        """Retrieve a workflow's state by ID.

        Args:
            workflow_id: The workflow's unique identifier.

        Returns:
            The WorkflowState if found, None if not found.
        """
        return self._workflow_states.get(workflow_id)

    # -------------------------------------------------------------------------
    # Task Result Operations
    # -------------------------------------------------------------------------
    async def save_task_result(self, result: TaskResult) -> None:
        """Save a task execution result.

        Args:
            result: The TaskResult to store.
        """
        self._task_results[result.task_id] = result
        logger.debug(
            "Saved task result: %s (status=%s)", result.task_id, result.status
        )

    async def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """Retrieve a task result by task ID.

        Args:
            task_id: The task's unique identifier.

        Returns:
            The TaskResult if found, None if not found.
        """
        return self._task_results.get(task_id)
