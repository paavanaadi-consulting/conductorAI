"""
Tests for conductor.agents.pipeline.pipeline_yaml_generator
=============================================================
"""

from __future__ import annotations

import textwrap

import pytest

from conductor.agents.pipeline.pipeline_yaml_generator import (
    PipelineYamlGeneratorAgent,
)
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, TaskStatus
from conductor.core.models import TaskDefinition
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Sample YAML fixtures
# =============================================================================

SAMPLE_DATA_REQUIREMENTS = textwrap.dedent("""\
    project_name: "customer-360-pipeline"
    team: "data-engineering"
    contact_email: "team@example.com"
    priority: "high"
    target_date: "2026-06-30"

    description: |
      Build a unified customer data pipeline.

    pipeline_type: "batch"
    architecture: "medallion"

    sources:
      - name: "Salesforce CRM"
        type: "api"
        technology: "REST API"
        update_frequency: "daily"
        estimated_volume: "500K records"

    destination:
      target: "Snowflake"
      format: "parquet"
      partitioning: "by date"

    quality_requirements:
      freshness: "Data available within 1 hour"
      accuracy: ">= 99%"
      completeness: "No null values in required fields"
      deduplication: true

    schedule:
      batch_frequency: "daily at 2AM UTC"
      sla: "Data available by 7 AM"

    consumers:
      - team: "Marketing"
        use_case: "Customer segmentation"
        data_needed: ["demographics", "purchase_history"]

    preferences:
      orchestrator: "airflow"
      processing_engine: "dbt"
      cloud_provider: "aws"

    compliance:
      regulations: [GDPR, SOC2]
      pii_handling: "mask"
      retention_period: "7 years"
      lineage_required: true

    success_criteria:
      - "All batch jobs complete within SLA window"
      - ">= 99% data quality score"
""")

SAMPLE_ML_REQUIREMENTS = textwrap.dedent("""\
    project_name: "churn-prediction"
    team: "ml-team"
    priority: "high"

    problem_type: "binary_classification"
    ml_type: "supervised"
    deployment: "batch"

    training_data:
      source: "Snowflake warehouse"
      size: "5M rows, 200 features"
      label_column: "churned"

    model_requirements:
      target_metric: "AUC-ROC >= 0.85"
""")

SAMPLE_RAG_REQUIREMENTS = textwrap.dedent("""\
    project_name: "knowledge-assistant"
    team: "ai-team"
    priority: "high"

    project_type: "rag_application"
    use_case: "question_answering"

    knowledge_sources:
      - name: "Confluence Wiki"
        type: "documentation"
        estimated_size: "10K pages"

    quality:
      accuracy_target: ">= 85%"
      hallucination_tolerance: "< 5%"
""")

SAMPLE_AGENTIC_REQUIREMENTS = textwrap.dedent("""\
    project_name: "incident-response"
    team: "sre-team"
    priority: "critical"

    agent_architecture: "multi_agent"
    orchestration: "conductor"
    domain: "devops_automation"

    agents:
      - name: "Incident Detector"
        role: "Monitor metrics"
        autonomy: "fully_autonomous"
        actions: ["query metrics", "send alerts"]

    autonomy_rules:
      auto_approve: ["scale up pods"]
      require_approval: ["deploy to prod"]

    safety:
      max_actions_per_incident: "5"
      kill_switch: true
""")

SAMPLE_INTEGRATION_REQUIREMENTS = textwrap.dedent("""\
    project_name: "legacy-migration"
    team: "platform-team"
    priority: "high"

    integration_type: "legacy_modernization"
    scope: "end_to_end"

    existing_systems:
      - name: "Customer ETL"
        technology: "Jenkins + Python 2.7"
        status: "degraded"

    target:
      platform: "Airflow + dbt + Snowflake"
      architecture: "Medallion lakehouse"

    strategy:
      approach: "phased"
      data_migration: "incremental"
""")

SAMPLE_GENERAL_REQUIREMENTS = textwrap.dedent("""\
    project_name: "internal-tool"
    team: "platform-team"
    priority: "medium"

    description: |
      Build an internal dashboard for monitoring team metrics.

    features:
      - name: "Dashboard"
        description: "Real-time metrics view"

    users:
      audience: "Engineering team"
      estimated_count: "200"
""")

