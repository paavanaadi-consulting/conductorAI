"""
Tests for conductor.infrastructure.context_bundler
=====================================================

Validates the ContextBundler:
    - Assembles context entries into .context/ files
    - Groups entries from multiple agents
    - Handles empty workflow (no context artifacts)
    - Handles malformed artifacts gracefully
    - Includes confidence annotations and agent attribution
"""

import pytest

from conductor.core.context_models import ContextEntry
from conductor.infrastructure.artifact_store import Artifact, InMemoryArtifactStore
from conductor.infrastructure.context_bundler import CONTEXT_FILES, ContextBundler


# =============================================================================
# Helpers
# =============================================================================
def _context_artifact(
    workflow_id: str,
    entry: ContextEntry,
    task_id: str = "task-01",
) -> Artifact:
    """Create a context artifact from a ContextEntry."""
    return Artifact(
        workflow_id=workflow_id,
        task_id=task_id,
        agent_id=entry.agent_id,
        artifact_type="context",
        content=entry.model_dump_json(),
        metadata={
            "context_file": entry.context_file,
            "section_heading": entry.section_heading,
        },
    )


# =============================================================================
# Tests
# =============================================================================
class TestContextBundler:
    """Tests for ContextBundler.bundle()."""

    async def test_empty_workflow_returns_empty(self) -> None:
        """No context artifacts → empty dict."""
        store = InMemoryArtifactStore()
        bundler = ContextBundler(store)
        result = await bundler.bundle("wf-empty")
        assert result == {}

    async def test_single_entry_produces_file(self) -> None:
        """One context entry → one .context/ file."""
        store = InMemoryArtifactStore()
        entry = ContextEntry(
            context_file="decisions.md",
            section_heading="## Architecture",
            content="Chose Flask for simplicity.",
            agent_id="coding-01",
        )
        await store.save(_context_artifact("wf-001", entry))

        bundler = ContextBundler(store)
        result = await bundler.bundle("wf-001")

        assert "decisions.md" in result
        assert "Architecture" in result["decisions.md"]
        assert "Flask" in result["decisions.md"]
        assert "coding-01" in result["decisions.md"]

    async def test_multiple_entries_same_file(self) -> None:
        """Multiple entries targeting the same file are merged."""
        store = InMemoryArtifactStore()

        entry1 = ContextEntry(
            context_file="decisions.md",
            section_heading="## Code Decisions",
            content="Used Flask.",
            agent_id="coding-01",
        )
        entry2 = ContextEntry(
            context_file="decisions.md",
            section_heading="## Infra Decisions",
            content="Used GitHub Actions.",
            agent_id="devops-01",
        )
        await store.save(_context_artifact("wf-001", entry1))
        await store.save(_context_artifact("wf-001", entry2))

        bundler = ContextBundler(store)
        result = await bundler.bundle("wf-001")

        content = result["decisions.md"]
        assert "Code Decisions" in content
        assert "Infra Decisions" in content
        assert "coding-01" in content
        assert "devops-01" in content

    async def test_multiple_files(self) -> None:
        """Entries targeting different files produce separate outputs."""
        store = InMemoryArtifactStore()

        entries = [
            ContextEntry(
                context_file="decisions.md",
                section_heading="## Arch",
                content="Decisions here.",
                agent_id="coding-01",
            ),
            ContextEntry(
                context_file="runbook.md",
                section_heading="## Setup",
                content="Run this.",
                agent_id="devops-01",
            ),
            ContextEntry(
                context_file="known-gaps.md",
                section_heading="## Gaps",
                content="Missing edge cases.",
                agent_id="test-01",
            ),
        ]
        for entry in entries:
            await store.save(_context_artifact("wf-001", entry))

        bundler = ContextBundler(store)
        result = await bundler.bundle("wf-001")

        assert len(result) == 3
        assert "decisions.md" in result
        assert "runbook.md" in result
        assert "known-gaps.md" in result

    async def test_confidence_annotation(self) -> None:
        """Entries with confidence should include the annotation."""
        store = InMemoryArtifactStore()
        entry = ContextEntry(
            context_file="confidence-report.md",
            section_heading="## AI Confidence",
            content="High confidence in approach.",
            agent_id="coding-01",
            confidence=0.85,
        )
        await store.save(_context_artifact("wf-001", entry))

        bundler = ContextBundler(store)
        result = await bundler.bundle("wf-001")

        assert "85%" in result["confidence-report.md"]

    async def test_filters_by_workflow_id(self) -> None:
        """Only artifacts from the requested workflow are included."""
        store = InMemoryArtifactStore()

        entry_wf1 = ContextEntry(
            context_file="decisions.md",
            section_heading="## WF1",
            content="Workflow 1 content.",
            agent_id="coding-01",
        )
        entry_wf2 = ContextEntry(
            context_file="decisions.md",
            section_heading="## WF2",
            content="Workflow 2 content.",
            agent_id="coding-01",
        )
        await store.save(_context_artifact("wf-001", entry_wf1))
        await store.save(_context_artifact("wf-002", entry_wf2))

        bundler = ContextBundler(store)
        result = await bundler.bundle("wf-001")

        assert "Workflow 1" in result["decisions.md"]
        assert "Workflow 2" not in result["decisions.md"]

    async def test_malformed_artifact_skipped(self) -> None:
        """Malformed artifacts are skipped without error."""
        store = InMemoryArtifactStore()

        # Save a valid entry
        entry = ContextEntry(
            context_file="decisions.md",
            section_heading="## Good",
            content="Valid.",
            agent_id="coding-01",
        )
        await store.save(_context_artifact("wf-001", entry))

        # Save a malformed artifact
        bad_artifact = Artifact(
            workflow_id="wf-001",
            task_id="task-bad",
            agent_id="bad-agent",
            artifact_type="context",
            content="not valid json{{{",
            metadata={},
        )
        await store.save(bad_artifact)

        bundler = ContextBundler(store)
        result = await bundler.bundle("wf-001")

        # Valid entry should still be included
        assert "decisions.md" in result
        assert "Valid" in result["decisions.md"]

    async def test_file_headers_match_context_files(self) -> None:
        """Each generated file should start with the canonical header."""
        store = InMemoryArtifactStore()
        entry = ContextEntry(
            context_file="runbook.md",
            section_heading="## Getting Started",
            content="Step 1: Install.",
            agent_id="devops-01",
        )
        await store.save(_context_artifact("wf-001", entry))

        bundler = ContextBundler(store)
        result = await bundler.bundle("wf-001")

        assert result["runbook.md"].startswith(CONTEXT_FILES["runbook.md"])
