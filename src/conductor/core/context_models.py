"""
conductor.core.context_models - Context Directory Models
==========================================================

Pydantic models for the .context/ directory generation system.
Each agent produces ContextEntry objects that map to sections in
.context/ files. The ContextBundler assembles these into the final
directory structure.

Context File Mapping (from pipeline-yaml-to-zip.md):
    decisions.md            <- CodingAgent + DevOpsAgent
    traceability.md         <- CodingAgent
    infra-bindings.md       <- DevOpsAgent
    confidence-report.md    <- CodingAgent + ReviewAgent
    runbook.md              <- DevOpsAgent
    known-gaps.md           <- CodingAgent + TestAgent
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ContextEntry(BaseModel):
    """A single contribution to a .context/ file from an agent.

    Each ContextEntry targets a specific file in the .context/ directory
    and provides a markdown section for that file. Multiple agents can
    contribute to the same file — the ContextBundler merges them.

    Attributes:
        context_file: Target filename in .context/ (e.g., "decisions.md").
        section_heading: Markdown heading for this section.
        content: Markdown content for this section.
        agent_id: Which agent produced this entry.
        confidence: Agent's confidence in this section (0.0-1.0).
    """

    context_file: str = Field(
        description="Target filename in .context/ (e.g., 'decisions.md')",
    )
    section_heading: str = Field(
        description="Markdown section heading (e.g., '## Code Architecture Decisions')",
    )
    content: str = Field(
        description="Markdown content for this section",
    )
    agent_id: str = Field(
        description="ID of the agent that produced this entry",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Agent's confidence in this section (0.0-1.0)",
    )


class ContextContribution(BaseModel):
    """All context entries produced by a single agent execution.

    Returned by BaseAgent._generate_context(). Contains zero or more
    ContextEntry objects, each targeting a different .context/ file.

    Attributes:
        entries: List of context entries this agent produced.
    """

    entries: list[ContextEntry] = Field(
        default_factory=list,
        description="Context entries produced by this agent execution",
    )