SAMPLE_INFRA = textwrap.dedent("""\
    registry_version: "1.0"
    organization: "Acme Corp"
    last_updated: "2026-03-14"

    compute:
      kubernetes:
        clusters: ["eks-prod", "eks-staging"]
        max_nodes: 50
      lambda:
        runtime: ["python3.11"]
        timeout_max: 900

    storage:
      s3:
        buckets_allowed: true
        max_size_tb: 50
        encryption: "AES-256"
      snowflake:
        warehouse_sizes: ["XSMALL", "SMALL", "MEDIUM"]

    orchestration:
      airflow:
        version: "2.8"
        deployment: "mwaa"

    ci_cd:
      provider: "github_actions"
      iac_tool: "terraform"

    constraints:
      cloud_provider: "aws"
      region: "us-east-1"
      compliance: ["SOC2", "GDPR"]
""")

# A mock LLM response that is a valid pipeline YAML
MOCK_PIPELINE_YAML = textwrap.dedent("""\
    project:
      name: "customer-360-pipeline"
      version: "1.0.0"
      description: "Unified customer data pipeline"
      pipeline_type: "batch"
      architecture: "medallion"
      domain: "customer_analytics"
      priority: "high"
      deadline: "2026-06-30"
    business_requirements:
      objective: "Build unified customer data pipeline"
      success_metrics:
        - metric: "data_freshness"
          target: "< 1 hour"
    data_sources:
      sources:
        - name: "salesforce_crm"
          type: "api"
          technology: "REST API"
    transformations:
      layers:
        bronze:
          description: "Raw data ingestion"
          storage: "s3://data-lake/bronze/"
    orchestration:
      tool: "apache_airflow"
      version: "2.8.0"
    storage:
      data_lake:
        provider: "aws_s3"
    monitoring:
      pipeline_metrics:
        - name: "job_success_rate"
          target: ">= 99%"
    success_criteria:
      technical:
        - metric: "quality_score"
          target: ">= 99%"
""")

MOCK_CONTEXT_RESPONSE = textwrap.dedent("""\
    ### DECISIONS
    - Chose Apache Airflow for orchestration because infra registry has MWAA available
    - Selected Snowflake as warehouse because it's the only warehouse in infra registry
    - Used medallion architecture as specified in requirements

    ### CONFIDENCE
    Overall confidence: 85%
    - project section: 95% - clearly specified
    - data_sources: 80% - API details need validation
    - monitoring: 70% - requirements were vague on alerting
""")


# =============================================================================
# Test PipelineYamlGeneratorAgent Init
# =============================================================================

class TestPipelineYamlGeneratorInit:
    """Tests for agent initialization."""

    def test_creates_with_correct_type(self, config, mock_llm_provider):
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=mock_llm_provider
        )
        assert agent.agent_type == AgentType.PIPELINE_GENERATOR

    def test_default_name(self, config, mock_llm_provider):
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=mock_llm_provider
        )
        assert "PipelineYamlGenerator" in agent.identity.name

    def test_custom_name(self, config, mock_llm_provider):
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=mock_llm_provider,
            name="CustomGen"
        )
        assert agent.identity.name == "CustomGen"

    def test_llm_provider_accessible(self, config, mock_llm_provider):
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=mock_llm_provider
        )
        assert agent.llm_provider is mock_llm_provider


# =============================================================================
# Test Pipeline Type Detection
# =============================================================================

class TestPipelineTypeDetection:
    """Tests for pipeline type auto-detection."""

    def test_detects_data_pipeline(self):
        import yaml
        reqs = yaml.safe_load(SAMPLE_DATA_REQUIREMENTS)
        ptype, confidence = PipelineYamlGeneratorAgent._detect_pipeline_type(reqs)
        assert ptype == "data_pipeline"
        assert confidence > 0.5

    def test_detects_ml_pipeline(self):
        import yaml
        reqs = yaml.safe_load(SAMPLE_ML_REQUIREMENTS)
        ptype, confidence = PipelineYamlGeneratorAgent._detect_pipeline_type(reqs)
        assert ptype == "ml_pipeline"
        assert confidence > 0.5

    def test_detects_rag_llm(self):
        import yaml
        reqs = yaml.safe_load(SAMPLE_RAG_REQUIREMENTS)
        ptype, confidence = PipelineYamlGeneratorAgent._detect_pipeline_type(reqs)
        assert ptype == "rag_llm"
        assert confidence > 0.3

    def test_detects_agentic_ops(self):
        import yaml
        reqs = yaml.safe_load(SAMPLE_AGENTIC_REQUIREMENTS)
        ptype, confidence = PipelineYamlGeneratorAgent._detect_pipeline_type(reqs)
        assert ptype == "agentic_ops"
        assert confidence > 0.5

    def test_detects_integration(self):
        import yaml
        reqs = yaml.safe_load(SAMPLE_INTEGRATION_REQUIREMENTS)
        ptype, confidence = PipelineYamlGeneratorAgent._detect_pipeline_type(reqs)
        assert ptype == "integration"
        assert confidence > 0.5

    def test_ambiguous_defaults_to_general(self):
        reqs = {"project_name": "test", "team": "eng"}
        ptype, confidence = PipelineYamlGeneratorAgent._detect_pipeline_type(reqs)
        assert ptype == "general"

    def test_empty_dict_defaults_to_general(self):
        ptype, confidence = PipelineYamlGeneratorAgent._detect_pipeline_type({})
        assert ptype == "general"
        assert confidence == 0.5


