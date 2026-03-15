"""
Tests for conductor.core.context_models
==========================================

Validates ContextEntry and ContextContribution Pydantic models:
    - Field defaults and required fields
    - Confidence score validation (0.0-1.0)
    - Serialization round-trips
"""

import pytest
from pydantic import ValidationError

from conductor.core.context_models import ContextContribution, ContextEntry


# =============================================================================
# ContextEntry
# =============================================================================
class TestContextEntry:
    """Tests for the ContextEntry model."""

    def test_creates_with_required_fields(self) -> None:
        entry = ContextEntry(
            context_file="decisions.md",
            section_heading="## Architecture",
            content="We chose Flask.",
            agent_id="coding-01",
        )
        assert entry.context_file == "decisions.md"
        assert entry.agent_id == "coding-01"
        assert entry.confidence is None

    def test_confidence_optional(self) -> None:
        entry = ContextEntry(
            context_file="decisions.md",
            section_heading="## Heading",
            content="content",
            agent_id="agent-01",
        )
        assert entry.confidence is None

    def test_confidence_valid_range(self) -> None:
        entry = ContextEntry(
            context_file="confidence-report.md",
            section_heading="## Confidence",
            content="High",
            agent_id="coding-01",
            confidence=0.85,
        )
        assert entry.confidence == 0.85

    def test_confidence_zero(self) -> None:
        entry = ContextEntry(
            context_file="x.md",
            section_heading="## H",
            content="c",
            agent_id="a",
            confidence=0.0,
        )
        assert entry.confidence == 0.0

    def test_confidence_one(self) -> None:
        entry = ContextEntry(
            context_file="x.md",
            section_heading="## H",
            content="c",
            agent_id="a",
            confidence=1.0,
        )
        assert entry.confidence == 1.0

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContextEntry(
                context_file="x.md",
                section_heading="## H",
                content="c",
                agent_id="a",
                confidence=-0.1,
            )

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContextEntry(
                context_file="x.md",
                section_heading="## H",
                content="c",
                agent_id="a",
                confidence=1.1,
            )

    def test_serialization_round_trip(self) -> None:
        entry = ContextEntry(
            context_file="decisions.md",
            section_heading="## Architecture",
            content="Chose Flask for simplicity.",
            agent_id="coding-01",
            confidence=0.9,
        )
        json_str = entry.model_dump_json()
        restored = ContextEntry.model_validate_json(json_str)
        assert restored == entry

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            ContextEntry(
                context_file="decisions.md",
                # missing section_heading, content, agent_id
            )


# =============================================================================
# ContextContribution
# =============================================================================
class TestContextContribution:
    """Tests for the ContextContribution model."""

    def test_default_empty_entries(self) -> None:
        contrib = ContextContribution()
        assert contrib.entries == []

    def test_with_entries(self) -> None:
        entries = [
            ContextEntry(
                context_file="decisions.md",
                section_heading="## Arch",
                content="content",
                agent_id="coding-01",
            ),
            ContextEntry(
                context_file="known-gaps.md",
                section_heading="## Gaps",
                content="gap content",
                agent_id="coding-01",
            ),
        ]
        contrib = ContextContribution(entries=entries)
        assert len(contrib.entries) == 2
        assert contrib.entries[0].context_file == "decisions.md"

    def test_serialization_round_trip(self) -> None:
        entry = ContextEntry(
            context_file="runbook.md",
            section_heading="## Setup",
            content="Run docker-compose up",
            agent_id="devops-01",
        )
        contrib = ContextContribution(entries=[entry])
        json_str = contrib.model_dump_json()
        restored = ContextContribution.model_validate_json(json_str)
        assert len(restored.entries) == 1
        assert restored.entries[0].context_file == "runbook.md"
