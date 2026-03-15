"""
Tests for conductor.agents.pipeline.validators
=================================================
"""

from __future__ import annotations

import pytest

from conductor.agents.pipeline.validators import (
    check_field_types,
    check_required_sections,
    strip_markdown_fences,
    validate_pipeline_yaml,
)


# =============================================================================
# Test strip_markdown_fences
# =============================================================================

class TestStripMarkdownFences:
    """Tests for markdown fence removal."""

    def test_removes_yaml_fence(self):
        text = "```yaml\nproject:\n  name: test\n```"
        assert strip_markdown_fences(text) == "project:\n  name: test"

    def test_removes_yml_fence(self):
        text = "```yml\nproject:\n  name: test\n```"
        assert strip_markdown_fences(text) == "project:\n  name: test"

    def test_removes_plain_fence(self):
        text = "```\nproject:\n  name: test\n```"
        assert strip_markdown_fences(text) == "project:\n  name: test"

    def test_no_fence_returns_stripped(self):
        text = "  project:\n  name: test  "
        result = strip_markdown_fences(text)
        assert result == "project:\n  name: test"

    def test_empty_string(self):
        assert strip_markdown_fences("") == ""

    def test_preserves_content_without_fences(self):
        text = "project:\n  name: test\nmonitoring:\n  enabled: true"
        assert strip_markdown_fences(text) == text


# =============================================================================
# Test check_required_sections
# =============================================================================

class TestCheckRequiredSections:
    """Tests for required section checking."""

    def test_all_present(self):
        data = {
            "project": {},
            "business_requirements": {},
            "data_sources": {},
            "transformations": {},
            "orchestration": {},
            "storage": {},
            "monitoring": {},
            "success_criteria": {},
        }
        found, missing = check_required_sections(data, "data_pipeline")
        assert len(missing) == 0
        assert len(found) == 8

    def test_some_missing(self):
        data = {"project": {}, "monitoring": {}}
        found, missing = check_required_sections(data, "data_pipeline")
        assert "project" in found
        assert "monitoring" in found
        assert "data_sources" in missing
        assert "transformations" in missing

    def test_unknown_type_returns_empty(self):
        data = {"project": {}}
        found, missing = check_required_sections(data, "unknown_type")
        assert found == []
        assert missing == []


# =============================================================================
# Test check_field_types
# =============================================================================

class TestCheckFieldTypes:
    """Tests for field type validation."""

    def test_valid_types_no_warnings(self):
        data = {
            "project": {"name": "test", "version": "1.0"},
            "success_criteria": {"technical": []},
            "monitoring": {"enabled": True},
        }
        warnings = check_field_types(data)
        assert warnings == []

    def test_empty_project_name_warns(self):
        data = {"project": {"name": ""}}
        warnings = check_field_types(data)
        assert any("project.name" in w for w in warnings)

    def test_non_string_version_warns(self):
        data = {"project": {"name": "test", "version": 123}}
        warnings = check_field_types(data)
        assert any("project.version" in w for w in warnings)

    def test_non_dict_monitoring_warns(self):
        data = {"monitoring": "enabled"}
        warnings = check_field_types(data)
        assert any("monitoring" in w for w in warnings)

    def test_non_dict_or_list_success_criteria_warns(self):
        data = {"success_criteria": "be good"}
        warnings = check_field_types(data)
        assert any("success_criteria" in w for w in warnings)


# =============================================================================
# Test validate_pipeline_yaml
# =============================================================================

class TestValidatePipelineYaml:
    """Tests for the full validation pipeline."""

    def test_valid_data_pipeline(self):
        yaml_str = """
project:
  name: test-pipeline
  version: "1.0"
business_requirements:
  objective: Test
data_sources:
  sources: []
transformations:
  layers: {}
orchestration:
  tool: airflow
storage:
  data_lake: {}
monitoring:
  enabled: true
success_criteria:
  technical:
    - metric: "quality"
"""
        result = validate_pipeline_yaml(yaml_str, "data_pipeline")
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert "project" in result["sections_found"]

    def test_unparseable_yaml(self):
        yaml_str = "{ invalid yaml: [unclosed"
        result = validate_pipeline_yaml(yaml_str, "data_pipeline")
        assert result["valid"] is False
        assert any("parse error" in e.lower() for e in result["errors"])

    def test_non_dict_yaml(self):
        yaml_str = "- just\n- a\n- list"
        result = validate_pipeline_yaml(yaml_str, "data_pipeline")
        assert result["valid"] is False
        assert any("expected dict" in e.lower() for e in result["errors"])

    def test_missing_sections(self):
        yaml_str = "project:\n  name: test"
        result = validate_pipeline_yaml(yaml_str, "data_pipeline")
        assert result["valid"] is False
        assert len(result["sections_missing"]) > 0
        assert "data_sources" in result["sections_missing"]

    def test_strips_markdown_fences(self):
        yaml_str = """```yaml
project:
  name: test-pipeline
  version: "1.0"
business_requirements:
  objective: Test
data_sources:
  sources: []
transformations:
  layers: {}
orchestration:
  tool: airflow
storage:
  data_lake: {}
monitoring:
  enabled: true
success_criteria:
  technical:
    - metric: quality
```"""
        result = validate_pipeline_yaml(yaml_str, "data_pipeline")
        assert result["valid"] is True

    def test_warnings_included(self):
        yaml_str = """
project:
  name: ""
  version: 123
business_requirements:
  objective: Test
data_sources:
  sources: []
transformations:
  layers: {}
orchestration:
  tool: airflow
storage:
  data_lake: {}
monitoring:
  enabled: true
success_criteria:
  technical: []
"""
        result = validate_pipeline_yaml(yaml_str, "data_pipeline")
        assert len(result["warnings"]) > 0

    def test_empty_yaml(self):
        result = validate_pipeline_yaml("", "data_pipeline")
        # Empty string parses to None
        assert result["valid"] is False