# =============================================================================
# Test Task Validation
# =============================================================================

class TestTaskValidation:
    """Tests for task input validation."""

    @pytest.mark.asyncio
    async def test_valid_task_passes(self, config, mock_llm_provider):
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=mock_llm_provider
        )
        task = TaskDefinition(
            name="Generate Pipeline",
            assigned_to=AgentType.PIPELINE_GENERATOR,
            input_data={
                "requirements_yaml": SAMPLE_DATA_REQUIREMENTS,
                "infra_yaml": SAMPLE_INFRA,
            },
        )
        assert await agent._validate_task(task) is True

    @pytest.mark.asyncio
    async def test_missing_requirements_fails(self, config, mock_llm_provider):
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=mock_llm_provider
        )
        task = TaskDefinition(
            name="Generate Pipeline",
            input_data={"infra_yaml": SAMPLE_INFRA},
        )
        assert await agent._validate_task(task) is False

    @pytest.mark.asyncio
    async def test_missing_infra_fails(self, config, mock_llm_provider):
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=mock_llm_provider
        )
        task = TaskDefinition(
            name="Generate Pipeline",
            input_data={"requirements_yaml": SAMPLE_DATA_REQUIREMENTS},
        )
        assert await agent._validate_task(task) is False


# =============================================================================
# Test Pipeline Generation (Full Execution)
# =============================================================================

class TestPipelineGeneration:
    """Tests for full pipeline YAML generation."""

    @pytest.mark.asyncio
    async def test_full_execution_succeeds(self, config):
        provider = MockLLMProvider()
        # Queue: generation response + context response
        provider.queue_response(MOCK_PIPELINE_YAML)
        provider.queue_response(MOCK_CONTEXT_RESPONSE)

        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=provider
        )
        await agent.start()

        task = TaskDefinition(
            name="Generate Pipeline",
            assigned_to=AgentType.PIPELINE_GENERATOR,
            input_data={
                "requirements_yaml": SAMPLE_DATA_REQUIREMENTS,
                "infra_yaml": SAMPLE_INFRA,
            },
        )
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "pipeline_yaml" in result.output_data
        assert result.output_data["pipeline_type"] == "data_pipeline"
        assert "validation_result" in result.output_data
        assert "llm_model" in result.output_data

    @pytest.mark.asyncio
    async def test_explicit_type_override(self, config):
        provider = MockLLMProvider()
        provider.queue_response(MOCK_PIPELINE_YAML)
        provider.queue_response(MOCK_CONTEXT_RESPONSE)

        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=provider
        )
        await agent.start()

        task = TaskDefinition(
            name="Generate Pipeline",
            assigned_to=AgentType.PIPELINE_GENERATOR,
            input_data={
                "requirements_yaml": SAMPLE_DATA_REQUIREMENTS,
                "infra_yaml": SAMPLE_INFRA,
                "pipeline_type": "ml_pipeline",
            },
        )
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.output_data["pipeline_type"] == "ml_pipeline"
        assert result.output_data["pipeline_type_confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_output_contains_sections_generated(self, config):
        provider = MockLLMProvider()
        provider.queue_response(MOCK_PIPELINE_YAML)
        provider.queue_response(MOCK_CONTEXT_RESPONSE)

        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=provider
        )
        await agent.start()

        task = TaskDefinition(
            name="Generate Pipeline",
            assigned_to=AgentType.PIPELINE_GENERATOR,
            input_data={
                "requirements_yaml": SAMPLE_DATA_REQUIREMENTS,
                "infra_yaml": SAMPLE_INFRA,
            },
        )
        result = await agent.execute_task(task)

        sections = result.output_data.get("sections_generated", [])
        assert isinstance(sections, list)
        assert len(sections) > 0

    @pytest.mark.asyncio
    async def test_invalid_requirements_yaml_fails(self, config):
        provider = MockLLMProvider()
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=provider
        )
        await agent.start()

        task = TaskDefinition(
            name="Generate Pipeline",
            assigned_to=AgentType.PIPELINE_GENERATOR,
            input_data={
                "requirements_yaml": "{ invalid yaml [",
                "infra_yaml": SAMPLE_INFRA,
            },
        )
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        assert "error" in result.output_data

    @pytest.mark.asyncio
    async def test_llm_call_count(self, config):
        """Generation uses 1 LLM call + 1 context call = 2 total."""
        provider = MockLLMProvider()
        provider.queue_response(MOCK_PIPELINE_YAML)
        provider.queue_response(MOCK_CONTEXT_RESPONSE)

        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=provider
        )
        await agent.start()

        task = TaskDefinition(
            name="Generate Pipeline",
            assigned_to=AgentType.PIPELINE_GENERATOR,
            input_data={
                "requirements_yaml": SAMPLE_DATA_REQUIREMENTS,
                "infra_yaml": SAMPLE_INFRA,
            },
        )
        await agent.execute_task(task)

        assert provider.call_count == 2


