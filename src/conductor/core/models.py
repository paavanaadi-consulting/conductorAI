"""
conductor.core.models - Core Data Models
==========================================

This module defines the fundamental Pydantic data models that flow through
every layer of ConductorAI. These models are the "lingua franca" — every
component speaks in terms of these types.

Model Hierarchy:
    AgentIdentity      → Who is this agent? (identity card)
    TaskDefinition     → What work needs to be done? (job ticket)
    TaskResult         → What happened when the work was done? (job report)
    WorkflowDefinition → What's the full pipeline plan? (project plan)

Data Flow Through Architecture:
    ┌──────────────┐     TaskDefinition      ┌──────────────┐
    │  Workflow     │ ─────────────────────→  │    Agent      │
    │  Engine       │                         │  (executes)   │
    │              │  ←─────────────────────  │              │
    └──────────────┘     TaskResult           └──────────────┘
           │                                         │
           │  WorkflowDefinition                     │  AgentIdentity
           ↓                                         ↓
    ┌──────────────┐                          ┌──────────────┐
    │  State       │                          │  Coordinator  │
    │  Manager     │                          │  (registers)  │
    └──────────────┘                          └──────────────┘

Design Principles:
    1. Immutable by convention: Models represent snapshots, not mutable state
    2. Self-validating: Pydantic enforces type/value constraints at creation
    3. Serializable: All models can be converted to/from JSON (for Redis, APIs)
    4. Documented: Every field has a description for API docs and IDE hints
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from conductor.core.enums import AgentType, Priority, TaskStatus, WorkflowPhase


# =============================================================================
# Helper: Generate Unique IDs
# =============================================================================
# We use UUID4 for all identifiers. This ensures uniqueness across distributed
# systems without requiring a central ID generator.
# =============================================================================
def _generate_id() -> str:
    """Generate a unique identifier using UUID4.

    Returns:
        A string UUID like "a1b2c3d4-e5f6-7890-abcd-ef1234567890".
        UUID4 is randomly generated, providing 2^122 possible values —
        collision probability is negligibly small.
    """
    return str(uuid4())


def _now() -> datetime:
    """Get the current UTC timestamp.

    We always use UTC to avoid timezone confusion across distributed systems.
    Every timestamp in ConductorAI is UTC.

    Returns:
        Current datetime in UTC timezone.
    """
    return datetime.now(timezone.utc)


# =============================================================================
# Agent Identity Model
# =============================================================================
# Think of this as an agent's "ID card". It identifies WHO the agent is,
# WHAT type it is, and WHAT version of the agent implementation is running.
# This is separate from AgentState (which tracks what the agent is DOING).
# =============================================================================
class AgentIdentity(BaseModel):
    """Identity information for a registered agent.

    This is the agent's "ID card" — it tells you who the agent is and what
    role it plays. Every agent has exactly one AgentIdentity, created when
    the agent is instantiated.

    This is intentionally separate from AgentState (Day 2):
        - AgentIdentity: WHO the agent is (static, doesn't change)
        - AgentState: WHAT the agent is doing (dynamic, changes frequently)

    Attributes:
        agent_id: Globally unique identifier for this agent instance.
            Auto-generated using UUID4 if not provided.
        agent_type: The role this agent plays (CODING, REVIEW, etc.).
            Determines which tasks the agent can handle.
        name: Human-readable name for logging and UI display.
            Example: "coding-agent-01", "primary-reviewer"
        version: Semantic version of the agent implementation.
            Used for tracking which version produced what output.
        description: Optional longer description of what this agent does.
            Useful for documentation and debugging.

    Example:
        >>> identity = AgentIdentity(
        ...     agent_type=AgentType.CODING,
        ...     name="primary-coder",
        ...     description="Main code generation agent using GPT-4",
        ... )
        >>> identity.agent_id  # auto-generated UUID
        'a1b2c3d4-...'
    """

    agent_id: str = Field(
        default_factory=_generate_id,
        description="Unique identifier for this agent instance (UUID4)",
    )
    agent_type: AgentType = Field(
        description="The specialized role this agent fulfills",
    )
    name: str = Field(
        description="Human-readable agent name for logging and display",
    )
    version: str = Field(
        default="0.1.0",
        description="Semantic version of the agent implementation",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional description of the agent's purpose and capabilities",
    )


# =============================================================================
# Task Definition Model
# =============================================================================
# A TaskDefinition is a "job ticket" — it describes a unit of work that an
# agent needs to perform. Tasks flow from the WorkflowEngine through the
# AgentCoordinator to individual agents.
#
# The input_data dict is intentionally flexible (dict[str, Any]) because
# different agent types need different inputs:
#   - CodingAgent needs: {"specification": "...", "language": "python"}
#   - ReviewAgent needs: {"code": "...", "review_criteria": [...]}
#   - TestAgent needs: {"code": "...", "test_data": [...]}
# =============================================================================
class TaskDefinition(BaseModel):
    """Definition of a task to be executed by an agent.

    A task is the fundamental unit of work in ConductorAI. The workflow engine
    creates tasks based on WorkflowSteps, and the coordinator dispatches them
    to appropriate agents.

    Task Lifecycle:
        1. Created by WorkflowEngine with status PENDING
        2. Dispatched by AgentCoordinator to an available agent
        3. Agent executes and produces a TaskResult
        4. Result flows back to WorkflowEngine for next-step decisions

    Attributes:
        task_id: Unique identifier for tracking this task through the system.
        name: Short, descriptive name. Example: "Generate REST API endpoint"
        description: Detailed description of what needs to be done.
        assigned_to: Which agent type should handle this task. None means
            the coordinator will choose based on availability.
        priority: Urgency level. Higher priority tasks are dispatched first.
        input_data: Flexible dict containing task-specific input. The schema
            depends on the target agent type (see agent documentation).
        timeout_seconds: Maximum time this task can run before being cancelled.
            Prevents hung tasks from blocking the workflow.
        created_at: When this task definition was created (UTC).
        metadata: Arbitrary key-value pairs for tracking, tagging, or passing
            additional context that doesn't fit the standard fields.

    Example:
        >>> task = TaskDefinition(
        ...     name="Generate User API",
        ...     description="Create a REST API for user CRUD operations",
        ...     assigned_to=AgentType.CODING,
        ...     priority=Priority.HIGH,
        ...     input_data={
        ...         "specification": "Create GET/POST/PUT/DELETE for /users",
        ...         "language": "python",
        ...         "framework": "fastapi",
        ...     },
        ... )
    """

    task_id: str = Field(
        default_factory=_generate_id,
        description="Unique task identifier (UUID4)",
    )
    name: str = Field(
        description="Short descriptive task name",
    )
    description: str = Field(
        default="",
        description="Detailed description of the work to be done",
    )
    assigned_to: Optional[AgentType] = Field(
        default=None,
        description="Target agent type (None = coordinator chooses)",
    )
    priority: Priority = Field(
        default=Priority.MEDIUM,
        description="Task urgency level",
    )
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Task-specific input data (schema varies by agent type)",
    )
    timeout_seconds: int = Field(
        default=120,
        ge=1,
        le=3600,
        description="Maximum execution time in seconds",
    )
    created_at: datetime = Field(
        default_factory=_now,
        description="Task creation timestamp (UTC)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata for tracking and tagging",
    )


# =============================================================================
# Task Result Model
# =============================================================================
# A TaskResult is a "job report" — it describes what happened when an agent
# executed a task. Results flow from agents back through the coordinator to
# the workflow engine for next-step decisions.
#
# Like input_data, output_data is a flexible dict because different agents
# produce different outputs:
#   - CodingAgent produces: {"code": "...", "language": "python", "files": [...]}
#   - ReviewAgent produces: {"approved": true, "findings": [...], "quality": 0.85}
#   - TestAgent produces: {"passed": 5, "failed": 1, "results": [...]}
# =============================================================================
class TaskResult(BaseModel):
    """Result of a task execution by an agent.

    After an agent completes (or fails) a task, it produces a TaskResult
    that captures the outcome, timing, and any output data.

    The workflow engine uses TaskResults to:
        - Decide whether to proceed to the next step
        - Pass output_data as input to dependent tasks
        - Determine if feedback loops should trigger
        - Record execution history for debugging

    Attributes:
        task_id: References the TaskDefinition that was executed.
        agent_id: Which agent instance performed the work.
        status: Final status of the task (COMPLETED or FAILED).
        output_data: Task-specific output. The schema depends on the agent
            type that produced it (see agent documentation).
        error_message: Human-readable error description if status is FAILED.
            None when the task completed successfully.
        started_at: When the agent began executing this task (UTC).
        completed_at: When the agent finished (success or failure) (UTC).
            None if the task is still in progress.
        duration_seconds: Wall-clock execution time. Calculated from
            started_at and completed_at. Useful for performance monitoring.
        metadata: Additional context about the execution (retries, warnings, etc.).

    Example:
        >>> result = TaskResult(
        ...     task_id="abc-123",
        ...     agent_id="agent-456",
        ...     status=TaskStatus.COMPLETED,
        ...     output_data={"code": "def hello(): ...", "language": "python"},
        ...     started_at=datetime.now(timezone.utc),
        ...     completed_at=datetime.now(timezone.utc),
        ...     duration_seconds=2.5,
        ... )
    """

    task_id: str = Field(
        description="ID of the TaskDefinition that was executed",
    )
    agent_id: str = Field(
        description="ID of the agent that performed the execution",
    )
    status: TaskStatus = Field(
        description="Final task status: COMPLETED or FAILED",
    )
    output_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Task-specific output data (schema varies by agent type)",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error description if task failed (None on success)",
    )
    started_at: datetime = Field(
        default_factory=_now,
        description="Execution start timestamp (UTC)",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Execution end timestamp (UTC, None if still running)",
    )
    duration_seconds: Optional[float] = Field(
        default=None,
        ge=0,
        description="Wall-clock execution time in seconds",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional execution context (retries, warnings, etc.)",
    )


# =============================================================================
# Workflow Definition Model
# =============================================================================
# A WorkflowDefinition is a "project plan" — it describes the full pipeline
# of tasks that need to execute across all phases (Dev → DevOps → Monitor).
#
# This is a high-level definition. The WorkflowEngine (Day 5) will break
# this down into executable WorkflowSteps with dependency resolution.
# =============================================================================
class WorkflowDefinition(BaseModel):
    """High-level definition of a multi-phase workflow.

    A workflow represents a complete pipeline execution, from code generation
    through deployment and monitoring. It contains:
        - Which phases to execute (some workflows may skip monitoring)
        - Tasks for each phase
        - Metadata for tracking and auditing

    The WorkflowEngine (see orchestration/workflow_engine.py) takes a
    WorkflowDefinition and executes it, managing phase transitions,
    dependency resolution, and feedback loops.

    Attributes:
        workflow_id: Unique identifier for this workflow execution.
        name: Human-readable workflow name.
            Example: "Build REST API v2", "Fix authentication bug"
        description: Detailed description of the workflow's purpose.
        phases: Ordered list of phases to execute. The standard pipeline is
            [DEVELOPMENT, DEVOPS, MONITORING], but subsets are allowed.
        tasks: All tasks across all phases. The workflow engine organizes
            these into phases and resolves dependencies.
        created_at: When this workflow was defined (UTC).
        metadata: Arbitrary metadata (project name, requester, tags, etc.).

    Example:
        >>> workflow = WorkflowDefinition(
        ...     name="Build User Service",
        ...     description="Generate, test, and deploy the user microservice",
        ...     phases=[WorkflowPhase.DEVELOPMENT, WorkflowPhase.DEVOPS],
        ...     tasks=[coding_task, review_task, test_task, deploy_task],
        ... )
    """

    workflow_id: str = Field(
        default_factory=_generate_id,
        description="Unique workflow identifier (UUID4)",
    )
    name: str = Field(
        description="Human-readable workflow name",
    )
    description: str = Field(
        default="",
        description="Detailed description of the workflow's purpose",
    )
    phases: list[WorkflowPhase] = Field(
        default_factory=lambda: [
            WorkflowPhase.DEVELOPMENT,
            WorkflowPhase.DEVOPS,
            WorkflowPhase.MONITORING,
        ],
        description="Ordered list of phases to execute",
    )
    tasks: list[TaskDefinition] = Field(
        default_factory=list,
        description="All tasks across all phases",
    )
    created_at: datetime = Field(
        default_factory=_now,
        description="Workflow creation timestamp (UTC)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata (project, requester, tags, etc.)",
    )
