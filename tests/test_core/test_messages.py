"""
Tests for conductor.core.messages
===================================

These tests verify the agent communication message types:
    - AgentMessage creation, serialization, TTL, response creation
    - Typed payload models (TaskAssignment, TaskResult, Feedback, Error, Status)

All tests are unit tests — no I/O, no Message Bus needed.
"""

import time
from datetime import datetime, timezone

import pytest

from conductor.core.enums import AgentType, MessageType, Priority, TaskStatus
from conductor.core.messages import (
    AgentMessage,
    ErrorPayload,
    FeedbackPayload,
    StatusUpdatePayload,
    TaskAssignmentPayload,
    TaskResultPayload,
)
from conductor.core.models import TaskDefinition, TaskResult


# =============================================================================
# Test: AgentMessage
# =============================================================================
class TestAgentMessage:
    """Tests for the AgentMessage envelope model."""

    def test_create_minimal_message(self) -> None:
        """AgentMessage should create with just message_type and sender_id."""
        msg = AgentMessage(
            message_type=MessageType.STATUS_UPDATE,
            sender_id="agent-01",
        )
        assert msg.message_type == MessageType.STATUS_UPDATE
        assert msg.sender_id == "agent-01"
        assert msg.recipient_id is None  # Broadcast
        assert msg.payload == {}
        assert msg.priority == Priority.MEDIUM

    def test_auto_generates_message_id(self) -> None:
        """message_id should be auto-generated as a UUID."""
        msg = AgentMessage(
            message_type=MessageType.CONTROL,
            sender_id="coordinator",
        )
        assert len(msg.message_id) == 36
        assert msg.message_id.count("-") == 4

    def test_auto_generates_timestamp(self) -> None:
        """timestamp should be auto-generated as current UTC time."""
        msg = AgentMessage(
            message_type=MessageType.CONTROL,
            sender_id="coordinator",
        )
        assert isinstance(msg.timestamp, datetime)
        now = datetime.now(timezone.utc)
        delta = (now - msg.timestamp).total_seconds()
        assert delta < 5

    def test_full_message_creation(self) -> None:
        """AgentMessage should accept all fields."""
        msg = AgentMessage(
            message_type=MessageType.TASK_ASSIGNMENT,
            sender_id="coordinator",
            recipient_id="coding-agent-01",
            payload={"task_name": "Generate API"},
            correlation_id="corr-123",
            priority=Priority.HIGH,
            ttl_seconds=60,
            metadata={"trace_id": "trace-abc"},
        )
        assert msg.recipient_id == "coding-agent-01"
        assert msg.correlation_id == "corr-123"
        assert msg.priority == Priority.HIGH
        assert msg.ttl_seconds == 60
        assert msg.metadata["trace_id"] == "trace-abc"

    def test_is_expired_no_ttl(self) -> None:
        """Messages without TTL should never expire."""
        msg = AgentMessage(
            message_type=MessageType.CONTROL,
            sender_id="coordinator",
            ttl_seconds=None,
        )
        assert msg.is_expired() is False

    def test_is_expired_with_ttl_not_expired(self) -> None:
        """Messages within TTL should not be expired."""
        msg = AgentMessage(
            message_type=MessageType.CONTROL,
            sender_id="coordinator",
            ttl_seconds=3600,  # 1 hour
        )
        assert msg.is_expired() is False

    def test_is_expired_with_ttl_expired(self) -> None:
        """Messages past their TTL should be expired."""
        # Create a message with timestamp 10 seconds ago but TTL of 1 second
        from datetime import timedelta

        old_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        msg = AgentMessage(
            message_type=MessageType.CONTROL,
            sender_id="coordinator",
            ttl_seconds=1,
            timestamp=old_time,
        )
        assert msg.is_expired() is True

    def test_create_response(self) -> None:
        """create_response() should create a linked response message."""
        original = AgentMessage(
            message_id="orig-123",
            message_type=MessageType.TASK_ASSIGNMENT,
            sender_id="coordinator",
            recipient_id="coding-01",
            priority=Priority.HIGH,
        )

        response = original.create_response(
            sender_id="coding-01",
            message_type=MessageType.TASK_RESULT,
            payload={"result": "success"},
        )

        # Response should be linked to original
        assert response.correlation_id == "orig-123"
        assert response.sender_id == "coding-01"
        assert response.recipient_id == "coordinator"  # Reply to sender
        assert response.priority == Priority.HIGH  # Inherited
        assert response.message_type == MessageType.TASK_RESULT
        assert response.payload == {"result": "success"}
        # Should have a new message_id
        assert response.message_id != original.message_id

    def test_create_response_with_existing_correlation(self) -> None:
        """If original has correlation_id, response should use it."""
        original = AgentMessage(
            message_type=MessageType.TASK_ASSIGNMENT,
            sender_id="coordinator",
            correlation_id="thread-456",
        )

        response = original.create_response(
            sender_id="agent-01",
            message_type=MessageType.TASK_RESULT,
            payload={},
        )

        # Should use the existing correlation_id, not the message_id
        assert response.correlation_id == "thread-456"

    def test_serialization_roundtrip(self) -> None:
        """AgentMessage should serialize to dict and back."""
        original = AgentMessage(
            message_type=MessageType.FEEDBACK,
            sender_id="monitor-01",
            payload={"findings": ["issue1"]},
        )
        data = original.model_dump()
        restored = AgentMessage(**data)
        assert restored.message_id == original.message_id
        assert restored.message_type == original.message_type
        assert restored.payload == original.payload


