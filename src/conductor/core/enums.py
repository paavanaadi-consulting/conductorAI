"""
conductor.core.enums - Type-Safe Enumerations
===============================================

This module defines all enumeration types used throughout ConductorAI.
Enums provide type safety, prevent typos, and make the codebase self-documenting.

All enums inherit from both `str` and `Enum`, which means:
    - They serialize to strings in JSON/YAML (Pydantic-friendly)
    - They can be compared with plain strings: AgentType.CODING == "coding"
    - They have human-readable representations

Architecture Mapping:
    Each enum maps directly to a concept in the architecture diagram:

    ┌─────────────────────────────────────────────────────────────────┐
    │  ORCHESTRATION LAYER                                            │
    │    MessageType: How agents communicate                          │
    │    Priority: Message/task urgency levels                        │
    ├─────────────────────────────────────────────────────────────────┤
    │  AGENT LAYER                                                    │
    │    AgentType: The 7 specialized agent roles                     │
    │    AgentStatus: Agent lifecycle states (IDLE → RUNNING → ...)   │
    │    WorkflowPhase: The 3 pipeline phases (DEV → DEVOPS → MON)   │
    ├─────────────────────────────────────────────────────────────────┤
    │  TASK TRACKING                                                  │
    │    TaskStatus: Task lifecycle (PENDING → IN_PROGRESS → ...)     │
    └─────────────────────────────────────────────────────────────────┘
"""

from enum import Enum


# =============================================================================
# Agent Type Enumeration
# =============================================================================
# Maps directly to the 7 specialized agents in the architecture diagram.
# Each agent type corresponds to a concrete agent class:
#
#   CODING    → agents/development/coding_agent.py    (generates code)
#   REVIEW    → agents/development/review_agent.py    (reviews code quality)
#   TEST_DATA → agents/development/test_data_agent.py (generates test data)
#   TEST      → agents/development/test_agent.py      (runs tests)
#   DEVOPS    → agents/devops/devops_agent.py         (creates CI/CD configs)
#   DEPLOYING → agents/devops/deploying_agent.py      (deploys applications)
#   MONITOR   → agents/monitoring/monitor_agent.py    (monitors & provides feedback)
# =============================================================================
class AgentType(str, Enum):
    """Enumeration of all specialized agent types in ConductorAI.

    The agent types are organized by their workflow phase:
        Development:  CODING, REVIEW, TEST_DATA, TEST
        DevOps:       DEVOPS, DEPLOYING
        Monitoring:   MONITOR

    Usage:
        >>> agent_type = AgentType.CODING
        >>> agent_type.value  # "coding"
        >>> agent_type == "coding"  # True (str comparison works)
    """

    # --- Development Phase Agents ---
    CODING = "coding"           # Generates or modifies source code
    REVIEW = "review"           # Reviews code for quality, bugs, best practices
    TEST_DATA = "test_data"     # Generates test data and fixtures
    TEST = "test"               # Creates and executes test suites

    # --- DevOps Phase Agents ---
    DEVOPS = "devops"           # Creates CI/CD pipelines, Dockerfiles, infra configs
    DEPLOYING = "deploying"     # Handles deployment to target environments

    # --- Monitoring & Feedback Phase Agents ---
    MONITOR = "monitor"         # Monitors deployed systems, generates feedback


# =============================================================================
# Agent Status Enumeration
# =============================================================================
# Represents the lifecycle state machine for an agent instance.
# An agent progresses through these states during its lifetime:
#
#   Created → IDLE → RUNNING → (COMPLETED | FAILED)
#                  ↘ WAITING (blocked on dependency)
#                  ↘ CANCELLED (externally stopped)
#
# The state machine is enforced by BaseAgent.execute_task() in agents/base.py.
# =============================================================================
class AgentStatus(str, Enum):
    """Lifecycle states for an agent instance.

    State Transitions:
        IDLE → RUNNING:     Agent starts executing a task
        RUNNING → COMPLETED: Task finished successfully
        RUNNING → FAILED:    Task encountered an unrecoverable error
        RUNNING → WAITING:   Agent is blocked waiting for a dependency
        WAITING → RUNNING:   Dependency resolved, agent resumes
        Any → CANCELLED:     Agent externally stopped (workflow cancel/timeout)

    Usage:
        >>> state = AgentStatus.IDLE
        >>> if state == AgentStatus.RUNNING:
        ...     print("Agent is busy")
    """

    IDLE = "idle"               # Agent is registered but not working on anything
    RUNNING = "running"         # Agent is actively executing a task
    WAITING = "waiting"         # Agent is blocked waiting for external input/dependency
    COMPLETED = "completed"     # Agent successfully completed its current task
    FAILED = "failed"           # Agent encountered an error during task execution
    CANCELLED = "cancelled"     # Agent was externally stopped (timeout or manual cancel)


