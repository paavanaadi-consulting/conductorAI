"""
conductor.facade - ConductorAI Top-Level Facade
==================================================

This module implements the ConductorAI facade — the single entry point
that ties together all framework layers into a clean, easy-to-use API.
It is the public interface that users interact with.

Architecture Context:
    The ConductorAI facade sits on top of all layers and orchestrates
    their initialization, lifecycle, and teardown.

    ┌──────────────────────────────────────────────────┐
    │              ConductorAI (Facade)                 │
    │                                                   │
    │  ┌─────────────────────────────────────────────┐ │
    │  │         Orchestration Layer                   │ │
    │  │  WorkflowEngine, Coordinator, MessageBus     │ │
    │  │  StateManager, PolicyEngine, ErrorHandler    │ │
    │  └─────────────────────┬───────────────────────┘ │
    │                        │                          │
    │  ┌─────────────────────▼───────────────────────┐ │
    │  │            Agent Layer                        │ │
    │  │  CodingAgent, ReviewAgent, TestAgent, etc.   │ │
    │  └─────────────────────┬───────────────────────┘ │
    │                        │                          │
    │  ┌─────────────────────▼───────────────────────┐ │
    │  │         Infrastructure Layer                  │ │
    │  │  ArtifactStore, (Storage, Repos, ...)         │ │
    │  └─────────────────────┬───────────────────────┘ │
    │                        │                          │
    │  ┌─────────────────────▼───────────────────────┐ │
    │  │         Integration Layer                     │ │
    │  │  LLM Providers, Notifications                 │ │
    │  └─────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────┘

Usage:
    >>> from conductor.facade import ConductorAI
    >>> from conductor.core.config import ConductorConfig
    >>>
    >>> config = ConductorConfig()
    >>> conductor = ConductorAI(config)
    >>> await conductor.initialize()
    >>>
    >>> # Register agents
    >>> await conductor.register_agent(coding_agent)
    >>> await conductor.register_agent(review_agent)
    >>>
    >>> # Run a workflow
    >>> state = await conductor.run_workflow(workflow_definition)
    >>>
    >>> # Clean up
    >>> await conductor.shutdown()

    Or with async context manager:
    >>> async with ConductorAI(config) as conductor:
    ...     await conductor.register_agent(coding_agent)
    ...     state = await conductor.run_workflow(definition)
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from conductor.agents.base import BaseAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.core.state import WorkflowState
from conductor.infrastructure.artifact_store import (
    Artifact,
    ArtifactStore,
    InMemoryArtifactStore,
)
from conductor.integrations.llm.base import BaseLLMProvider
from conductor.integrations.llm.factory import create_llm_provider
from conductor.orchestration.agent_coordinator import AgentCoordinator
from conductor.orchestration.error_handler import ErrorHandler
from conductor.orchestration.message_bus import InMemoryMessageBus, MessageBus
from conductor.orchestration.policy_engine import PolicyEngine
from conductor.orchestration.state_manager import InMemoryStateManager, StateManager
from conductor.orchestration.workflow_engine import WorkflowEngine


# =============================================================================
# Logger
# =============================================================================
logger = structlog.get_logger()


class ConductorAI:
    """Top-level facade for the ConductorAI multi-agent framework.

    ConductorAI is the single entry point for users of the framework.
    It manages the lifecycle of all internal components:

    1. **Configuration**: Loads and validates settings
    2. **Infrastructure**: Sets up artifact storage
    3. **Orchestration**: Initializes message bus, state manager,
       coordinator, workflow engine, error handler, policy engine
    4. **Integration**: Initializes LLM providers
    5. **Agents**: Registers and manages specialized agents

    Lifecycle:
        1. ``ConductorAI(config)`` — Instantiate with configuration
        2. ``await initialize()`` — Start all components
        3. ``await register_agent(agent)`` — Add agents
        4. ``await run_workflow(definition)`` — Execute workflows
        5. ``await shutdown()`` — Clean up all resources

    Or use the async context manager:
        async with ConductorAI(config) as conductor:
            ...

    Attributes:
        _config: ConductorAI configuration.
        _message_bus: Communication layer between components.
        _state_manager: State persistence layer.
        _error_handler: Error handling and circuit breakers.
        _policy_engine: Policy enforcement for workflow rules.
        _coordinator: Agent registry and task dispatch.
        _workflow_engine: Multi-phase workflow execution.
        _artifact_store: Artifact persistence layer.
        _initialized: Whether initialize() has been called.

    Example:
        >>> config = ConductorConfig()
        >>> conductor = ConductorAI(config)
        >>> await conductor.initialize()
        >>> await conductor.register_agent(coding_agent)
        >>> state = await conductor.run_workflow(my_workflow)
        >>> await conductor.shutdown()
    """

    def __init__(
        self,
        config: Optional[ConductorConfig] = None,
        *,
        message_bus: Optional[MessageBus] = None,
        state_manager: Optional[StateManager] = None,
        artifact_store: Optional[ArtifactStore] = None,
        error_handler: Optional[ErrorHandler] = None,
        policy_engine: Optional[PolicyEngine] = None,
        max_feedback_loops: int = 3,
    ) -> None:
        """Initialize the ConductorAI facade.

        Args:
            config: ConductorAI configuration. Defaults to ConductorConfig()
                which loads from environment and conductor.yaml.
            message_bus: Optional custom message bus. Defaults to InMemoryMessageBus.
            state_manager: Optional custom state manager. Defaults to InMemoryStateManager.
            artifact_store: Optional custom artifact store. Defaults to InMemoryArtifactStore.
            error_handler: Optional custom error handler. Defaults to ErrorHandler.
            policy_engine: Optional custom policy engine. Defaults to PolicyEngine.
            max_feedback_loops: Maximum MONITORING → DEVELOPMENT cycles.
                Default is 3. Set to 0 to disable feedback loops.
        """
        # --- Configuration ---
        self._config = config or ConductorConfig()

        # --- Infrastructure Layer ---
        self._artifact_store = artifact_store or InMemoryArtifactStore()

        # --- Orchestration Layer ---
        self._message_bus = message_bus or InMemoryMessageBus()
        self._state_manager = state_manager or InMemoryStateManager()
        self._error_handler = error_handler or ErrorHandler(
            message_bus=self._message_bus,
            state_manager=self._state_manager,
        )
        self._policy_engine = policy_engine or PolicyEngine()

        # --- Coordinator and Workflow Engine ---
        self._coordinator = AgentCoordinator(
            message_bus=self._message_bus,
            state_manager=self._state_manager,
            policy_engine=self._policy_engine,
            error_handler=self._error_handler,
        )
        self._workflow_engine = WorkflowEngine(
            coordinator=self._coordinator,
            state_manager=self._state_manager,
            policy_engine=self._policy_engine,
            max_feedback_loops=max_feedback_loops,
        )

        # --- Tracking ---
        self._initialized = False
        self._logger = logger.bind(component="conductor_ai")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def config(self) -> ConductorConfig:
        """Access the configuration."""
        return self._config

    @property
    def coordinator(self) -> AgentCoordinator:
        """Access the Agent Coordinator for direct agent management."""
        return self._coordinator

    @property
    def workflow_engine(self) -> WorkflowEngine:
        """Access the Workflow Engine for direct workflow control."""
        return self._workflow_engine

    @property
    def message_bus(self) -> MessageBus:
        """Access the Message Bus for direct pub/sub."""
        return self._message_bus

    @property
    def state_manager(self) -> StateManager:
        """Access the State Manager for direct state queries."""
        return self._state_manager

    @property
    def artifact_store(self) -> ArtifactStore:
        """Access the Artifact Store for direct artifact queries."""
        return self._artifact_store

    @property
    def error_handler(self) -> ErrorHandler:
        """Access the Error Handler."""
        return self._error_handler

    @property
    def policy_engine(self) -> PolicyEngine:
        """Access the Policy Engine."""
        return self._policy_engine

    @property
    def is_initialized(self) -> bool:
        """Check if the facade has been initialized."""
        return self._initialized

    # =========================================================================
    # Lifecycle Management
    # =========================================================================

    async def initialize(self) -> None:
        """Start all internal components.

        This method initializes the orchestration layer in the correct
        order to ensure all dependencies are ready:
        1. Connect the message bus
        2. Connect the state manager
        3. Start the coordinator

        After this method returns, the system is ready to accept
        agent registrations and workflow executions.

        Idempotent: Safe to call multiple times.
        """
        if self._initialized:
            self._logger.debug("conductor_already_initialized")
            return

        self._logger.info("conductor_initializing")

        # Connect infrastructure
        await self._message_bus.connect()
        await self._state_manager.connect()

        # Start coordinator
        await self._coordinator.start()

        self._initialized = True
        self._logger.info("conductor_initialized")

    async def shutdown(self) -> None:
        """Gracefully shut down all components.

        This method tears down components in reverse order:
        1. Stop the coordinator (stops all agents)
        2. Disconnect the state manager
        3. Disconnect the message bus

        After this method returns, the system is fully stopped.

        Idempotent: Safe to call multiple times.
        """
        if not self._initialized:
            self._logger.debug("conductor_not_initialized_skipping_shutdown")
            return

        self._logger.info("conductor_shutting_down")

        # Stop coordinator (stops all registered agents)
        await self._coordinator.stop()

        # Disconnect infrastructure
        await self._state_manager.disconnect()
        await self._message_bus.disconnect()

        self._initialized = False
        self._logger.info("conductor_shutdown_complete")

    # =========================================================================
    # Async Context Manager
    # =========================================================================

    async def __aenter__(self) -> ConductorAI:
        """Enter the async context manager.

        Automatically calls initialize().

        Usage:
            async with ConductorAI(config) as conductor:
                # conductor is initialized and ready
                ...
        """
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the async context manager.

        Automatically calls shutdown(), even if an exception occurred.
        """
        await self.shutdown()

    # =========================================================================
    # Agent Management
    # =========================================================================

    async def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the coordinator.

        The agent will be started (via agent.start()) and added to the
        coordinator's registry. It will then be available for task dispatch.

        Args:
            agent: The specialized agent to register.

        Raises:
            RuntimeError: If ConductorAI has not been initialized.
        """
        self._ensure_initialized()
        await self._coordinator.register_agent(agent)
        self._logger.info(
            "agent_registered",
            agent_id=agent.agent_id,
            agent_type=agent.agent_type.value,
        )

    async def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from the coordinator.

        The agent will be stopped and removed from the registry.

        Args:
            agent_id: The ID of the agent to unregister.

        Raises:
            RuntimeError: If ConductorAI has not been initialized.
        """
        self._ensure_initialized()
        await self._coordinator.unregister_agent(agent_id)
        self._logger.info("agent_unregistered", agent_id=agent_id)

    # =========================================================================
    # Workflow Execution
    # =========================================================================

    async def run_workflow(
        self,
        definition: WorkflowDefinition,
    ) -> WorkflowState:
        """Execute a complete multi-phase workflow.

        This is the primary method for running workflows. It delegates to
        the WorkflowEngine which handles:
        - Phase iteration (DEVELOPMENT → DEVOPS → MONITORING)
        - Task dispatch to appropriate agents
        - Phase gate checks (PolicyEngine)
        - Feedback loops (Monitor → Development)
        - State persistence

        Args:
            definition: The workflow definition with tasks and phases.

        Returns:
            WorkflowState with the final status and all task results.

        Raises:
            RuntimeError: If ConductorAI has not been initialized.
            WorkflowError: If the workflow fails a phase gate check.
        """
        self._ensure_initialized()
        self._logger.info(
            "workflow_starting",
            workflow_name=definition.name,
            task_count=len(definition.tasks),
            phase_count=len(definition.phases),
        )

        state = await self._workflow_engine.run_workflow(definition)

        self._logger.info(
            "workflow_completed",
            workflow_name=definition.name,
            status=state.status.value,
            completed_tasks=state.completed_task_count,
            failed_tasks=state.failed_task_count,
        )

        return state

    async def dispatch_task(self, task: TaskDefinition) -> Any:
        """Dispatch a single task to an appropriate agent.

        This is a convenience method for executing individual tasks
        without a full workflow. Useful for one-off tasks or debugging.

        Args:
            task: The task definition to execute.

        Returns:
            TaskResult from the agent that executed the task.

        Raises:
            RuntimeError: If ConductorAI has not been initialized.
        """
        self._ensure_initialized()
        return await self._coordinator.dispatch_task(task)

    # =========================================================================
    # Artifact Management
    # =========================================================================

    async def save_artifact(self, artifact: Artifact) -> None:
        """Save a workflow artifact to the artifact store.

        Args:
            artifact: The artifact to save.
        """
        await self._artifact_store.save(artifact)

    async def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve an artifact by its ID.

        Args:
            artifact_id: The artifact's unique identifier.

        Returns:
            The Artifact if found, None otherwise.
        """
        return await self._artifact_store.get(artifact_id)

    async def get_workflow_artifacts(self, workflow_id: str) -> list[Artifact]:
        """Get all artifacts produced during a workflow.

        Args:
            workflow_id: The workflow's unique identifier.

        Returns:
            List of artifacts for that workflow, sorted by creation time.
        """
        return await self._artifact_store.list_by_workflow(workflow_id)

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _ensure_initialized(self) -> None:
        """Check that initialize() has been called.

        Raises:
            RuntimeError: If the facade has not been initialized.
        """
        if not self._initialized:
            raise RuntimeError(
                "ConductorAI has not been initialized. "
                "Call await conductor.initialize() or use 'async with ConductorAI() as conductor:'"
            )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"ConductorAI("
            f"initialized={self._initialized}, "
            f"agents={len(self._coordinator._agents) if self._initialized else 0})"
        )
