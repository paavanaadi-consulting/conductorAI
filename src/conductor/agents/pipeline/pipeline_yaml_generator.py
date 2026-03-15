"""
conductor.agents.pipeline.pipeline_yaml_generator - Pipeline YAML Generation Agent
====================================================================================

Generates a complete pipeline specification YAML from simplified business
requirements and an infrastructure registry. Detects the pipeline type,
loads the corresponding template schema, and uses the LLM to produce a
fully populated pipeline specification.

Architecture Context:
    The PipelineYamlGeneratorAgent operates *before* the standard workflow
    phases — it produces the specification that other agents consume.

    ┌──────────────────┐    TaskDefinition     ┌──────────────────────────┐
    │ AgentCoordinator │ ──────────────────→   │ PipelineYamlGenerator    │
    │                  │                       │                           │
    │                  │ ←── TaskResult ────── │  ┌─────────┐ ┌────────┐ │
    └──────────────────┘                       │  │ LLM     │ │ Schema │ │
                                               │  │ Provider│ │ Extract│ │
                                               │  └─────────┘ └────────┘ │
                                               └──────────────────────────┘

    Input (task.input_data):
        {
            "requirements_yaml": "...",        # Raw YAML from templates/requirements/
            "infra_yaml": "...",               # Raw YAML from templates/infrastructure/
            "pipeline_type": "auto",           # Optional: auto | data_pipeline | ml_pipeline | ...
        }

    Output (result.output_data):
        {
            "pipeline_yaml": "...",            # The complete generated pipeline YAML
            "pipeline_type": "data_pipeline",  # Detected or specified type
            "pipeline_type_confidence": 0.9,   # Detection confidence
            "sections_generated": [...],       # Top-level sections in the output
            "validation_result": {...},        # Parse + section + type check results
            "decisions_summary": "...",        # Key architectural decisions
            "llm_model": "...",
            "llm_usage": {...},
            "generation_stages": 2,            # Number of LLM calls made
        }

Usage:
    >>> from conductor.agents.pipeline import PipelineYamlGeneratorAgent
    >>> agent = PipelineYamlGeneratorAgent("pipeline-gen-01", config, llm_provider=provider)
    >>> await agent.start()
    >>> task = TaskDefinition(
    ...     name="Generate Data Pipeline YAML",
    ...     assigned_to=AgentType.PIPELINE_GENERATOR,
    ...     input_data={"requirements_yaml": req_yaml, "infra_yaml": infra_yaml},
    ... )
    >>> result = await agent.execute_task(task)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import structlog
import yaml

from conductor.agents.base import BaseAgent
from conductor.agents.pipeline.schema_extractor import (
    REQUIRED_SECTIONS,
    load_template_schema,
)
from conductor.agents.pipeline.validators import (
    strip_markdown_fences,
    validate_pipeline_yaml,
)
from conductor.core.config import ConductorConfig
from conductor.core.context_models import ContextContribution, ContextEntry
from conductor.core.enums import AgentType, TaskStatus
from conductor.core.models import TaskDefinition, TaskResult
from conductor.integrations.llm.base import BaseLLMProvider


# =============================================================================
# Logger
# =============================================================================
logger = structlog.get_logger()


# =============================================================================
# Pipeline Type Detection
# =============================================================================
# Each pipeline type is identified by the presence of specific keys in the
# requirements YAML. The type with the highest match score wins.
# =============================================================================
PIPELINE_TYPE_INDICATORS: dict[str, list[str]] = {
    "data_pipeline": [
        "pipeline_type", "sources", "destination", "schedule",
        "quality_requirements", "consumers",
    ],
    "ml_pipeline": [
        "problem_type", "ml_type", "training_data", "model_requirements",
        "features", "inference", "retraining",
    ],
    "rag_llm": [
        "project_type", "knowledge_sources", "quality",
        "users", "budget",
    ],
    "agentic_ops": [
        "agent_architecture", "agents", "autonomy_rules", "safety",
        "llm_config", "integrations",
    ],
    "integration": [
        "integration_type", "existing_systems", "target", "strategy",
        "constraints",
    ],
}

# Values that strongly indicate a specific type
PIPELINE_TYPE_VALUES: dict[str, dict[str, list[str]]] = {
    "data_pipeline": {
        "pipeline_type": ["batch", "streaming", "batch_and_streaming"],
        "architecture": ["medallion", "lambda", "kappa", "simple_etl"],
    },
    "ml_pipeline": {
        "problem_type": [
            "binary_classification", "multi_class", "regression",
            "ranking", "clustering", "anomaly_detection", "forecasting",
        ],
        "ml_type": [
            "supervised", "unsupervised", "deep_learning",
            "time_series", "nlp", "computer_vision",
        ],
    },
    "rag_llm": {
        "project_type": [
            "rag_application", "chatbot", "summarization",
            "content_generation", "code_assistant",
        ],
    },
    "agentic_ops": {
        "agent_architecture": [
            "single_agent", "multi_agent", "hierarchical", "swarm",
        ],
    },
    "integration": {
        "integration_type": [
            "legacy_modernization", "multi_pipeline_integration",
            "platform_consolidation", "single_pipeline_migration",
        ],
    },
}


# =============================================================================
# System Prompts
# =============================================================================
BASE_SYSTEM_PROMPT = """You are a senior solutions architect generating a production-ready pipeline specification YAML.

