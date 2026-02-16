"""
conductor.core.exceptions - Custom Exception Hierarchy
========================================================

This module defines a structured exception hierarchy for ConductorAI.
Instead of catching generic Exception everywhere, components raise and catch
specific exception types that carry contextual information.

Exception Hierarchy:
    ConductorError (base)
        ├── ConfigurationError     - Invalid config, missing required values
        ├── AgentError             - Agent execution failures
        ├── WorkflowError          - Workflow orchestration failures
        ├── MessageBusError        - Message publishing/subscribing failures
        ├── StateError             - State read/write failures
        └── PolicyViolationError   - Policy rule violations

Design Principles:
    1. Every exception carries structured context (not just a string message)
    2. Error codes enable programmatic handling (retry vs. abort decisions)
    3. The `details` dict can carry arbitrary debugging information
    4. All exceptions serialize cleanly to JSON (for logging and API responses)

Error Handling Flow in the Architecture:
    Agent raises AgentError
        → ErrorHandler catches it
        → ErrorHandler checks RetryPolicy
        → If retryable: retry with backoff
        → If not: escalate to WorkflowEngine
        → WorkflowEngine may abort or trigger feedback loop

Usage:
    >>> from conductor.core.exceptions import AgentError
    >>> raise AgentError(
    ...     message="LLM API call failed",
    ...     agent_id="coding-agent-01",
    ...     error_code="LLM_API_ERROR",
    ...     details={"status_code": 429, "retry_after": 30},
    ... )
"""

from __future__ import annotations

from typing import Any, Optional


