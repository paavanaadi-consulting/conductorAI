"""
Tests for ReadmeGeneratorAgent
==============================

Unit and integration tests for the README generation agent.
"""

import pytest
from conductor.agents.development.readme_generator_agent import (
    ReadmeGeneratorAgent,
)
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, TaskStatus
from conductor.core.models import TaskDefinition
from conductor.integrations.llm.mock import MockLLMProvider


SAMPLE_INFRA_YAML = """\
registry_version: "1.0"
organization: "Test Corp"
compute:
  kubernetes:
    clusters: ["eks-prod"]
storage:
  rds:
    engines: ["postgres15"]
monitoring:
  metrics: "prometheus"
"""

SAMPLE_REQUIREMENTS_YAML = """\
project_name: "test-api"
team: "Test Team"
priority: "high"
description: Test project
performance:
  availability: "99.95%"
"""


@pytest.mark.unit
class TestReadmeGeneratorAgentValidation:
    """Tests for task validation."""

    @pytest.fixture
    async def agent(self):
        """Create a README generator agent."""
        config = ConductorConfig()
        llm = MockLLMProvider()
        agent = ReadmeGeneratorAgent("readme-test", config, llm_provider=llm)
        await agent.start()
        yield agent
        await agent.stop()

    @pytest.mark.asyncio
    async def test_validate_task_with_required_fields(self, agent):
        """Should validate tasks with infra_yaml and requirements_yaml."""
        task = TaskDefinition(
            name="Generate README",
            assigned_to=AgentType.CODING,
            input_data={
                "infra_yaml": SAMPLE_INFRA_YAML,
                "requirements_yaml": SAMPLE_REQUIREMENTS_YAML,
            },
        )
        assert await agent._validate_task(task) is True

    @pytest.mark.asyncio
    async def test_validate_task_missing_infra_yaml(self, agent):
        """Should reject tasks without infra_yaml."""
        task = TaskDefinition(
            name="Generate README",
            assigned_to=AgentType.CODING,
            input_data={"requirements_yaml": SAMPLE_REQUIREMENTS_YAML},
        )
        assert await agent._validate_task(task) is False

    @pytest.mark.asyncio
    async def test_validate_task_missing_requirements_yaml(self, agent):
        """Should reject tasks without requirements_yaml."""
        task = TaskDefinition(
            name="Generate README",
            assigned_to=AgentType.CODING,
            input_data={"infra_yaml": SAMPLE_INFRA_YAML},
        )
        assert await agent._validate_task(task) is False


@pytest.mark.unit
class TestReadmeGeneratorYAMLParsing:
    """Tests for YAML parsing."""

    @pytest.fixture
    def agent(self):
        """Create a README generator agent."""
        config = ConductorConfig()
        llm = MockLLMProvider()
        agent = ReadmeGeneratorAgent("readme-test", config, llm_provider=llm)
        return agent

    def test_parse_valid_yaml(self, agent):
        """Should parse valid YAML correctly."""
        data = agent._parse_yaml(SAMPLE_INFRA_YAML)
        assert data["registry_version"] == "1.0"
        assert data["organization"] == "Test Corp"
        assert "compute" in data

    def test_parse_empty_yaml(self, agent):
        """Should handle empty YAML."""
        data = agent._parse_yaml("")
        assert data == {}

    def test_parse_invalid_yaml(self, agent):
        """Should handle invalid YAML gracefully."""
        invalid_yaml = "{ invalid: yaml: content: ["
        data = agent._parse_yaml(invalid_yaml)
        assert data == {}

    def test_parse_non_string_input(self, agent):
        """Should handle non-string input."""
        data = agent._parse_yaml(None)
        assert data == {}


