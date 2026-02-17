"""
Tests for conductor.infrastructure.artifact_store
====================================================

These tests verify the Artifact model and ArtifactStore implementations.

What's Being Tested:
    - Artifact model (creation, defaults, validation)
    - InMemoryArtifactStore (save, get, list, delete, count)
    - Querying by workflow, task, agent, and type
    - Edge cases (not found, duplicate save, empty store)

All tests use InMemoryArtifactStore — no external dependencies.
"""

import pytest
from datetime import datetime, timezone

from conductor.infrastructure.artifact_store import (
    Artifact,
    ArtifactStore,
    InMemoryArtifactStore,
)


# =============================================================================
# Helpers
# =============================================================================
def _artifact(**overrides) -> Artifact:
    """Create a standard artifact with optional overrides."""
    defaults = {
        "workflow_id": "wf-001",
        "task_id": "task-abc",
        "agent_id": "coding-01",
        "artifact_type": "code",
        "content": "def hello():\n    return 'Hello!'",
        "metadata": {"language": "python"},
    }
    defaults.update(overrides)
    return Artifact(**defaults)


# =============================================================================
# Tests: Artifact Model
# =============================================================================
class TestArtifactModel:
    """Tests for the Artifact Pydantic model."""

    def test_creates_with_defaults(self) -> None:
        """Artifact should auto-generate ID and timestamp."""
        a = _artifact()
        assert a.artifact_id.startswith("art-")
        assert a.created_at is not None
        assert a.workflow_id == "wf-001"

    def test_unique_ids(self) -> None:
        """Each artifact should get a unique ID."""
        a1 = _artifact()
        a2 = _artifact()
        assert a1.artifact_id != a2.artifact_id

    def test_all_fields_set(self) -> None:
        """All fields should be accessible."""
        a = _artifact()
        assert a.workflow_id == "wf-001"
        assert a.task_id == "task-abc"
        assert a.agent_id == "coding-01"
        assert a.artifact_type == "code"
        assert "Hello" in a.content
        assert a.metadata["language"] == "python"

    def test_custom_artifact_id(self) -> None:
        """Custom artifact_id should be respected."""
        a = _artifact(artifact_id="custom-id-123")
        assert a.artifact_id == "custom-id-123"

    def test_default_metadata_is_empty_dict(self) -> None:
        """Metadata should default to empty dict."""
        a = Artifact(
            workflow_id="wf-001",
            task_id="task-abc",
            agent_id="coding-01",
            artifact_type="code",
            content="code here",
        )
        assert a.metadata == {}

    def test_serialization(self) -> None:
        """Artifact should be serializable to dict."""
        a = _artifact()
        data = a.model_dump()
        assert isinstance(data, dict)
        assert "artifact_id" in data
        assert "content" in data


# =============================================================================
# Tests: InMemoryArtifactStore — Save and Get
# =============================================================================
class TestInMemoryStoreSaveGet:
    """Tests for save and get operations."""

    async def test_save_and_get(self) -> None:
        """Saved artifact should be retrievable by ID."""
        store = InMemoryArtifactStore()
        a = _artifact()

        await store.save(a)
        retrieved = await store.get(a.artifact_id)

        assert retrieved is not None
        assert retrieved.artifact_id == a.artifact_id
        assert retrieved.content == a.content

    async def test_get_nonexistent_returns_none(self) -> None:
        """Getting a non-existent artifact should return None."""
        store = InMemoryArtifactStore()
        result = await store.get("nonexistent-id")
        assert result is None

    async def test_save_overwrites_existing(self) -> None:
        """Saving with same ID should overwrite."""
        store = InMemoryArtifactStore()
        a = _artifact(artifact_id="fixed-id")

        await store.save(a)

        updated = _artifact(artifact_id="fixed-id", content="updated code")
        await store.save(updated)

        retrieved = await store.get("fixed-id")
        assert retrieved.content == "updated code"

    async def test_multiple_saves(self) -> None:
        """Multiple artifacts should be saved independently."""
        store = InMemoryArtifactStore()
        a1 = _artifact(task_id="task-1")
        a2 = _artifact(task_id="task-2")

        await store.save(a1)
        await store.save(a2)

        assert await store.count() == 2


