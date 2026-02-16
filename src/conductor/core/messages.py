"""
conductor.core.messages - Agent Communication Message Types
============================================================

This module defines the message types that flow through the ConductorAI
Message Bus. Messages are the primary communication mechanism between
agents and the orchestration layer.

Message Architecture:
    All messages share a common envelope (AgentMessage) with typed payloads.
    The message_type field determines what's in the payload:

    ┌─────────────────────────────────────────────────────────────┐
    │  AgentMessage (envelope)                                     │
    │  ├── message_id:      Unique identifier for tracking         │
    │  ├── message_type:    What kind of message this is           │
    │  ├── sender_id:       Who sent it                            │
    │  ├── recipient_id:    Who it's for (None = broadcast)        │
    │  ├── payload:         The actual data (dict)                 │
    │  ├── correlation_id:  Links request → response pairs         │
    │  ├── priority:        Processing priority                    │
    │  ├── timestamp:       When it was created                    │
    │  └── ttl_seconds:     Time-to-live (auto-expire)             │
    └─────────────────────────────────────────────────────────────┘

Typed Payloads:
    To maintain type safety, we define Pydantic models for common payload
    structures. These are used to serialize INTO the payload dict and
    deserialize FROM it:

    - TaskAssignmentPayload: Coordinator → Agent (here's your task)
    - TaskResultPayload:     Agent → Coordinator (here's my result)
    - FeedbackPayload:       Monitor → Coordinator (issues found)
    - ErrorPayload:          Agent → ErrorHandler (something broke)
    - StatusUpdatePayload:   Agent → All (heartbeat / progress)

Channel Naming Convention:
    Messages are published to named channels on the Message Bus:
    - "conductor:agent:{agent_id}"     → Direct message to specific agent
    - "conductor:broadcast"            → Message to all agents
    - "conductor:phase:{phase_name}"   → Phase-level messages
    - "conductor:workflow:{workflow_id}"→ Workflow-level coordination
    - "conductor:dlq"                  → Dead letter queue

Usage:
    >>> msg = AgentMessage(
    ...     message_type=MessageType.TASK_ASSIGNMENT,
    ...     sender_id="coordinator",
    ...     recipient_id="coding-agent-01",
    ...     payload=TaskAssignmentPayload(task=my_task).model_dump(),
    ... )
    >>> await message_bus.publish("conductor:agent:coding-agent-01", msg)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from conductor.core.enums import MessageType, Priority
from conductor.core.models import TaskDefinition, TaskResult


# =============================================================================
# Helper Functions
# =============================================================================
def _generate_message_id() -> str:
    """Generate a unique message identifier using UUID4."""
    return str(uuid4())


def _now() -> datetime:
    """Get the current UTC timestamp."""
    return datetime.now(timezone.utc)


# =============================================================================
# Agent Message (The Envelope)
# =============================================================================
# Every message flowing through the Message Bus uses this common envelope.
# Think of it like an email: it has a sender, recipient, subject (type),
# and body (payload). The correlation_id is like a thread ID for tracking
# request-response pairs.
# =============================================================================
class AgentMessage(BaseModel):
    """Universal message envelope for agent communication.

    All messages in ConductorAI use this common structure. The message_type
    field determines how the payload should be interpreted:

    - TASK_ASSIGNMENT: payload contains TaskAssignmentPayload data
    - TASK_RESULT:     payload contains TaskResultPayload data
    - FEEDBACK:        payload contains FeedbackPayload data
    - ERROR:           payload contains ErrorPayload data
    - STATUS_UPDATE:   payload contains StatusUpdatePayload data
    - CONTROL:         payload contains control commands

    Attributes:
        message_id: Unique identifier for deduplication and tracking.
            Auto-generated UUID4. Used in logging and dead letter queue.
        message_type: Categorizes the message for routing and handling.
            Determines which handler processes this message.
        sender_id: ID of the agent/component that created this message.
            "coordinator" for orchestration layer messages.
        recipient_id: Target agent ID. None means broadcast to all agents
            on the subscribed channel. Specific ID for direct messages.
        payload: The actual message data. Structure depends on message_type.
            Always a dict for JSON serialization compatibility.
        correlation_id: Links related messages together. When agent A sends
            a request and agent B responds, both messages share the same
            correlation_id. Essential for the request-response pattern.
        priority: Message processing priority. CRITICAL messages are handled
            before MEDIUM ones in the queue.
        timestamp: When this message was created (UTC). Used for ordering
            and TTL calculations.
        ttl_seconds: Time-to-live in seconds. Messages older than TTL are
            discarded by the message bus. None means no expiration.
        metadata: Arbitrary key-value pairs for tracking (trace IDs, etc.).

    Example:
        >>> msg = AgentMessage(
        ...     message_type=MessageType.TASK_ASSIGNMENT,
        ...     sender_id="coordinator",
        ...     recipient_id="coding-agent-01",
        ...     payload={"task": task.model_dump()},
        ...     priority=Priority.HIGH,
        ... )
    """

    message_id: str = Field(
        default_factory=_generate_message_id,
        description="Unique message identifier for tracking and deduplication",
    )
    message_type: MessageType = Field(
        description="Message category (determines payload interpretation)",
    )
    sender_id: str = Field(
        description="ID of the sending agent/component",
    )
    recipient_id: Optional[str] = Field(
        default=None,
        description="Target agent ID (None = broadcast to all)",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Message data (structure depends on message_type)",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Links request-response message pairs together",
    )
    priority: Priority = Field(
        default=Priority.MEDIUM,
        description="Message processing priority",
    )
    timestamp: datetime = Field(
        default_factory=_now,
        description="Message creation timestamp (UTC)",
    )
    ttl_seconds: Optional[int] = Field(
        default=None,
        ge=1,
        description="Time-to-live in seconds (None = no expiration)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata (trace IDs, tags, etc.)",
    )

    def is_expired(self) -> bool:
        """Check if this message has exceeded its TTL.

        Returns:
            True if the message has a TTL and it has been exceeded.
            False if no TTL is set or the message is still valid.
        """
        if self.ttl_seconds is None:
            return False
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl_seconds

    def create_response(
        self,
        sender_id: str,
        message_type: MessageType,
        payload: dict[str, Any],
    ) -> "AgentMessage":
        """Create a response message linked to this one via correlation_id.

        This is a convenience method for the request-response pattern.
        The response automatically:
        - Gets a new message_id
        - Inherits the correlation_id (or uses original message_id)
        - Swaps sender/recipient
        - Gets a fresh timestamp

        Args:
            sender_id: ID of the responding agent.
            message_type: Type of the response message.
            payload: Response data.

        Returns:
            A new AgentMessage linked to this message.
        """
        return AgentMessage(
            message_type=message_type,
            sender_id=sender_id,
            recipient_id=self.sender_id,  # Reply to original sender
            payload=payload,
            correlation_id=self.correlation_id or self.message_id,
            priority=self.priority,  # Inherit priority from request
        )


# =============================================================================
# Typed Payloads
# =============================================================================
# These models define the structure of common message payloads.
# They're serialized to dict for storage in AgentMessage.payload,
# and deserialized back for type-safe access.
#
# Usage Pattern:
#   Sending:  msg.payload = TaskAssignmentPayload(task=my_task).model_dump()
#   Receiving: assignment = TaskAssignmentPayload(**msg.payload)
# =============================================================================


class TaskAssignmentPayload(BaseModel):
    """Payload for TASK_ASSIGNMENT messages.

    Sent by the Coordinator to an agent when assigning a new task.
    Contains the full TaskDefinition with all input data.

    Attributes:
        task: The complete task definition to be executed.

    Example:
        >>> payload = TaskAssignmentPayload(task=my_task)
        >>> msg = AgentMessage(
        ...     message_type=MessageType.TASK_ASSIGNMENT,
        ...     sender_id="coordinator",
        ...     payload=payload.model_dump(),
        ... )
    """

    task: TaskDefinition = Field(
        description="The task definition to be executed by the receiving agent",
    )


class TaskResultPayload(BaseModel):
    """Payload for TASK_RESULT messages.

    Sent by an agent back to the Coordinator after task execution.
    Contains the full TaskResult with output data or error information.

    Attributes:
        result: The task execution result (success or failure).

    Example:
        >>> payload = TaskResultPayload(result=my_result)
        >>> msg = AgentMessage(
        ...     message_type=MessageType.TASK_RESULT,
        ...     sender_id="coding-agent-01",
        ...     payload=payload.model_dump(),
        ... )
    """

    result: TaskResult = Field(
        description="The task execution result",
    )


class FeedbackPayload(BaseModel):
    """Payload for FEEDBACK messages.

    Sent by the Monitor Agent when it detects issues that need attention.
    This triggers the feedback loop: Monitor → Coordinator → Development Phase.

    The severity field helps the Coordinator decide whether to:
    - "info":     Log it and continue (no action needed)
    - "warning":  Flag for review but don't block
    - "error":    Trigger re-development of the affected component
    - "critical": Halt deployment and trigger immediate fixes

    Attributes:
        source_agent_id: Which monitor agent generated this feedback.
        findings: List of specific issues found (human-readable strings).
        severity: Overall severity level of the findings.
        recommendations: Suggested actions to resolve the findings.
        affected_task_ids: IDs of tasks whose output is affected.
        metrics: Optional numerical metrics that triggered the feedback.

    Example:
        >>> feedback = FeedbackPayload(
        ...     source_agent_id="monitor-01",
        ...     findings=["Response time exceeds 500ms", "Error rate at 5%"],
        ...     severity="error",
        ...     recommendations=["Optimize database queries", "Add caching"],
        ...     affected_task_ids=["task-code-123"],
        ... )
    """

    source_agent_id: str = Field(
        description="ID of the monitor agent that generated this feedback",
    )
    findings: list[str] = Field(
        default_factory=list,
        description="List of specific issues found",
    )
    severity: str = Field(
        default="info",
        description="Overall severity: 'info', 'warning', 'error', 'critical'",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Suggested actions to resolve findings",
    )
    affected_task_ids: list[str] = Field(
        default_factory=list,
        description="IDs of tasks whose output is affected by these findings",
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Numerical metrics that triggered the feedback",
    )


class ErrorPayload(BaseModel):
    """Payload for ERROR messages.

    Sent by any component when an error occurs. The Error Handler processes
    these to decide whether to retry, skip, or escalate.

    Attributes:
        error_code: Machine-readable error code (e.g., "LLM_API_ERROR").
            Used by ErrorHandler for retry decisions.
        error_message: Human-readable error description.
        agent_id: ID of the agent that encountered the error (if applicable).
        task_id: ID of the task that failed (if applicable).
        traceback: Optional Python traceback string for debugging.

    Example:
        >>> error = ErrorPayload(
        ...     error_code="LLM_TIMEOUT",
        ...     error_message="OpenAI API timed out after 30s",
        ...     agent_id="coding-agent-01",
        ...     task_id="task-abc",
        ... )
    """

    error_code: str = Field(
        description="Machine-readable error code for programmatic handling",
    )
    error_message: str = Field(
        description="Human-readable error description",
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="ID of the agent that encountered the error",
    )
    task_id: Optional[str] = Field(
        default=None,
        description="ID of the task that failed",
    )
    traceback: Optional[str] = Field(
        default=None,
        description="Python traceback string for debugging",
    )


class StatusUpdatePayload(BaseModel):
    """Payload for STATUS_UPDATE messages.

    Sent periodically by agents as a heartbeat and progress report.
    The Coordinator uses these to detect stuck/dead agents.

    Attributes:
        agent_id: ID of the agent reporting status.
        status: Current agent status (from AgentStatus enum value).
        current_task_id: ID of the task currently being executed (if any).
        progress_percent: Optional execution progress (0-100).
        message: Optional human-readable status message.

    Example:
        >>> status = StatusUpdatePayload(
        ...     agent_id="coding-agent-01",
        ...     status="running",
        ...     current_task_id="task-123",
        ...     progress_percent=60,
        ...     message="Generating REST API endpoints",
        ... )
    """

    agent_id: str = Field(
        description="ID of the agent reporting status",
    )
    status: str = Field(
        description="Current agent status (AgentStatus enum value)",
    )
    current_task_id: Optional[str] = Field(
        default=None,
        description="ID of the task currently being executed",
    )
    progress_percent: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
        description="Task execution progress percentage (0-100)",
    )
    message: Optional[str] = Field(
        default=None,
        description="Human-readable status message",
    )
