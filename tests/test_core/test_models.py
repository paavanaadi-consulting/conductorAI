"""
Tests for conductor.core.models
=================================

These tests verify that the core Pydantic data models work correctly:
    - AgentIdentity: Agent identification and metadata
    - TaskDefinition: Task specification and validation
    - TaskResult: Task execution outcomes
    - WorkflowDefinition: Multi-phase workflow plans

All tests are unit tests — pure data validation, no I/O.
"""

from datetime import datetime, timezone

import pytest

from conductor.core.enums import AgentType, Priority, TaskStatus, WorkflowPhase
from conductor.core.models import (
    AgentIdentity,
    TaskDefinition,
    TaskResult,
    WorkflowDefinition,
)


# =============================================================================
# Test: AgentIdentity
# =============================================================================
class TestAgentIdentity:
    """Tests for the AgentIdentity model."""

    def test_create_with_required_fields(self) -> None:
        """AgentIdentity should create with just agent_type and name."""
        identity = AgentIdentity(
            agent_type=AgentType.CODING,
            name="test-coder",
        )
        assert identity.agent_type == AgentType.CODING
        assert identity.name == "test-coder"

    def test_auto_generates_agent_id(self) -> None:
        """agent_id should be auto-generated as a UUID if not provided."""
        identity = AgentIdentity(
            agent_type=AgentType.REVIEW,
            name="test-reviewer",
        )
        # UUID4 format: 8-4-4-4-12 hex characters
        assert len(identity.agent_id) == 36
        assert identity.agent_id.count("-") == 4

    def test_explicit_agent_id(self) -> None:
        """Explicitly provided agent_id should be used."""
        identity = AgentIdentity(
            agent_id="custom-id-123",
            agent_type=AgentType.CODING,
            name="custom-coder",
        )
        assert identity.agent_id == "custom-id-123"

    def test_default_version(self) -> None:
        """Default version should be 0.1.0."""
        identity = AgentIdentity(
            agent_type=AgentType.TEST,
            name="test-agent",
        )
        assert identity.version == "0.1.0"

    def test_optional_description(self) -> None:
        """Description should be optional (None by default)."""
        identity = AgentIdentity(
            agent_type=AgentType.MONITOR,
            name="monitor-agent",
        )
        assert identity.description is None

        identity_with_desc = AgentIdentity(
            agent_type=AgentType.MONITOR,
            name="monitor-agent",
            description="Monitors production metrics",
        )
        assert identity_with_desc.description == "Monitors production metrics"

    def test_serialization_roundtrip(self) -> None:
        """AgentIdentity should serialize to dict and back without data loss."""
        original = AgentIdentity(
            agent_id="test-id",
            agent_type=AgentType.DEVOPS,
            name="devops-agent",
            version="1.0.0",
            description="Handles CI/CD",
        )
        data = original.model_dump()
        restored = AgentIdentity(**data)

        assert restored.agent_id == original.agent_id
        assert restored.agent_type == original.agent_type
        assert restored.name == original.name
        assert restored.version == original.version
        assert restored.description == original.description


# =============================================================================
# Test: TaskDefinition
# =============================================================================
class TestTaskDefinition:
    """Tests for the TaskDefinition model."""

    def test_create_minimal_task(self) -> None:
        """TaskDefinition should create with just a name."""
        task = TaskDefinition(name="Generate API code")
        assert task.name == "Generate API code"
        assert task.description == ""
        assert task.assigned_to is None
        assert task.priority == Priority.MEDIUM
        assert task.input_data == {}
        assert task.timeout_seconds == 120

    def test_auto_generates_task_id(self) -> None:
        """task_id should be auto-generated as a UUID."""
        task = TaskDefinition(name="Test task")
        assert len(task.task_id) == 36

    def test_auto_generates_timestamp(self) -> None:
        """created_at should be auto-generated as current UTC time."""
        task = TaskDefinition(name="Test task")
        assert isinstance(task.created_at, datetime)
        # Should be very recent (within last 5 seconds)
        now = datetime.now(timezone.utc)
        delta = (now - task.created_at).total_seconds()
        assert delta < 5

    def test_full_task_definition(self) -> None:
        """TaskDefinition should accept all fields."""
        task = TaskDefinition(
            name="Generate REST API",
            description="Create FastAPI endpoints for user CRUD",
            assigned_to=AgentType.CODING,
            priority=Priority.HIGH,
            input_data={
                "specification": "CRUD for /users",
                "language": "python",
                "framework": "fastapi",
            },
            timeout_seconds=60,
            metadata={"project": "user-service", "version": "1.0"},
        )
        assert task.assigned_to == AgentType.CODING
        assert task.priority == Priority.HIGH
        assert task.input_data["language"] == "python"
        assert task.timeout_seconds == 60
        assert task.metadata["project"] == "user-service"

    def test_timeout_validation_minimum(self) -> None:
        """timeout_seconds must be >= 1."""
        with pytest.raises(Exception):
            TaskDefinition(name="Bad task", timeout_seconds=0)

    def test_timeout_validation_maximum(self) -> None:
        """timeout_seconds must be <= 3600 (1 hour)."""
        with pytest.raises(Exception):
            TaskDefinition(name="Bad task", timeout_seconds=7200)

    def test_json_serialization(self) -> None:
        """TaskDefinition should serialize to JSON cleanly."""
        task = TaskDefinition(
            name="Test task",
            assigned_to=AgentType.TEST,
            priority=Priority.LOW,
        )
        json_str = task.model_dump_json()
        assert "test" in json_str  # AgentType.TEST serializes to "test"
        assert "low" in json_str   # Priority.LOW serializes to "low"


