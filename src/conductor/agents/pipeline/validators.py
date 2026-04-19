"""
conductor.agents.pipeline.validators - Pipeline YAML Validation
=================================================================

Three-layer validation for generated pipeline YAML output:
1. YAML parsability (yaml.safe_load)
2. Required top-level sections present
3. Basic field type checks on critical fields

Also provides a utility to strip markdown code fences that LLMs
commonly wrap around YAML output.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from conductor.agents.pipeline.schema_extractor import REQUIRED_SECTIONS


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output.

    Handles patterns like:
        ```yaml\\n...\\n```
        ```\\n...\\n```
        ``` yaml\\n...\\n```

    Args:
        text: Raw LLM output that may contain markdown fences.

    Returns:
        The text with fences removed, or unchanged if none found.
    """
    # Match ```yaml ... ``` or ``` ... ```
    pattern = r"^```(?:yaml|yml)?\s*\n(.*?)```\s*$"
    match = re.search(pattern, text.strip(), re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def validate_pipeline_yaml(
    yaml_str: str, pipeline_type: str
) -> dict[str, Any]:
    """Validate generated pipeline YAML through three layers.

    Args:
        yaml_str: The raw YAML string to validate.
        pipeline_type: The pipeline type for section requirements.

    Returns:
        {
            "valid": bool,
            "errors": list[str],
            "warnings": list[str],
            "sections_found": list[str],
            "sections_missing": list[str],
            "parsed_data": dict | None,
        }
    """
    result: dict[str, Any] = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "sections_found": [],
        "sections_missing": [],
        "parsed_data": None,
    }

    # --- Layer 1: YAML parsability ---
    cleaned = strip_markdown_fences(yaml_str)
    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError as e:
        result["valid"] = False
        result["errors"].append(f"YAML parse error: {e}")
        return result

    if not isinstance(data, dict):
        result["valid"] = False
        result["errors"].append(
            f"YAML parsed to {type(data).__name__}, expected dict"
        )
        return result

    result["parsed_data"] = data
    result["sections_found"] = list(data.keys())

    # --- Layer 2: Required sections ---
    found, missing = check_required_sections(data, pipeline_type)
    result["sections_found"] = found
    result["sections_missing"] = missing

    if missing:
        result["valid"] = False
        result["errors"].append(
            f"Missing required sections: {missing}"
        )

    # --- Layer 3: Field type checks ---
    warnings = check_field_types(data)
    result["warnings"] = warnings

    return result


def check_required_sections(
    data: dict[str, Any], pipeline_type: str
) -> tuple[list[str], list[str]]:
    """Check which required sections are present and which are missing.

    Args:
        data: Parsed YAML dictionary.
        pipeline_type: Pipeline type key.

    Returns:
        Tuple of (found_sections, missing_sections).
    """
    required = REQUIRED_SECTIONS.get(pipeline_type, [])
    found = [s for s in required if s in data]
    missing = [s for s in required if s not in data]
    return found, missing


def check_field_types(data: dict[str, Any]) -> list[str]:
    """Basic type checks on critical fields across all pipeline types.

    Args:
        data: Parsed YAML dictionary.

    Returns:
        List of warning messages for type mismatches.
    """
    warnings: list[str] = []

    # project.name should be a non-empty string
    project = data.get("project")
    if isinstance(project, dict):
        name = project.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            warnings.append("project.name should be a non-empty string")

        version = project.get("version")
        if version is not None and not isinstance(version, str):
            warnings.append("project.version should be a string")

    # success_criteria should be a dict or list
    criteria = data.get("success_criteria")
    if criteria is not None and not isinstance(criteria, (dict, list)):
        warnings.append("success_criteria should be a dict or list")

    # monitoring should be a dict
    monitoring = data.get("monitoring")
    if monitoring is not None and not isinstance(monitoring, dict):
        warnings.append("monitoring should be a dict")

    return warnings