# =============================================================================
# Test: Typed Payloads
# =============================================================================
class TestTaskAssignmentPayload:
    """Tests for TaskAssignmentPayload."""

    def test_create_with_task(self) -> None:
        """Should wrap a TaskDefinition."""
        task = TaskDefinition(
            name="Generate Code",
            assigned_to=AgentType.CODING,
            input_data={"spec": "Build API"},
        )
        payload = TaskAssignmentPayload(task=task)
        assert payload.task.name == "Generate Code"
        assert payload.task.input_data["spec"] == "Build API"

    def test_serialization_into_message(self) -> None:
        """Payload should serialize into AgentMessage.payload dict."""
        task = TaskDefinition(name="Test Task")
        payload = TaskAssignmentPayload(task=task)
        data = payload.model_dump()
        assert "task" in data
        assert data["task"]["name"] == "Test Task"


class TestTaskResultPayload:
    """Tests for TaskResultPayload."""

    def test_create_with_result(self) -> None:
        """Should wrap a TaskResult."""
        result = TaskResult(
            task_id="t1",
            agent_id="a1",
            status=TaskStatus.COMPLETED,
            output_data={"code": "print('hello')"},
        )
        payload = TaskResultPayload(result=result)
        assert payload.result.status == TaskStatus.COMPLETED


class TestFeedbackPayload:
    """Tests for FeedbackPayload."""

    def test_create_with_findings(self) -> None:
        """Should hold monitor agent feedback."""
        feedback = FeedbackPayload(
            source_agent_id="monitor-01",
            findings=["High error rate", "Slow response time"],
            severity="error",
            recommendations=["Add caching", "Optimize queries"],
            affected_task_ids=["task-code-01"],
        )
        assert len(feedback.findings) == 2
        assert feedback.severity == "error"
        assert len(feedback.recommendations) == 2

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        feedback = FeedbackPayload(source_agent_id="monitor-01")
        assert feedback.findings == []
        assert feedback.severity == "info"
        assert feedback.recommendations == []
        assert feedback.metrics == {}


class TestErrorPayload:
    """Tests for ErrorPayload."""

    def test_create_with_error_info(self) -> None:
        """Should hold error information."""
        error = ErrorPayload(
            error_code="LLM_TIMEOUT",
            error_message="OpenAI API timed out after 30s",
            agent_id="coding-01",
            task_id="task-abc",
        )
        assert error.error_code == "LLM_TIMEOUT"
        assert error.agent_id == "coding-01"

    def test_optional_fields(self) -> None:
        """agent_id, task_id, and traceback should be optional."""
        error = ErrorPayload(
            error_code="UNKNOWN",
            error_message="Something went wrong",
        )
        assert error.agent_id is None
        assert error.task_id is None
        assert error.traceback is None


class TestStatusUpdatePayload:
    """Tests for StatusUpdatePayload."""

    def test_create_with_status(self) -> None:
        """Should hold agent status information."""
        status = StatusUpdatePayload(
            agent_id="coding-01",
            status="running",
            current_task_id="task-123",
            progress_percent=75.0,
            message="Generating REST API endpoints",
        )
        assert status.agent_id == "coding-01"
        assert status.progress_percent == 75.0

    def test_progress_validation(self) -> None:
        """progress_percent must be between 0 and 100."""
        with pytest.raises(Exception):
            StatusUpdatePayload(
                agent_id="a1",
                status="running",
                progress_percent=150.0,
            )