# =============================================================================
# Workflow Phase Enumeration
# =============================================================================
# Maps to the three horizontal phases in the architecture diagram.
# Workflows execute phases sequentially (left to right):
#
#   DEVELOPMENT → DEVOPS → MONITORING
#       ↑                       │
#       └───── feedback loop ───┘  (red dashed arrow in diagram)
#
# The feedback loop is the key architectural feature: when the Monitor agent
# detects issues, it can trigger the Development phase to run again.
# =============================================================================
class WorkflowPhase(str, Enum):
    """The three sequential phases of the ConductorAI pipeline.

    Execution Order:
        1. DEVELOPMENT:  Code generation → Review → Testing
        2. DEVOPS:       CI/CD configuration → Deployment
        3. MONITORING:   System monitoring → Feedback generation

    Feedback Loop:
        MONITORING can trigger a return to DEVELOPMENT when issues
        are detected (e.g., performance problems, errors in production).
        This is handled by WorkflowEngine._handle_feedback().

    Usage:
        >>> phase = WorkflowPhase.DEVELOPMENT
        >>> phases = [WorkflowPhase.DEVELOPMENT, WorkflowPhase.DEVOPS]
    """

    DEVELOPMENT = "development"   # Phase 1: Code, Review, Test
    DEVOPS = "devops"             # Phase 2: Build, Configure, Deploy
    MONITORING = "monitoring"     # Phase 3: Monitor, Analyze, Feedback


# =============================================================================
# Message Type Enumeration
# =============================================================================
# Categorizes messages flowing through the Message Bus.
# Each type triggers different handling logic in the receiving agent/component:
#
#   TASK_ASSIGNMENT → Agent starts working on a new task
#   TASK_RESULT     → Agent reports completion (success or failure)
#   STATUS_UPDATE   → Agent broadcasts its current state
#   ERROR           → Error notification for error handler
#   FEEDBACK        → Monitor agent's findings sent back to development
#   CONTROL         → System-level commands (pause, resume, cancel)
# =============================================================================
class MessageType(str, Enum):
    """Types of messages that flow through the ConductorAI Message Bus.

    Message Flow Examples:
        Coordinator → Agent:  TASK_ASSIGNMENT (assigns work)
        Agent → Coordinator:  TASK_RESULT (reports completion)
        Agent → All:          STATUS_UPDATE (heartbeat/progress)
        Agent → ErrorHandler: ERROR (reports failures)
        Monitor → Coordinator: FEEDBACK (issues found, re-trigger dev)
        Coordinator → Agent:  CONTROL (pause/resume/cancel commands)

    Usage:
        >>> msg_type = MessageType.TASK_ASSIGNMENT
        >>> if msg_type == MessageType.FEEDBACK:
        ...     handle_feedback(msg)
    """

    TASK_ASSIGNMENT = "task_assignment"   # Coordinator assigns a task to an agent
    TASK_RESULT = "task_result"           # Agent reports task completion/failure
    STATUS_UPDATE = "status_update"       # Agent broadcasts status (heartbeat)
    ERROR = "error"                       # Error notification to error handler
    FEEDBACK = "feedback"                 # Monitor findings → development phase
    CONTROL = "control"                   # System commands: pause, resume, cancel


# =============================================================================
# Priority Enumeration
# =============================================================================
# Used for both messages and tasks to determine processing order.
# Higher priority items are processed first when the system is under load.
# =============================================================================
class Priority(str, Enum):
    """Priority levels for messages and tasks.

    Processing Order (highest first):
        CRITICAL → HIGH → MEDIUM → LOW

    Guidelines:
        LOW:      Background tasks, optional optimizations
        MEDIUM:   Standard workflow tasks (default)
        HIGH:     Time-sensitive tasks, blocking dependencies
        CRITICAL: System errors, security alerts, production issues

    Usage:
        >>> task = TaskDefinition(priority=Priority.HIGH, ...)
        >>> if msg.priority == Priority.CRITICAL:
        ...     process_immediately(msg)
    """

    LOW = "low"             # Background, non-urgent
    MEDIUM = "medium"       # Standard priority (default)
    HIGH = "high"           # Time-sensitive, important
    CRITICAL = "critical"   # Urgent, process immediately


# =============================================================================
# Task Status Enumeration
# =============================================================================
# Tracks the lifecycle of individual tasks within a workflow.
# A task is a unit of work assigned to a specific agent.
#
# State machine:
#   PENDING → IN_PROGRESS → (COMPLETED | FAILED)
#                         → BLOCKED (waiting for dependency)
#                         → SKIPPED (dependency failed, task not needed)
# =============================================================================
class TaskStatus(str, Enum):
    """Lifecycle states for a task within a workflow.

    State Transitions:
        PENDING → IN_PROGRESS:  Task assigned to agent, execution starts
        IN_PROGRESS → COMPLETED: Task finished successfully
        IN_PROGRESS → FAILED:    Task encountered an error
        PENDING → BLOCKED:       A dependency task failed/is not ready
        PENDING → SKIPPED:       Task skipped (dependency failed, optional task)

    Usage:
        >>> result = TaskResult(status=TaskStatus.COMPLETED, ...)
        >>> if result.status == TaskStatus.FAILED:
        ...     error_handler.handle(result)
    """

    PENDING = "pending"           # Task created but not yet started
    IN_PROGRESS = "in_progress"   # Task is currently being executed by an agent
    COMPLETED = "completed"       # Task finished successfully with output
    FAILED = "failed"             # Task failed with an error
    BLOCKED = "blocked"           # Task cannot start (dependency not met)
    SKIPPED = "skipped"           # Task intentionally skipped (e.g., optional after failure)
