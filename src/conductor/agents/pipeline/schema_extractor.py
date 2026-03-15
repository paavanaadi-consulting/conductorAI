"""
conductor.agents.pipeline.schema_extractor - Template Schema Extraction
========================================================================

Extracts compact schema skeletons from full pipeline template YAML files.
Used to create manageable LLM prompts from 800-2300 line templates.

The skeleton preserves the hierarchical structure and key names but replaces
concrete values with type hints, keeping the representation under ~200 lines.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


# =============================================================================
# Template file mapping: pipeline_type → template filename
# =============================================================================
TEMPLATE_FILES: dict[str, str] = {
    "data_pipeline": "data-pipeline-requirements-template.yaml",
    "ml_pipeline": "ml-pipeline-requirements-template.yaml",
    "rag_llm": "rag-llm-pipeline-template.yaml",
    "agentic_ops": "agentic-ops-pipeline-template.yaml",
    "integration": "pipeline-integration-template.yaml",
    "general": "project-requirements-template.yaml",
}


# =============================================================================
# Required top-level sections per pipeline type
# =============================================================================
REQUIRED_SECTIONS: dict[str, list[str]] = {
    "data_pipeline": [
        "project",
        "business_requirements",
        "data_sources",
        "transformations",
        "orchestration",
        "storage",
        "monitoring",
        "success_criteria",
    ],
    "ml_pipeline": [
        "project",
        "business_requirements",
        "data_requirements",
        "model_requirements",
        "training_pipeline",
        "monitoring",
        "success_criteria",
    ],
    "rag_llm": [
        "project",
        "rag_objectives",
        "knowledge_sources",
        "retrieval_pipeline",
        "llm_configuration",
        "monitoring",
        "success_criteria",
    ],
    "agentic_ops": [
        "project",
        "agent_objectives",
        "agents",
        "orchestration",
        "safety_guardrails",
        "monitoring",
        "success_criteria",
    ],
    "integration": [
        "project",
        "current_state",
        "target_state",
        "migration_strategy",
        "monitoring",
        "success_criteria",
    ],
    "general": [
        "project",
        "functional_requirements",
        "technical_requirements",
        "testing",
        "success_criteria",
    ],
}


def infer_type_hint(value: Any) -> str:
    """Infer a compact type hint string from a YAML value.

    Args:
        value: Any parsed YAML value.

    Returns:
        A short string like "str", "int", "list[str]", "dict", etc.
    """
    if value is None or value == "":
        return "str"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        if not value:
            return "list"
        first = value[0]
        if isinstance(first, dict):
            return "list[dict]"
        if isinstance(first, str):
            return "list[str]"
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "str"


def extract_schema_skeleton(
    data: dict[str, Any],
    max_depth: int = 3,
    _current_depth: int = 0,
    _indent: int = 0,
) -> str:
    """Recursively traverse parsed YAML and produce a compact schema skeleton.

    The skeleton preserves key names and nesting structure but replaces
    concrete values with type hints. For lists of dicts, only the first
    item's structure is shown.

    Args:
        data: Parsed YAML dictionary.
        max_depth: Maximum nesting depth to traverse.
        _current_depth: Internal recursion tracker.
        _indent: Internal indentation tracker.

    Returns:
        A multi-line string representing the schema skeleton in YAML-like format.
    """
    if not isinstance(data, dict):
        return ""

    lines: list[str] = []
    prefix = "  " * _indent

    for key, value in data.items():
        if isinstance(value, dict) and _current_depth < max_depth:
            lines.append(f"{prefix}{key}:")
            child = extract_schema_skeleton(
                value,
                max_depth=max_depth,
                _current_depth=_current_depth + 1,
                _indent=_indent + 1,
            )
            if child:
                lines.append(child)
            else:
                lines.append(f"{prefix}  # (empty dict)")
        elif isinstance(value, list) and value and isinstance(value[0], dict) and _current_depth < max_depth:
            lines.append(f"{prefix}{key}:  # list[dict]")
            lines.append(f"{prefix}  - # item structure:")
            child = extract_schema_skeleton(
                value[0],
                max_depth=max_depth,
                _current_depth=_current_depth + 1,
                _indent=_indent + 2,
            )
            if child:
                lines.append(child)
        else:
            type_hint = infer_type_hint(value)
            lines.append(f"{prefix}{key}: {type_hint}")

    return "\n".join(lines)


def load_template_schema(pipeline_type: str, templates_dir: Path) -> str:
    """Load a pipeline template and extract its schema skeleton.

    Args:
        pipeline_type: One of the keys in TEMPLATE_FILES.
        templates_dir: Path to the templates/ directory.

    Returns:
        The schema skeleton string.

    Raises:
        FileNotFoundError: If the template file doesn't exist.
        KeyError: If pipeline_type is not recognized.
    """
    if pipeline_type not in TEMPLATE_FILES:
        raise KeyError(
            f"Unknown pipeline type '{pipeline_type}'. "
            f"Valid types: {list(TEMPLATE_FILES.keys())}"
        )

    template_path = templates_dir / TEMPLATE_FILES[pipeline_type]
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    with open(template_path, "r") as f:
        try:
            template_data = yaml.safe_load(f)
        except yaml.YAMLError:
            # Some template files contain illustrative YAML that doesn't
            # strictly parse (e.g., complex flow examples). Return empty
            # skeleton — the LLM can still generate without it.
            return ""

    if not isinstance(template_data, dict):
        return ""

    return extract_schema_skeleton(template_data, max_depth=2)