You have been given:
1. BUSINESS REQUIREMENTS — what the stakeholder needs built
2. INFRASTRUCTURE REGISTRY — what compute, storage, networking, and tools are available
3. SCHEMA SKELETON — the expected structure and sections of the output YAML

RULES:
- Output ONLY valid YAML. No markdown code fences. No prose before or after the YAML.
- Fill EVERY section from the schema with concrete, realistic values.
- Derive values from the requirements. Where requirements are silent, use sensible defaults.
- Map infrastructure capabilities to config values:
  - If infra has snowflake, use Snowflake for warehouse sections.
  - If infra has airflow, use Airflow for orchestration.
  - If infra constrains to a specific cloud provider, only use that provider's services.
- Add YAML comments (# Decision: ...) explaining WHY for non-obvious choices.
- Values must be deployment-ready, not placeholders like "TBD" or "FILL_IN".
- Respect constraints from the infrastructure registry (banned_services, region, compliance).
- Ensure the output is a single YAML document (no --- separators)."""

TYPE_SPECIFIC_ADDENDA: dict[str, str] = {
    "data_pipeline": (
        "Focus on: data source configs with authentication and ingestion modes, "
        "transformation logic with medallion/lakehouse layers, orchestration DAGs "
        "with task dependencies, streaming configs if applicable, data quality rules "
        "with validation tools, and lineage tracking."
    ),
    "ml_pipeline": (
        "Focus on: feature engineering pipeline, model training configs with "
        "hyperparameter ranges, experiment tracking setup, model serving "
        "infrastructure, retraining triggers and schedules, model monitoring "
        "with drift detection, and model registry/governance."
    ),
    "rag_llm": (
        "Focus on: knowledge source ingestion and chunking strategy, embedding "
        "model and vector database configuration, retrieval strategy (hybrid search, "
        "re-ranking), LLM prompt chains and guardrails, response quality evaluation, "
        "and cost management per query."
    ),
    "agentic_ops": (
        "Focus on: agent definitions with roles and capabilities, tool bindings "
        "with access levels, autonomy boundaries and approval gates, safety "
        "guardrails with kill switches, human-in-the-loop checkpoints, and "
        "observability for agent actions."
    ),
    "integration": (
        "Focus on: current state inventory of legacy systems, target state "
        "architecture, migration strategy with phased approach, parallel run "
        "configuration, data migration plans with validation, rollback procedures, "
        "and decommission timeline."
    ),
    "general": (
        "Focus on: feature breakdown with user stories, API endpoint definitions, "
        "database schema design, deployment strategy with environments, testing "
        "strategy covering unit/integration/e2e, and monitoring setup."
    ),
}

REPAIR_SYSTEM_PROMPT = """You are fixing an incomplete pipeline YAML specification.
The YAML is missing some required sections. Add the missing sections with realistic,
deployment-ready values based on the context already present in the YAML.

Output the COMPLETE corrected YAML — including the existing sections unchanged plus
the new sections added. Output ONLY valid YAML, no markdown fences or prose."""

CONTEXT_SYSTEM_PROMPT = """You are documenting the architectural decisions and confidence levels for a pipeline YAML specification you just generated.

Produce a structured report with EXACTLY these two sections:

### DECISIONS
For each major architectural choice in the generated YAML, explain:
- What was decided and the specific value chosen
- Why this choice was made (which requirement or infrastructure constraint drove it)
- What alternatives were available but not chosen

### CONFIDENCE
Rate your confidence (0-100%) for each top-level section of the generated YAML.
For each section explain:
- What was clearly specified vs ambiguous in the requirements
- Which sections need human review before deployment

Be specific, concise, and operational. Use markdown formatting."""


class PipelineYamlGeneratorAgent(BaseAgent):
    """Generates complete pipeline YAML from requirements + infrastructure inputs.

    Detects pipeline type, loads the corresponding template schema, and uses
    an LLM to produce a fully populated pipeline specification YAML.

    Extends BaseAgent:
        - _validate_task(): Checks for requirements_yaml and infra_yaml
        - _execute(): Multi-stage: detect type → load schema → LLM → validate → repair
        - _generate_context(): Produces decisions.md and confidence-report.md

    Attributes:
        _llm_provider: The LLM provider for YAML generation.
        _templates_dir: Path to the templates/ directory.
    """

    def __init__(
        self,
        agent_id: str,
        config: ConductorConfig,
        *,
        llm_provider: BaseLLMProvider,
        templates_dir: Optional[Path] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.PIPELINE_GENERATOR,
            config=config,
            name=name or f"PipelineYamlGenerator-{agent_id}",
            description=description or "Generates pipeline YAML from requirements and infrastructure",
        )

        self._llm_provider = llm_provider
        self._templates_dir = templates_dir or Path(__file__).resolve().parents[3] / "templates"

        self._logger = logger.bind(
            agent_id=agent_id,
            agent_type="pipeline_generator",
            component="pipeline_yaml_generator",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def llm_provider(self) -> BaseLLMProvider:
        """Access the LLM provider."""
        return self._llm_provider

    @property
    def templates_dir(self) -> Path:
        """Access the templates directory path."""
        return self._templates_dir

    # =========================================================================
    # BaseAgent Implementations
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that the task contains requirements and infrastructure YAML."""
        requirements_yaml = task.input_data.get("requirements_yaml")
        infra_yaml = task.input_data.get("infra_yaml")

        if not requirements_yaml:
            self._logger.warning(
                "pipeline_task_missing_requirements",
                task_id=task.task_id,
                available_keys=list(task.input_data.keys()),
            )
            return False

        if not infra_yaml:
            self._logger.warning(
                "pipeline_task_missing_infra",
                task_id=task.task_id,
                available_keys=list(task.input_data.keys()),
            )
            return False

        return True

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Generate pipeline YAML through multi-stage LLM process."""
        requirements_yaml = task.input_data["requirements_yaml"]
        infra_yaml = task.input_data["infra_yaml"]
        explicit_type = task.input_data.get("pipeline_type", "auto")

        # --- Stage 0: Parse inputs ---
        try:
            requirements = yaml.safe_load(requirements_yaml)
            if not isinstance(requirements, dict):
                raise ValueError("Requirements YAML did not parse to a dict")
        except (yaml.YAMLError, ValueError) as e:
            return self._create_result(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                output={"error": f"Invalid requirements YAML: {e}"},
                error=f"Invalid requirements YAML: {e}",
            )

        try:
            infrastructure = yaml.safe_load(infra_yaml)
            if not isinstance(infrastructure, dict):
                raise ValueError("Infrastructure YAML did not parse to a dict")
        except (yaml.YAMLError, ValueError) as e:
            return self._create_result(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                output={"error": f"Invalid infrastructure YAML: {e}"},
                error=f"Invalid infrastructure YAML: {e}",
            )

        # --- Stage 1: Detect pipeline type ---
        if explicit_type and explicit_type != "auto":
            pipeline_type = explicit_type
            type_confidence = 1.0
        else:
            pipeline_type, type_confidence = self._detect_pipeline_type(requirements)

        self._logger.info(
            "pipeline_type_detected",
            task_id=task.task_id,
            pipeline_type=pipeline_type,
            confidence=type_confidence,
        )

        # --- Stage 2: Load schema skeleton ---
        try:
            schema_skeleton = load_template_schema(pipeline_type, self._templates_dir)
        except (FileNotFoundError, KeyError) as e:
            self._logger.warning("schema_load_fallback", error=str(e))
            schema_skeleton = ""

        # --- Stage 3: LLM generation ---
        system_prompt = self._build_system_prompt(pipeline_type)
        user_prompt = self._build_user_prompt(
            requirements_yaml, infra_yaml, schema_skeleton, pipeline_type
        )

        self._logger.info(
            "pipeline_llm_call_starting",
            task_id=task.task_id,
            pipeline_type=pipeline_type,
        )

        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=self._config.llm.max_tokens,
        )

        generated_yaml = strip_markdown_fences(llm_response.content)
        stages = 1
        total_usage = llm_response.usage.model_dump()

        self._logger.info(
            "pipeline_llm_response_received",
            task_id=task.task_id,
            response_length=len(generated_yaml),
            model=llm_response.model,
        )

        # --- Stage 4: Validate ---
        validation = validate_pipeline_yaml(generated_yaml, pipeline_type)

        # --- Stage 5: Repair if needed ---
        if not validation["valid"] and validation["parsed_data"] is not None:
            # Parseable but missing sections — attempt repair
            self._logger.info(
                "pipeline_repair_attempt",
                task_id=task.task_id,
                missing_sections=validation["sections_missing"],
            )

            repair_prompt = (
                f"The following pipeline YAML is missing these required sections: "
                f"{validation['sections_missing']}\n\n"
                f"Here is the current YAML:\n{generated_yaml}\n\n"
                f"Here are the original requirements for context:\n{requirements_yaml}\n\n"
                f"Add the missing sections with realistic values."
            )

            repair_response = await self._llm_provider.generate_with_system(
                system_prompt=REPAIR_SYSTEM_PROMPT,
                user_prompt=repair_prompt,
                temperature=0.1,
                max_tokens=self._config.llm.max_tokens,
            )

            repaired_yaml = strip_markdown_fences(repair_response.content)
            validation = validate_pipeline_yaml(repaired_yaml, pipeline_type)
            stages = 2

            # Accumulate usage
            repair_usage = repair_response.usage.model_dump()
            total_usage = {
                "prompt_tokens": total_usage.get("prompt_tokens", 0) + repair_usage.get("prompt_tokens", 0),
                "completion_tokens": total_usage.get("completion_tokens", 0) + repair_usage.get("completion_tokens", 0),
                "total_tokens": total_usage.get("total_tokens", 0) + repair_usage.get("total_tokens", 0),
            }

            if validation["valid"]:
                generated_yaml = repaired_yaml
                self._logger.info("pipeline_repair_successful", task_id=task.task_id)
            else:
                self._logger.warning(
                    "pipeline_repair_failed",
                    task_id=task.task_id,
                    errors=validation["errors"],
                )

        # Remove parsed_data from validation result (not serializable in output)
        validation_output = {k: v for k, v in validation.items() if k != "parsed_data"}

        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "pipeline_yaml": generated_yaml,
                "pipeline_type": pipeline_type,
                "pipeline_type_confidence": type_confidence,
                "sections_generated": validation.get("sections_found", []),
                "validation_result": validation_output,
                "decisions_summary": f"Generated {pipeline_type} pipeline specification",
                "llm_model": llm_response.model,
                "llm_usage": total_usage,
                "generation_stages": stages,
            },
        )

    async def _on_start(self) -> None:
        """Validate the LLM provider during startup."""
        is_valid = await self._llm_provider.validate()
        if not is_valid:
            self._logger.warning(
                "pipeline_generator_llm_validation_failed",
                provider=self._llm_provider.provider_name,
                model=self._llm_provider.model,
            )

        self._logger.info(
            "pipeline_generator_initialized",
            provider=self._llm_provider.provider_name,
            model=self._llm_provider.model,
            templates_dir=str(self._templates_dir),
        )

    # =========================================================================
    # Pipeline Type Detection
    # =========================================================================

    @staticmethod
    def _detect_pipeline_type(requirements: dict[str, Any]) -> tuple[str, float]:
        """Detect pipeline type from requirements by scoring indicator key matches.

        Args:
            requirements: Parsed requirements YAML dict.

        Returns:
            Tuple of (pipeline_type, confidence_score).
        """
        scores: dict[str, float] = {}

        for ptype, indicators in PIPELINE_TYPE_INDICATORS.items():
            score = 0.0
            for key in indicators:
                if key in requirements:
                    score += 1.0

                    # Bonus for value matches
                    value_map = PIPELINE_TYPE_VALUES.get(ptype, {})
                    if key in value_map:
                        val = requirements[key]
                        if isinstance(val, str) and val in value_map[key]:
                            score += 0.5

            scores[ptype] = score

        if not scores or max(scores.values()) == 0:
            return "general", 0.5

        best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_type]
        total_indicators = len(PIPELINE_TYPE_INDICATORS.get(best_type, []))
        confidence = min(best_score / max(total_indicators, 1), 1.0)

        return best_type, round(confidence, 2)

    # =========================================================================
    # Prompt Building
    # =========================================================================

    @staticmethod
    def _build_system_prompt(pipeline_type: str) -> str:
        """Build system prompt with type-specific addendum."""
        addendum = TYPE_SPECIFIC_ADDENDA.get(pipeline_type, TYPE_SPECIFIC_ADDENDA["general"])
        return f"{BASE_SYSTEM_PROMPT}\n\nSPECIFIC FOCUS FOR THIS PIPELINE TYPE:\n{addendum}"

    @staticmethod
    def _build_user_prompt(
        requirements_yaml: str,
        infra_yaml: str,
        schema_skeleton: str,
        pipeline_type: str,
    ) -> str:
        """Build the user prompt from inputs."""
        parts = [
            f"Generate a complete {pipeline_type.replace('_', ' ')} specification YAML.\n",
            "## BUSINESS REQUIREMENTS\n",
            f"```yaml\n{requirements_yaml}\n```\n",
            "## AVAILABLE INFRASTRUCTURE\n",
            f"```yaml\n{infra_yaml}\n```\n",
        ]

        if schema_skeleton:
            parts.append("## EXPECTED OUTPUT SCHEMA\n")
            parts.append(
                "Fill in ALL of these sections with concrete values:\n\n"
            )
            parts.append(f"```\n{schema_skeleton}\n```\n")

        required = REQUIRED_SECTIONS.get(pipeline_type, [])
        if required:
            parts.append(
                f"\n## REQUIRED SECTIONS\n"
                f"The output MUST include at minimum these top-level sections: "
                f"{', '.join(required)}\n"
            )

        return "\n".join(parts)

    # =========================================================================
    # Context Generation
    # =========================================================================

    async def _generate_context(
        self, task: TaskDefinition, result: TaskResult
    ) -> ContextContribution:
        """Generate .context/ entries: decisions and confidence report."""
        pipeline_yaml = result.output_data.get("pipeline_yaml", "")
        pipeline_type = result.output_data.get("pipeline_type", "unknown")
        requirements_yaml = task.input_data.get("requirements_yaml", "")

        context_prompt = (
            f"You just generated a {pipeline_type.replace('_', ' ')} pipeline YAML specification.\n\n"
            f"## Original Requirements\n```yaml\n{requirements_yaml}\n```\n\n"
            f"## Generated Pipeline YAML\n```yaml\n{pipeline_yaml[:3000]}\n```\n\n"
            "Now produce the structured context report with DECISIONS and CONFIDENCE sections."
        )

        llm_response = await self._llm_provider.generate_with_system(
            system_prompt=CONTEXT_SYSTEM_PROMPT,
            user_prompt=context_prompt,
            temperature=0.3,
            max_tokens=self._config.llm.max_tokens,
        )

        parsed = self._parse_context_response(llm_response.content)
        entries: list[ContextEntry] = []

        if parsed.get("decisions"):
            entries.append(ContextEntry(
                context_file="decisions.md",
                section_heading="## Pipeline Architecture Decisions",
                content=parsed["decisions"],
                agent_id=self.agent_id,
            ))

        if parsed.get("confidence"):
            confidence_score = parsed.get("confidence_score")
            entries.append(ContextEntry(
                context_file="confidence-report.md",
                section_heading="## Pipeline Generation Confidence",
                content=parsed["confidence"],
                agent_id=self.agent_id,
                confidence=confidence_score,
            ))

        return ContextContribution(entries=entries)

    @staticmethod
    def _parse_context_response(text: str) -> dict[str, Any]:
        """Parse structured context sections from LLM response."""
        result: dict[str, Any] = {}

        section_markers = [
            ("decisions", r"###\s*DECISIONS"),
            ("confidence", r"###\s*CONFIDENCE"),
        ]

        for i, (key, pattern) in enumerate(section_markers):
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            start = match.end()
            end = len(text)
            for _, next_pattern in section_markers[i + 1:]:
                next_match = re.search(next_pattern, text[start:], re.IGNORECASE)
                if next_match:
                    end = start + next_match.start()
                    break

            content = text[start:end].strip()
            if content:
                result[key] = content

        # Extract confidence score
        if "confidence" in result:
            score_match = re.search(r"(\d{1,3})%", result["confidence"])
            if score_match:
                score_val = int(score_match.group(1))
                if 0 <= score_val <= 100:
                    result["confidence_score"] = score_val / 100.0

        return result