# =============================================================================
# Tests: InMemoryArtifactStore — List Queries
# =============================================================================
class TestInMemoryStoreListQueries:
    """Tests for list_by_* query operations."""

    async def test_list_by_workflow(self) -> None:
        """Should return all artifacts for a specific workflow."""
        store = InMemoryArtifactStore()
        a1 = _artifact(workflow_id="wf-001", task_id="task-1")
        a2 = _artifact(workflow_id="wf-001", task_id="task-2")
        a3 = _artifact(workflow_id="wf-002", task_id="task-3")

        for a in [a1, a2, a3]:
            await store.save(a)

        results = await store.list_by_workflow("wf-001")
        assert len(results) == 2
        assert all(a.workflow_id == "wf-001" for a in results)

    async def test_list_by_workflow_sorted_by_creation(self) -> None:
        """Workflow artifacts should be sorted by creation time."""
        store = InMemoryArtifactStore()
        a1 = _artifact(workflow_id="wf-001", task_id="task-1")
        a2 = _artifact(workflow_id="wf-001", task_id="task-2")

        await store.save(a1)
        await store.save(a2)

        results = await store.list_by_workflow("wf-001")
        assert results[0].created_at <= results[1].created_at

    async def test_list_by_workflow_empty(self) -> None:
        """Should return empty list for unknown workflow."""
        store = InMemoryArtifactStore()
        results = await store.list_by_workflow("nonexistent-wf")
        assert results == []

    async def test_list_by_task(self) -> None:
        """Should return all artifacts for a specific task."""
        store = InMemoryArtifactStore()
        a1 = _artifact(task_id="task-abc", artifact_type="code")
        a2 = _artifact(task_id="task-abc", artifact_type="review")
        a3 = _artifact(task_id="task-def", artifact_type="code")

        for a in [a1, a2, a3]:
            await store.save(a)

        results = await store.list_by_task("task-abc")
        assert len(results) == 2

    async def test_list_by_agent(self) -> None:
        """Should return all artifacts produced by a specific agent."""
        store = InMemoryArtifactStore()
        a1 = _artifact(agent_id="coding-01", task_id="task-1")
        a2 = _artifact(agent_id="coding-01", task_id="task-2")
        a3 = _artifact(agent_id="review-01", task_id="task-3")

        for a in [a1, a2, a3]:
            await store.save(a)

        results = await store.list_by_agent("coding-01")
        assert len(results) == 2
        assert all(a.agent_id == "coding-01" for a in results)

    async def test_list_by_type(self) -> None:
        """Should return all artifacts of a specific type."""
        store = InMemoryArtifactStore()
        a1 = _artifact(artifact_type="code", task_id="task-1")
        a2 = _artifact(artifact_type="test", task_id="task-2")
        a3 = _artifact(artifact_type="code", task_id="task-3")

        for a in [a1, a2, a3]:
            await store.save(a)

        results = await store.list_by_type("code")
        assert len(results) == 2
        assert all(a.artifact_type == "code" for a in results)

    async def test_list_by_type_empty(self) -> None:
        """Should return empty list for unknown type."""
        store = InMemoryArtifactStore()
        results = await store.list_by_type("nonexistent-type")
        assert results == []


# =============================================================================
# Tests: InMemoryArtifactStore — Delete
# =============================================================================
class TestInMemoryStoreDelete:
    """Tests for delete operations."""

    async def test_delete_existing(self) -> None:
        """Deleting an existing artifact should return True."""
        store = InMemoryArtifactStore()
        a = _artifact()
        await store.save(a)

        deleted = await store.delete(a.artifact_id)
        assert deleted is True
        assert await store.get(a.artifact_id) is None

    async def test_delete_nonexistent(self) -> None:
        """Deleting a non-existent artifact should return False."""
        store = InMemoryArtifactStore()
        deleted = await store.delete("nonexistent-id")
        assert deleted is False

    async def test_delete_reduces_count(self) -> None:
        """Deleting should reduce the artifact count."""
        store = InMemoryArtifactStore()
        a = _artifact()
        await store.save(a)
        assert await store.count() == 1

        await store.delete(a.artifact_id)
        assert await store.count() == 0


# =============================================================================
# Tests: InMemoryArtifactStore — Count
# =============================================================================
class TestInMemoryStoreCount:
    """Tests for count operations."""

    async def test_empty_store_count(self) -> None:
        """Empty store should have count 0."""
        store = InMemoryArtifactStore()
        assert await store.count() == 0

    async def test_count_after_saves(self) -> None:
        """Count should reflect number of saved artifacts."""
        store = InMemoryArtifactStore()
        for i in range(5):
            await store.save(_artifact(task_id=f"task-{i}"))
        assert await store.count() == 5

    async def test_count_after_delete(self) -> None:
        """Count should decrease after deletion."""
        store = InMemoryArtifactStore()
        a1 = _artifact(task_id="task-1")
        a2 = _artifact(task_id="task-2")
        await store.save(a1)
        await store.save(a2)
        assert await store.count() == 2

        await store.delete(a1.artifact_id)
        assert await store.count() == 1