# =============================================================================
# Test Context Generation
# =============================================================================

class TestContextGeneration:
    """Tests for .context/ entry generation."""

    @pytest.mark.asyncio
    async def test_context_entries_in_metadata(self, config):
        provider = MockLLMProvider()
        provider.queue_response(MOCK_PIPELINE_YAML)
        provider.queue_response(MOCK_CONTEXT_RESPONSE)

        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=provider
        )
        await agent.start()

        task = TaskDefinition(
            name="Generate Pipeline",
            assigned_to=AgentType.PIPELINE_GENERATOR,
            input_data={
                "requirements_yaml": SAMPLE_DATA_REQUIREMENTS,
                "infra_yaml": SAMPLE_INFRA,
            },
        )
        result = await agent.execute_task(task)

        context_entries = result.metadata.get("context_entries", [])
        assert len(context_entries) > 0

        # Should have decisions.md and confidence-report.md
        files = [e["context_file"] for e in context_entries]
        assert "decisions.md" in files
        assert "confidence-report.md" in files


# =============================================================================
# Test Error Handling
# =============================================================================

class TestErrorHandling:
    """Tests for error scenarios."""

    @pytest.mark.asyncio
    async def test_agent_returns_to_idle_after_failure(self, config):
        provider = MockLLMProvider()
        agent = PipelineYamlGeneratorAgent(
            "pipeline-01", config, llm_provider=provider
        )
        await agent.start()

        task = TaskDefinition(
            name="Generate Pipeline",
            assigned_to=AgentType.PIPELINE_GENERATOR,
            input_data={
                "requirements_yaml": "{ broken [yaml",
                "infra_yaml": SAMPLE_INFRA,
            },
        )
        result = await agent.execute_task(task)

        assert result.status == TaskStatus.FAILED
        # Agent should return to IDLE after failure
        from conductor.core.enums import AgentStatus
        assert agent.status == AgentStatus.IDLE


# =============================================================================
# Test Parse Context Response
# =============================================================================

class TestParseContextResponse:
    """Tests for context response parsing."""

    def test_parses_decisions_and_confidence(self):
        parsed = PipelineYamlGeneratorAgent._parse_context_response(
            MOCK_CONTEXT_RESPONSE
        )
        assert "decisions" in parsed
        assert "confidence" in parsed
        assert "Airflow" in parsed["decisions"]

    def test_extracts_confidence_score(self):
        parsed = PipelineYamlGeneratorAgent._parse_context_response(
            MOCK_CONTEXT_RESPONSE
        )
        assert "confidence_score" in parsed
        assert parsed["confidence_score"] == 0.85

    def test_handles_empty_response(self):
        parsed = PipelineYamlGeneratorAgent._parse_context_response("")
        assert parsed == {}

    def test_handles_response_without_markers(self):
        parsed = PipelineYamlGeneratorAgent._parse_context_response(
            "Just some random text without section markers."
        )
        assert parsed == {}