# =============================================================================
# Base Exception
# =============================================================================
# All ConductorAI exceptions inherit from this base class. This allows
# catching all framework-specific errors with a single except clause:
#
#   try:
#       await agent.execute_task(task)
#   except ConductorError as e:
#       logger.error(e.message, error_code=e.error_code, details=e.details)
# =============================================================================
class ConductorError(Exception):
    """Base exception for all ConductorAI errors.

    Provides structured error information beyond a simple message string.
    All ConductorAI components should raise subclasses of this exception,
    never raw Exception or ValueError.

    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error code for programmatic handling.
            Convention: UPPER_SNAKE_CASE (e.g., "AGENT_TIMEOUT", "LLM_API_ERROR").
        details: Arbitrary dict with additional debugging context.
            Can include stack traces, request/response data, configuration
            values, or anything helpful for diagnosing the issue.

    Example:
        >>> try:
        ...     do_something()
        ... except ConductorError as e:
        ...     print(f"[{e.error_code}] {e.message}")
        ...     print(f"Details: {e.details}")
    """

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        # Call Exception.__init__ with the message so that str(exception) works
        super().__init__(message)

        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize this exception to a dictionary.

        Useful for:
            - JSON logging (structlog)
            - API error responses
            - Storing in error logs / dead letter queue

        Returns:
            Dictionary with error_type, message, error_code, and details.
        """
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code!r}, "
            f"details={self.details!r})"
        )


# =============================================================================
# Configuration Error
# =============================================================================
# Raised during startup when configuration is invalid, missing, or
# inconsistent. This should cause the application to fail fast — don't
# try to run with bad config.
# =============================================================================
class ConfigurationError(ConductorError):
    """Raised when ConductorAI configuration is invalid or missing.

    This typically occurs during startup and should cause the application
    to fail fast with a clear message about what's wrong.

    Common Causes:
        - Missing required config values (e.g., LLM API key in production)
        - Invalid config file syntax (malformed YAML)
        - Incompatible configuration combinations
        - Unable to connect to configured Redis instance

    Example:
        >>> raise ConfigurationError(
        ...     message="LLM API key is required in production",
        ...     error_code="MISSING_API_KEY",
        ...     details={"environment": "prod", "provider": "openai"},
        ... )
    """

    def __init__(
        self,
        message: str,
        error_code: str = "CONFIG_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, details=details)


# =============================================================================
# Agent Error
# =============================================================================
# Raised when an agent fails to execute a task. Carries the agent_id so
# the error handler knows which agent had the problem.
# =============================================================================
class AgentError(ConductorError):
    """Raised when an agent fails during task execution.

    The ErrorHandler uses the agent_id and error_code to decide whether
    to retry, skip, or escalate the failure.

    Common Causes:
        - LLM API call failed (rate limit, timeout, server error)
        - Task validation failed (missing required input data)
        - Agent internal logic error (bug in agent implementation)
        - Task timeout exceeded

    Attributes:
        agent_id: ID of the agent that encountered the error.
            Used by ErrorHandler to track per-agent failure counts.
        task_id: Optional ID of the task that failed.
            Used for retry tracking and dead letter queue.

    Example:
        >>> raise AgentError(
        ...     message="Code generation failed: LLM returned empty response",
        ...     agent_id="coding-agent-01",
        ...     task_id="task-abc-123",
        ...     error_code="LLM_EMPTY_RESPONSE",
        ... )
    """

    def __init__(
        self,
        message: str,
        agent_id: str,
        task_id: Optional[str] = None,
        error_code: str = "AGENT_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        # Enrich details with agent context
        enriched_details = details or {}
        enriched_details["agent_id"] = agent_id
        if task_id:
            enriched_details["task_id"] = task_id

        super().__init__(message=message, error_code=error_code, details=enriched_details)

        self.agent_id = agent_id
        self.task_id = task_id


# =============================================================================
# Workflow Error
# =============================================================================
# Raised when the workflow engine encounters a problem during orchestration.
# This is for workflow-level issues, not individual task failures.
# =============================================================================
class WorkflowError(ConductorError):
    """Raised when workflow orchestration fails.

    This covers workflow-level issues (not individual task failures):
        - Phase transition failures
        - Dependency resolution errors (circular dependencies)
        - Workflow timeout exceeded
        - Invalid workflow definition
        - Feedback loop limit exceeded

    Attributes:
        workflow_id: ID of the workflow that encountered the error.

    Example:
        >>> raise WorkflowError(
        ...     message="Circular dependency detected: step A → B → A",
        ...     workflow_id="workflow-xyz",
        ...     error_code="CIRCULAR_DEPENDENCY",
        ...     details={"cycle": ["step-A", "step-B", "step-A"]},
        ... )
    """

    def __init__(
        self,
        message: str,
        workflow_id: str,
        error_code: str = "WORKFLOW_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        enriched_details = details or {}
        enriched_details["workflow_id"] = workflow_id

        super().__init__(message=message, error_code=error_code, details=enriched_details)

        self.workflow_id = workflow_id


# =============================================================================
# Message Bus Error
# =============================================================================
# Raised when the message bus (Redis pub/sub) fails to deliver messages.
# This is a critical infrastructure error — agents can't communicate.
# =============================================================================
class MessageBusError(ConductorError):
    """Raised when the message bus fails to publish or deliver messages.

    Since the message bus is the communication backbone of ConductorAI,
    these errors are typically CRITICAL and may require system restart.

    Common Causes:
        - Redis connection lost
        - Message serialization failed
        - Channel doesn't exist
        - Message TTL expired before delivery

    Example:
        >>> raise MessageBusError(
        ...     message="Failed to publish to channel: Redis connection refused",
        ...     error_code="PUBLISH_FAILED",
        ...     details={"channel": "conductor:agent:coding-01", "redis_url": "..."},
        ... )
    """

    def __init__(
        self,
        message: str,
        error_code: str = "MESSAGE_BUS_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, details=details)


# =============================================================================
# State Error
# =============================================================================
# Raised when state read/write operations fail. State is critical for
# workflow continuity — losing state means losing workflow progress.
# =============================================================================
class StateError(ConductorError):
    """Raised when state management operations fail.

    State persistence is critical for workflow continuity. If state can't
    be saved, the system risks losing workflow progress on restart.

    Common Causes:
        - Redis write failed (disk full, memory limit)
        - State deserialization failed (schema mismatch after upgrade)
        - Concurrent state update conflict
        - State key not found (stale reference)

    Example:
        >>> raise StateError(
        ...     message="Failed to save workflow state: Redis memory limit exceeded",
        ...     error_code="STATE_WRITE_FAILED",
        ...     details={"workflow_id": "...", "state_size_bytes": 1048576},
        ... )
    """

    def __init__(
        self,
        message: str,
        error_code: str = "STATE_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, details=details)


# =============================================================================
# Policy Violation Error
# =============================================================================
# Raised when an action violates a registered policy. The policy engine
# evaluates rules before actions execute; violations block the action.
# =============================================================================
class PolicyViolationError(ConductorError):
    """Raised when an action violates a registered policy rule.

    The PolicyEngine evaluates all registered policies before allowing
    actions (task assignments, phase transitions, etc.). If any policy
    returns a violation, this error is raised to prevent the action.

    Attributes:
        policy_name: Name of the policy that was violated.
        violation_details: Specific details about what rule was broken
            and what the allowed limits/values are.

    Common Violations:
        - MaxConcurrentTasksPolicy: Too many tasks running on one agent
        - TaskTimeoutPolicy: Task timeout exceeds maximum allowed
        - PhaseGatePolicy: Prerequisites not met for phase transition

    Example:
        >>> raise PolicyViolationError(
        ...     message="Agent has too many concurrent tasks",
        ...     policy_name="MaxConcurrentTasksPolicy",
        ...     violation_details="Agent coding-01 has 3/3 tasks running",
        ...     details={"agent_id": "coding-01", "current": 3, "max": 3},
        ... )
    """

    def __init__(
        self,
        message: str,
        policy_name: str,
        violation_details: str = "",
        error_code: str = "POLICY_VIOLATION",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        enriched_details = details or {}
        enriched_details["policy_name"] = policy_name
        enriched_details["violation_details"] = violation_details

        super().__init__(message=message, error_code=error_code, details=enriched_details)

        self.policy_name = policy_name
        self.violation_details = violation_details
