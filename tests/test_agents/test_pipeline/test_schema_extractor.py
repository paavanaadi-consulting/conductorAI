"""
Tests for conductor.agents.pipeline.schema_extractor
=====================================================
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conductor.agents.pipeline.schema_extractor import (
    REQUIRED_SECTIONS,
    TEMPLATE_FILES,
    extract_schema_skeleton,
    infer_type_hint,
    load_template_schema,
)


# =============================================================================
# Locate the templates directory
# =============================================================================
TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"


# =============================================================================
# Test infer_type_hint
# =============================================================================

class TestInferTypeHint:
    """Tests for type hint inference from YAML values."""

    def test_none_returns_str(self):
        assert infer_type_hint(None) == "str"

    def test_empty_string_returns_str(self):
        assert infer_type_hint("") == "str"

    def test_string_returns_str(self):
        assert infer_type_hint("hello") == "str"

    def test_int_returns_int(self):
        assert infer_type_hint(42) == "int"

    def test_float_returns_float(self):
        assert infer_type_hint(3.14) == "float"

    def test_bool_returns_bool(self):
        assert infer_type_hint(True) == "bool"

    def test_list_of_strings(self):
        assert infer_type_hint(["a", "b"]) == "list[str]"

    def test_list_of_dicts(self):
        assert infer_type_hint([{"key": "val"}]) == "list[dict]"

    def test_empty_list(self):
        assert infer_type_hint([]) == "list"

    def test_dict_returns_dict(self):
        assert infer_type_hint({"key": "val"}) == "dict"


# =============================================================================
# Test extract_schema_skeleton
# =============================================================================

class TestExtractSchemaSkeleton:
    """Tests for schema skeleton extraction."""

    def test_flat_dict(self):
        data = {"name": "test", "version": "1.0", "count": 5}
        skeleton = extract_schema_skeleton(data)
        assert "name: str" in skeleton
        assert "version: str" in skeleton
        assert "count: int" in skeleton

    def test_nested_dict(self):
        data = {"project": {"name": "test", "version": "1.0"}}
        skeleton = extract_schema_skeleton(data)
        assert "project:" in skeleton
        assert "name: str" in skeleton

    def test_list_of_dicts(self):
        data = {"sources": [{"name": "s1", "type": "api"}]}
        skeleton = extract_schema_skeleton(data)
        assert "sources:" in skeleton
        assert "list[dict]" in skeleton
        assert "name: str" in skeleton

    def test_max_depth_limits_recursion(self):
        data = {
            "a": {"b": {"c": {"d": {"e": "deep"}}}}
        }
        skeleton_shallow = extract_schema_skeleton(data, max_depth=1)
        skeleton_deep = extract_schema_skeleton(data, max_depth=4)
        # Shallow should show 'c' as dict, deep should show 'e'
        assert "dict" in skeleton_shallow
        assert "e: str" in skeleton_deep

    def test_empty_dict(self):
        skeleton = extract_schema_skeleton({})
        assert skeleton == ""

    def test_non_dict_input(self):
        skeleton = extract_schema_skeleton("not a dict")  # type: ignore
        assert skeleton == ""


# =============================================================================
# Test REQUIRED_SECTIONS
# =============================================================================

class TestRequiredSections:
    """Tests for required sections configuration."""

    def test_all_pipeline_types_have_required_sections(self):
        for ptype in TEMPLATE_FILES:
            assert ptype in REQUIRED_SECTIONS, f"Missing required sections for {ptype}"

    def test_all_types_require_project_and_success_criteria(self):
        for ptype, sections in REQUIRED_SECTIONS.items():
            assert "project" in sections, f"{ptype} missing 'project'"
            assert "success_criteria" in sections, f"{ptype} missing 'success_criteria'"

    def test_most_types_require_monitoring(self):
        types_with_monitoring = {
            k for k, v in REQUIRED_SECTIONS.items() if "monitoring" in v
        }
        # All types except general should require monitoring
        assert "data_pipeline" in types_with_monitoring
        assert "ml_pipeline" in types_with_monitoring
        assert "rag_llm" in types_with_monitoring
        assert "agentic_ops" in types_with_monitoring
        assert "integration" in types_with_monitoring


# =============================================================================
# Test load_template_schema
# =============================================================================

class TestLoadTemplateSchema:
    """Tests for loading and extracting schemas from template files."""

    @pytest.mark.parametrize("pipeline_type", list(TEMPLATE_FILES.keys()))
    def test_load_schema_for_each_type(self, pipeline_type):
        """Each template type should return a string (possibly empty for invalid YAML)."""
        if not TEMPLATES_DIR.exists():
            pytest.skip("Templates directory not found")

        template_path = TEMPLATES_DIR / TEMPLATE_FILES[pipeline_type]
        if not template_path.exists():
            pytest.skip(f"Template file not found: {template_path}")

        skeleton = load_template_schema(pipeline_type, TEMPLATES_DIR)
        assert isinstance(skeleton, str)

    def test_parseable_templates_produce_nonempty_skeleton(self):
        """Templates that parse correctly should produce non-empty skeletons."""
        if not TEMPLATES_DIR.exists():
            pytest.skip("Templates directory not found")

        for ptype in ["data_pipeline", "ml_pipeline"]:
            template_path = TEMPLATES_DIR / TEMPLATE_FILES[ptype]
            if not template_path.exists():
                continue
            skeleton = load_template_schema(ptype, TEMPLATES_DIR)
            assert len(skeleton) > 0, f"{ptype} skeleton should not be empty"
            assert ":" in skeleton

    def test_skeleton_under_500_lines(self):
        """Schema skeleton with depth=2 should be compact."""
        if not TEMPLATES_DIR.exists():
            pytest.skip("Templates directory not found")

        for ptype in TEMPLATE_FILES:
            template_path = TEMPLATES_DIR / TEMPLATE_FILES[ptype]
            if not template_path.exists():
                continue

            skeleton = load_template_schema(ptype, TEMPLATES_DIR)
            if not skeleton:
                continue  # Unparseable templates return empty
            line_count = len(skeleton.split("\n"))
            assert line_count < 500, (
                f"{ptype} skeleton is {line_count} lines, expected < 500"
            )

    def test_unknown_type_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown pipeline type"):
            load_template_schema("nonexistent_type", TEMPLATES_DIR)

    def test_missing_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_template_schema("data_pipeline", Path("/tmp/nonexistent"))