# =============================================================================
# Test: TaskResult
# =============================================================================
class TestTaskResult:
    """Tests for the TaskResult model."""

    def test_create_successful_result(self) -> None:
        """TaskResult should represent a successful task execution."""
        result = TaskResult(
            task_id="task-123",
            agent_id="agent-456",
            status=TaskStatus.COMPLETED,
            output_data={"code": "def hello(): pass", "language": "python"},
            duration_seconds=2.5,
        )
        assert result.task_id == "task-123"
        assert result.agent_id == "agent-456"
        assert result.status == TaskStatus.COMPLETED
        assert result.output_data["code"] == "def hello(): pass"
        assert result.error_message is None
        assert result.duration_seconds == 2.5

    def test_create_failed_result(self) -> None:
        """TaskResult should represent a failed task execution."""
        result = TaskResult(
            task_id="task-789",
            agent_id="agent-101",
            status=TaskStatus.FAILED,
            error_message="LLM API returned 429 Too Many Requests",
            duration_seconds=0.5,
        )
        assert result.status == TaskStatus.FAILED
        assert result.error_message is not None
        assert "429" in result.error_message

    def test_auto_generates_started_at(self) -> None:
        """started_at should be auto-generated."""
        result = TaskResult(
            task_id="t1",
            agent_id="a1",
            status=TaskStatus.COMPLETED,
        )
        assert isinstance(result.started_at, datetime)

    def test_completed_at_is_optional(self) -> None:
        """completed_at should be None by default (task might be in progress)."""
        result = TaskResult(
            task_id="t1",
            agent_id="a1",
            status=TaskStatus.COMPLETED,
        )
        assert result.completed_at is None

    def test_duration_validation(self) -> None:
        """duration_seconds must be >= 0 if provided."""
        with pytest.raises(Exception):
            TaskResult(
                task_id="t1",
                agent_id="a1",
                status=TaskStatus.COMPLETED,
                duration_seconds=-1.0,
            )

    def test_serialization_roundtrip(self) -> None:
        """TaskResult should serialize to dict and back."""
        original = TaskResult(
            task_id="t1",
            agent_id="a1",
            status=TaskStatus.COMPLETED,
            output_data={"result": "success"},
            duration_seconds=1.0,
        )
        data = original.model_dump()
        restored = TaskResult(**data)
        assert restored.task_id == original.task_id
        assert restored.status == original.status
        assert restored.output_data == original.output_data


# =============================================================================
# Test: WorkflowDefinition
# =============================================================================
class TestWorkflowDefinition:
    """Tests for the WorkflowDefinition model."""

    def test_create_minimal_workflow(self) -> None:
        """WorkflowDefinition should create with just a name."""
        workflow = WorkflowDefinition(name="Test Workflow")
        assert workflow.name == "Test Workflow"
        assert len(workflow.workflow_id) == 36  # Auto-generated UUID

    def test_default_phases(self) -> None:
        """Default phases should be the full pipeline: DEV → DEVOPS → MONITORING."""
        workflow = WorkflowDefinition(name="Full Pipeline")
        assert workflow.phases == [
            WorkflowPhase.DEVELOPMENT,
            WorkflowPhase.DEVOPS,
            WorkflowPhase.MONITORING,
        ]

    def test_custom_phases(self) -> None:
        """Workflows should allow custom phase lists (e.g., skip monitoring)."""
        workflow = WorkflowDefinition(
            name="Dev Only",
            phases=[WorkflowPhase.DEVELOPMENT],
        )
        assert workflow.phases == [WorkflowPhase.DEVELOPMENT]

    def test_workflow_with_tasks(self) -> None:
        """WorkflowDefinition should hold multiple TaskDefinitions."""
        tasks = [
            TaskDefinition(name="Code", assigned_to=AgentType.CODING),
            TaskDefinition(name="Review", assigned_to=AgentType.REVIEW),
            TaskDefinition(name="Test", assigned_to=AgentType.TEST),
        ]
        workflow = WorkflowDefinition(
            name="Dev Pipeline",
            tasks=tasks,
            metadata={"project": "my-api"},
        )
        assert len(workflow.tasks) == 3
        assert workflow.tasks[0].name == "Code"
        assert workflow.metadata["project"] == "my-api"

    def test_auto_generates_created_at(self) -> None:
        """created_at should be auto-generated."""
        workflow = WorkflowDefinition(name="Test")
        assert isinstance(workflow.created_at, datetime)

    def test_serialization_roundtrip(self) -> None:
        """WorkflowDefinition should serialize to dict and back."""
        original = WorkflowDefinition(
            name="Test Workflow",
            description="Integration test workflow",
            phases=[WorkflowPhase.DEVELOPMENT, WorkflowPhase.DEVOPS],
        )
        data = original.model_dump()
        restored = WorkflowDefinition(**data)
        assert restored.name == original.name
        assert restored.phases == original.phases