@pytest.mark.unit
class TestReadmeGeneratorMetadataExtraction:
    """Tests for metadata extraction."""

    @pytest.fixture
    def agent(self):
        """Create a README generator agent."""
        config = ConductorConfig()
        llm = MockLLMProvider()
        agent = ReadmeGeneratorAgent("readme-test", config, llm_provider=llm)
        return agent

    def test_extract_metadata(self, agent):
        """Should extract metadata from YAML."""
        infra_data = agent._parse_yaml(SAMPLE_INFRA_YAML)
        requirements_data = agent._parse_yaml(SAMPLE_REQUIREMENTS_YAML)

        metadata = agent._extract_metadata(
            infra_data,
            requirements_data,
            "My Project",
        )

        assert metadata["project_name"] == "My Project"
        assert metadata["organization"] == "Test Corp"
        assert metadata["team"] == "Test Team"
        assert metadata["priority"] == "high"
        assert "compute" in str(metadata["compute_platforms"])

    def test_extract_metadata_empty_data(self, agent):
        """Should handle empty data."""
        metadata = agent._extract_metadata({}, {}, "Default Project")
        assert metadata["project_name"] == "Default Project"
        assert metadata["organization"] == ""


@pytest.mark.unit
class TestReadmeGeneratorSummaries:
    """Tests for infrastructure and requirements summarization."""

    @pytest.fixture
    def agent(self):
        """Create a README generator agent."""
        config = ConductorConfig()
        llm = MockLLMProvider()
        agent = ReadmeGeneratorAgent("readme-test", config, llm_provider=llm)
        return agent

    def test_summarize_infra(self, agent):
        """Should create infrastructure summary."""
        infra_data = agent._parse_yaml(SAMPLE_INFRA_YAML)
        summary = agent._summarize_infra(infra_data)

        assert "Compute" in summary
        assert "Storage" in summary
        assert "Monitoring" in summary

    def test_summarize_infra_empty(self, agent):
        """Should handle empty infrastructure data."""
        summary = agent._summarize_infra({})
        assert "No infrastructure data" in summary

    def test_summarize_requirements(self, agent):
        """Should create requirements summary."""
        req_data = agent._parse_yaml(SAMPLE_REQUIREMENTS_YAML)
        summary = agent._summarize_requirements(req_data)

        assert "test-api" in summary or "Project" in summary


@pytest.mark.integration
class TestReadmeGeneratorExecution:
    """Integration tests for README generation."""

    @pytest.mark.asyncio
    async def test_execute_readme_generation(self):
        """Should generate README from YAML specifications."""
        config = ConductorConfig()
        llm = MockLLMProvider()
        llm.queue_response("Generated README content here")

        agent = ReadmeGeneratorAgent("readme-test", config, llm_provider=llm)
        await agent.start()

        task = TaskDefinition(
            name="Generate README",
            assigned_to=AgentType.CODING,
            input_data={
                "infra_yaml": SAMPLE_INFRA_YAML,
                "requirements_yaml": SAMPLE_REQUIREMENTS_YAML,
                "project_name": "Test Project",
                "include_sections": ["overview", "architecture"],
            },
        )

        result = await agent.execute_task(task)

        assert result.task_id == task.task_id
        assert result.status == TaskStatus.COMPLETED
        assert "readme_md" in result.output_data
        assert "sections_generated" in result.output_data
        assert len(result.output_data["sections_generated"]) > 0

        await agent.stop()

    @pytest.mark.asyncio
    async def test_execute_readme_with_all_sections(self):
        """Should generate README with all sections."""
        config = ConductorConfig()
        llm = MockLLMProvider()
        llm.queue_response("Section content")

        agent = ReadmeGeneratorAgent("readme-test", config, llm_provider=llm)
        await agent.start()

        all_sections = [
            "overview",
            "architecture",
            "setup",
            "usage",
            "testing",
            "deployment",
            "monitoring",
            "troubleshooting",
        ]

        task = TaskDefinition(
            name="Generate Comprehensive README",
            assigned_to=AgentType.CODING,
            input_data={
                "infra_yaml": SAMPLE_INFRA_YAML,
                "requirements_yaml": SAMPLE_REQUIREMENTS_YAML,
                "project_name": "Comprehensive API",
                "include_sections": all_sections,
            },
        )

        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        readme = result.output_data["readme_md"]
        assert "Comprehensive API" in readme
        assert "Table of Contents" in readme

        await agent.stop()

