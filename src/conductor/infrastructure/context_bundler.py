"""
conductor.infrastructure.context_bundler - Context Directory Assembly
=======================================================================

Assembles .context/ directory content from context artifacts produced
by agents during workflow execution. Each agent stores ContextEntry
objects as artifacts with artifact_type="context". The ContextBundler
reads these, groups by target file, and produces final markdown content.

Architecture Context:
    The ContextBundler runs as a post-workflow step, after all agents
    have completed and stored their context entries as artifacts.

    ┌─────────────┐                    ┌─────────────────┐
    │ CodingAgent │ ── context ──→     │  ArtifactStore   │
    │ DevOpsAgent │ ── context ──→     │  (type=context)  │
    │ TestAgent   │ ── context ──→     └────────┬────────┘
    └─────────────┘                             │
                                                ↓
                                    ┌─────────────────────┐
                                    │   ContextBundler     │
                                    │  bundle(workflow_id) │
                                    └──────────┬──────────┘
                                               │
                                               ↓
                                    dict[str, str]
                                    {
                                      "decisions.md": "# ...",
                                      "runbook.md": "# ...",
                                      ...
                                    }

Usage:
    >>> bundler = ContextBundler(artifact_store)
    >>> context_files = await bundler.bundle("wf-001")
    >>> context_files["decisions.md"]  # Full markdown content
"""

from __future__ import annotations

from typing import Any

import structlog

from src.conductor.core.context_models import ContextEntry
from src.conductor.infrastructure.artifact_store import ArtifactStore


# =============================================================================
# Logger
# =============================================================================
logger = structlog.get_logger()


# =============================================================================
# Canonical .context/ file definitions
# =============================================================================
# Maps filename to its top-level markdown header. Only files with
# contributions from agents will appear in the final output.
# =============================================================================
CONTEXT_FILES: dict[str, str] = {
    "decisions.md": "# Architectural Decision Record\n\n",
    "traceability.md": "# Requirements to Code Traceability\n\n",
    "infra-bindings.md": "# Infrastructure Bindings\n\n",
    "confidence-report.md": "# AI Confidence Report\n\n",
    "runbook.md": "# Getting Started Runbook\n\n",
    "known-gaps.md": "# Known Gaps and TODOs\n\n",
}


class ContextBundler:
    """Assembles context artifacts into .context/ directory content.

    Collects all context-type artifacts for a workflow from the
    ArtifactStore, groups them by target file, and produces the
    final markdown content for each .context/ file.

    Attributes:
        _artifact_store: The artifact store to read context entries from.

    Example:
        >>> bundler = ContextBundler(artifact_store)
        >>> files = await bundler.bundle("wf-001")
        >>> print(files["decisions.md"])
    """

    def __init__(self, artifact_store: ArtifactStore) -> None:
        self._artifact_store = artifact_store
        self._logger = logger.bind(component="context_bundler")

    async def bundle(self, workflow_id: str) -> dict[str, str]:
        """Assemble all context artifacts for a workflow.

        Reads context artifacts from the store, parses ContextEntry
        objects, groups them by target file, and assembles final
        markdown content with headers and agent attribution.

        Args:
            workflow_id: The workflow to collect context for.

        Returns:
            Dict mapping filename (e.g., "decisions.md") to assembled
            markdown content. Only files with contributions are included.
        """
        # Collect all context artifacts for this workflow
        all_context = await self._artifact_store.list_by_type("context")
        workflow_context = [
            a for a in all_context
            if a.workflow_id == workflow_id
        ]

        if not workflow_context:
            self._logger.info("no_context_artifacts", workflow_id=workflow_id)
            return {}

        # Parse entries and group by target file
        file_sections: dict[str, list[ContextEntry]] = {}
        for artifact in workflow_context:
            try:
                entry = ContextEntry.model_validate_json(artifact.content)
                file_sections.setdefault(entry.context_file, []).append(entry)
            except Exception as e:
                self._logger.warning(
                    "context_entry_parse_failed",
                    artifact_id=artifact.artifact_id,
                    error=str(e),
                )

        # Assemble final content for each file
        result: dict[str, str] = {}
        for filename, header in CONTEXT_FILES.items():
            sections = file_sections.get(filename)
            if not sections:
                continue

            parts = [header]
            for section in sections:
                parts.append(f"{section.section_heading}\n\n")
                parts.append(f"*Generated by: {section.agent_id}*\n\n")
                parts.append(section.content)
                if section.confidence is not None:
                    parts.append(
                        f"\n\n> Confidence: {section.confidence:.0%}\n"
                    )
                parts.append("\n\n---\n\n")
            result[filename] = "".join(parts)

        self._logger.info(
            "context_bundled",
            workflow_id=workflow_id,
            files_generated=list(result.keys()),
            total_entries=sum(len(s) for s in file_sections.values()),
        )

        return result
