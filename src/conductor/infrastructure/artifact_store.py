"""
conductor.infrastructure.artifact_store - Artifact Persistence Layer
=====================================================================

This module provides the artifact storage abstraction for ConductorAI.
Artifacts are the work products that flow between agents and across
workflow phases — generated code, test suites, CI/CD configs, deployment
manifests, monitoring reports, etc.

Architecture Context:
    The ArtifactStore sits in the Infrastructure Layer and provides
    persistence for all artifacts produced during workflow execution.

    ┌───────────────┐                    ┌─────────────────┐
    │  CodingAgent  │ ── stores code ──→ │  ArtifactStore   │
    │  ReviewAgent  │ ── stores review → │                  │
    │  TestAgent    │ ── stores tests ──→│  ┌────────────┐ │
    │  DevOpsAgent  │ ── stores CI/CD ──→│  │ Artifacts  │ │
    │  MonitorAgent │ ── stores report → │  └────────────┘ │
    └───────────────┘                    └─────────────────┘

Artifact Model:
    Each Artifact stores:
    - artifact_id: Unique identifier
    - workflow_id: Which workflow produced it
    - task_id: Which task produced it
    - agent_id: Which agent produced it
    - artifact_type: What kind of artifact (code, test, config, etc.)
    - content: The actual artifact content (string)
    - metadata: Additional metadata (language, framework, etc.)
    - created_at: Timestamp

Storage Implementations:
    - InMemoryArtifactStore: Dict-based, for development/testing
    - (Future) RedisArtifactStore: Redis-backed, for production
    - (Future) S3ArtifactStore: S3-backed, for large artifacts

Usage:
    >>> store = InMemoryArtifactStore()
    >>> artifact = Artifact(
    ...     workflow_id="wf-001",
    ...     task_id="task-abc",
    ...     agent_id="coding-01",
    ...     artifact_type="code",
    ...     content="def hello(): return 'Hello!'",
    ...     metadata={"language": "python"},
    ... )
    >>> await store.save(artifact)
    >>> retrieved = await store.get(artifact.artifact_id)
    >>> by_workflow = await store.list_by_workflow("wf-001")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import structlog
from pydantic import BaseModel, Field


# =============================================================================
# Logger
# =============================================================================
logger = structlog.get_logger()


# =============================================================================
# Helper: Generate Unique IDs
# =============================================================================
def _generate_artifact_id() -> str:
    """Generate a unique artifact identifier using UUID4.

    Returns:
        A string UUID like "art-a1b2c3d4-e5f6-7890-abcd-ef1234567890".
    """
    return f"art-{uuid4()}"


# =============================================================================
# Artifact Model
# =============================================================================
class Artifact(BaseModel):
    """A work product produced by an agent during workflow execution.

    Artifacts are the tangible outputs of agent work — code files, test
    suites, CI/CD configurations, deployment manifests, monitoring reports,
    etc. They are stored in the ArtifactStore and can be retrieved for
    downstream processing, auditing, or debugging.

    Attributes:
        artifact_id: Unique identifier for this artifact.
        workflow_id: ID of the workflow that produced this artifact.
        task_id: ID of the task that produced this artifact.
        agent_id: ID of the agent that produced this artifact.
        artifact_type: Category of artifact (code, test, config, etc.).
        content: The actual artifact content as a string.
        metadata: Additional key-value metadata (language, framework, etc.).
        created_at: When this artifact was created.

    Example:
        >>> artifact = Artifact(
        ...     workflow_id="wf-001",
        ...     task_id="task-abc",
        ...     agent_id="coding-01",
        ...     artifact_type="code",
        ...     content="def hello(): return 'Hello!'",
        ...     metadata={"language": "python", "framework": "flask"},
        ... )
    """

    artifact_id: str = Field(
        default_factory=_generate_artifact_id,
        description="Unique identifier for this artifact",
    )
    workflow_id: str = Field(
        description="ID of the workflow that produced this artifact",
    )
    task_id: str = Field(
        description="ID of the task that produced this artifact",
    )
    agent_id: str = Field(
        description="ID of the agent that produced this artifact",
    )
    artifact_type: str = Field(
        description=(
            "Category of artifact. Common types: "
            "'code', 'test', 'test_data', 'review', 'config', "
            "'deployment', 'monitoring_report'"
        ),
    )
    content: str = Field(
        description="The actual artifact content as a string",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (language, framework, version, etc.)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this artifact was created (UTC)",
    )


# =============================================================================
# Abstract Base Class
# =============================================================================
class ArtifactStore(ABC):
    """Abstract interface for artifact persistence.

    All artifact stores implement this interface, ensuring a consistent
    API regardless of the backing store (in-memory, Redis, S3, etc.).

    Methods:
        save(artifact): Persist an artifact.
        get(artifact_id): Retrieve a single artifact by ID.
        list_by_workflow(workflow_id): Get all artifacts for a workflow.
        list_by_task(task_id): Get all artifacts for a task.
        list_by_agent(agent_id): Get all artifacts produced by an agent.
        list_by_type(artifact_type): Get all artifacts of a certain type.
        delete(artifact_id): Remove an artifact from storage.
        count(): Get the total number of stored artifacts.

    Usage:
        >>> store: ArtifactStore = InMemoryArtifactStore()
        >>> await store.save(artifact)
        >>> result = await store.get(artifact.artifact_id)
    """

    @abstractmethod
    async def save(self, artifact: Artifact) -> None:
        """Persist an artifact to the store.

        Args:
            artifact: The Artifact to save. If an artifact with the same
                ID already exists, it will be overwritten.
        """
        ...

    @abstractmethod
    async def get(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve a single artifact by its ID.

        Args:
            artifact_id: The unique identifier of the artifact.

        Returns:
            The Artifact if found, None otherwise.
        """
        ...

    @abstractmethod
    async def list_by_workflow(self, workflow_id: str) -> list[Artifact]:
        """Get all artifacts produced during a specific workflow.

        Args:
            workflow_id: The workflow's unique identifier.

        Returns:
            List of artifacts for that workflow, sorted by creation time.
        """
        ...

    @abstractmethod
    async def list_by_task(self, task_id: str) -> list[Artifact]:
        """Get all artifacts produced by a specific task.

        Args:
            task_id: The task's unique identifier.

        Returns:
            List of artifacts for that task.
        """
        ...

    @abstractmethod
    async def list_by_agent(self, agent_id: str) -> list[Artifact]:
        """Get all artifacts produced by a specific agent.

        Args:
            agent_id: The agent's unique identifier.

        Returns:
            List of artifacts produced by that agent.
        """
        ...

    @abstractmethod
    async def list_by_type(self, artifact_type: str) -> list[Artifact]:
        """Get all artifacts of a specific type.

        Args:
            artifact_type: The artifact type to filter by
                (e.g., "code", "test", "config").

        Returns:
            List of artifacts of that type.
        """
        ...

    @abstractmethod
    async def delete(self, artifact_id: str) -> bool:
        """Remove an artifact from storage.

        Args:
            artifact_id: The unique identifier of the artifact to delete.

        Returns:
            True if the artifact was deleted, False if it didn't exist.
        """
        ...

    @abstractmethod
    async def count(self) -> int:
        """Get the total number of stored artifacts.

        Returns:
            The count of artifacts in the store.
        """
        ...


# =============================================================================
# In-Memory Implementation
# =============================================================================
class InMemoryArtifactStore(ArtifactStore):
    """In-memory artifact store for development and testing.

    Uses a Python dictionary as the backing store. This is fast and
    requires no external dependencies, making it perfect for:
    - Unit testing
    - Local development
    - Examples and tutorials

    Not suitable for production because:
    - Data is lost when the process exits
    - No persistence across restarts
    - Not shared between processes

    For production, use RedisArtifactStore or S3ArtifactStore (future).

    Attributes:
        _store: Internal dictionary mapping artifact_id to Artifact.

    Example:
        >>> store = InMemoryArtifactStore()
        >>> await store.save(artifact)
        >>> all_code = await store.list_by_type("code")
    """

    def __init__(self) -> None:
        """Initialize the in-memory artifact store.

        Creates an empty dictionary to hold artifacts.
        """
        self._store: dict[str, Artifact] = {}
        self._logger = logger.bind(component="in_memory_artifact_store")

    async def save(self, artifact: Artifact) -> None:
        """Save an artifact to the in-memory store.

        Args:
            artifact: The Artifact to save.
        """
        self._store[artifact.artifact_id] = artifact
        self._logger.debug(
            "artifact_saved",
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            workflow_id=artifact.workflow_id,
        )

    async def get(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve an artifact by ID.

        Args:
            artifact_id: The artifact's unique identifier.

        Returns:
            The Artifact if found, None otherwise.
        """
        return self._store.get(artifact_id)

    async def list_by_workflow(self, workflow_id: str) -> list[Artifact]:
        """Get all artifacts for a workflow, sorted by creation time.

        Args:
            workflow_id: The workflow's unique identifier.

        Returns:
            List of artifacts sorted by created_at (oldest first).
        """
        artifacts = [
            a for a in self._store.values()
            if a.workflow_id == workflow_id
        ]
        return sorted(artifacts, key=lambda a: a.created_at)

    async def list_by_task(self, task_id: str) -> list[Artifact]:
        """Get all artifacts for a task.

        Args:
            task_id: The task's unique identifier.

        Returns:
            List of artifacts for that task.
        """
        return [
            a for a in self._store.values()
            if a.task_id == task_id
        ]

    async def list_by_agent(self, agent_id: str) -> list[Artifact]:
        """Get all artifacts produced by an agent.

        Args:
            agent_id: The agent's unique identifier.

        Returns:
            List of artifacts produced by that agent.
        """
        return [
            a for a in self._store.values()
            if a.agent_id == agent_id
        ]

    async def list_by_type(self, artifact_type: str) -> list[Artifact]:
        """Get all artifacts of a specific type.

        Args:
            artifact_type: The artifact type to filter by.

        Returns:
            List of artifacts of that type.
        """
        return [
            a for a in self._store.values()
            if a.artifact_type == artifact_type
        ]

    async def delete(self, artifact_id: str) -> bool:
        """Remove an artifact from the store.

        Args:
            artifact_id: The artifact's unique identifier.

        Returns:
            True if deleted, False if not found.
        """
        if artifact_id in self._store:
            del self._store[artifact_id]
            self._logger.debug(
                "artifact_deleted",
                artifact_id=artifact_id,
            )
            return True
        return False

    async def count(self) -> int:
        """Get the total number of stored artifacts.

        Returns:
            The count of artifacts in the store.
        """
        return len(self._store)
