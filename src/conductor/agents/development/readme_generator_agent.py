"""
conductor.agents.development.readme_generator_agent - README Generation Agent
==============================================================================

This module implements the ReadmeGeneratorAgent — a specialized agent that
generates comprehensive README.md files with a focus on PROJECT REQUIREMENTS,
ARCHITECTURE, and WORKFLOWS (not tutorials or setup instructions).

Architecture Context:
    The ReadmeGeneratorAgent is part of the DEVELOPMENT phase. It generates
    requirements-focused project documentation based on infrastructure and
    requirements YAML specifications.

    ┌───────────────────┐    TaskDefinition     ┌─────────────────────────┐
    │ AgentCoordinator  │ ──────────────────→   │ ReadmeGeneratorAgent    │
    │                   │                       │                         │
    │                   │ ←── TaskResult ────── │  ┌─────────────────┐   │
    └───────────────────┘                       │  │  LLMProvider    │   │
                                                │  │  YAML Parser    │   │
                                                │  └─────────────────┘   │
                                                └─────────────────────────┘

    Input (task.input_data):
        {
            "infra_yaml": "...",                # Infrastructure YAML content
            "requirements_yaml": "...",         # Requirements YAML content
            "project_name": "my-project",       # Optional project name
            "include_sections": [               # Optional, defaults to all
                "project_overview", "business_requirements",
                "technical_requirements", "use_cases", "system_workflow",
                "data_architecture", "integration_points", "api_endpoints",
                "security_systems", "success_criteria"
            ],
            "style": "professional"             # Optional: minimal | standard | professional
        }

    Output (result.output_data):
        {
            "readme_md": "...",                 # The generated README.md content
            "sections_generated": [...],        # List of sections included
            "project_metadata": {...},          # Extracted metadata
            "document_length": 3500,            # Character count
            "table_of_contents": "...",         # Generated TOC
            "infra_summary": "...",             # Infrastructure summary
            "requirements_summary": "...",      # Requirements summary
        }

Documentation Content Generated:
    The README focuses on:
    1. Project Overview - Business context and stakeholders
    2. Business Requirements - Goals, KPIs, constraints
    3. Technical Requirements - Performance, scalability, technology stack
    4. Use Cases - User personas, workflows, business value
    5. System Workflow - Architecture, data flows, integrations
    6. Data Architecture - Data sources, models, quality
    7. Integration Points - External systems, dependencies
    8. API Endpoints - REST/GraphQL endpoints, schemas, authentication
    9. Security Systems - Authentication, encryption, compliance, audit logging
    10. Success Criteria - Metrics, targets, acceptance criteria

    NOT INCLUDED (unlike typical README files):
    - Setup and installation instructions
    - Code examples or tutorials
    - Troubleshooting guides
    - Developer guides or API documentation

Usage:
    >>> from conductor.agents.development import ReadmeGeneratorAgent
    >>> from conductor.core.config import ConductorConfig
    >>> from conductor.integrations.llm import MockLLMProvider
    >>>
    >>> config = ConductorConfig()
    >>> provider = MockLLMProvider()
    >>> agent = ReadmeGeneratorAgent("readme-01", config, llm_provider=provider)
    >>> await agent.start()
    >>>
    >>> task = TaskDefinition(
    ...     name="Generate Requirements README",
    ...     assigned_to=AgentType.CODING,
    ...     input_data={
    ...         "infra_yaml": infra_content,
    ...         "requirements_yaml": requirements_content,
    ...         "project_name": "my-project",
    ...     },
    ... )
    >>> result = await agent.execute_task(task)
    >>> print(result.output_data["readme_md"])
"""

from __future__ import annotations

from typing import Any

import structlog
import yaml

from conductor.agents.base import BaseAgent
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
# System Prompt Template - Requirements & Workflow Focused
# =============================================================================
README_SYSTEM_PROMPT = """You are a technical requirements and architecture specialist.
Your role is to generate comprehensive project documentation that focuses on
business and technical requirements, use cases, and system workflows.

Guidelines:
- Focus on WHAT the project does and WHY, not HOW to use it
- Document business requirements and technical constraints
- Describe real-world use cases and user scenarios
- Explain system workflows, data flows, and integration points
- Include requirement matrices and success criteria
- Document stakeholders, priorities, and deadlines
- Use clear requirements language and structured formats
- Avoid tutorial content, setup instructions, or code examples

Output Format:
Generate ONLY the markdown content in valid format.
Do NOT include any explanations, metadata, or comments outside the markdown."""


# =============================================================================
# Default Sections - Requirements & Workflow Focused
# =============================================================================
DEFAULT_SECTIONS = [
    "project_overview",
    "business_requirements",
    "technical_requirements",
    "use_cases",
    "system_workflow",
    "data_architecture",
    "integration_points",
    "api_endpoints",
    "security_systems",
    "success_criteria",
]

SECTION_TEMPLATES = {
    "project_overview": "## Project Overview\n\n{content}\n",
    "business_requirements": "## Business Requirements\n\n{content}\n",
    "technical_requirements": "## Technical Requirements\n\n{content}\n",
    "use_cases": "## Use Cases & User Scenarios\n\n{content}\n",
    "system_workflow": "## System Workflow & Architecture\n\n{content}\n",
    "data_architecture": "## Data Architecture\n\n{content}\n",
    "integration_points": "## Integration Points & Dependencies\n\n{content}\n",
    "api_endpoints": "## API Endpoints & Contracts\n\n{content}\n",
    "security_systems": "## Security Systems & Methodologies\n\n{content}\n",
    "success_criteria": "## Success Criteria & Metrics\n\n{content}\n",
    "compliance_requirements": "## Compliance & Governance\n\n{content}\n",
}


class ReadmeGeneratorAgent(BaseAgent):
    """Agent for generating comprehensive README.md documentation.

    The ReadmeGeneratorAgent takes infrastructure and requirements specifications
    in YAML format and generates professional README.md documentation that
    describes the project, architecture, setup, usage, deployment, and more.

    Attributes:
        _llm_provider: LLM provider for generating content.
    """

    def __init__(
        self,
        agent_id: str,
        config: ConductorConfig,
        llm_provider: BaseLLMProvider,
    ) -> None:
        """Initialize the README Generator Agent.

        Args:
            agent_id: Unique identifier for this agent instance.
            config: ConductorAI configuration.
            llm_provider: LLM provider for generating content.
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.README_FILE_GENERATOR,
            config=config,
            name="README Generator Agent",
            description="Generates comprehensive README.md from specs",
        )
        self._llm_provider = llm_provider
        self._logger = logger.bind(component="readme_generator_agent")

    # =========================================================================
    # Task Validation
    # =========================================================================

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Validate that this task is appropriate for README generation.

        Args:
            task: The task to validate.

        Returns:
            True if the task contains required input data.
        """
        required_fields = ["infra_yaml", "requirements_yaml"]
        return all(field in task.input_data for field in required_fields)

    # =========================================================================
    # Task Execution
    # =========================================================================

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Generate README.md from infrastructure and requirements YAML.

        Args:
            task: The task containing infra_yaml and requirements_yaml.

        Returns:
            TaskResult with the generated README content.
        """
        self._logger.info("readme_generation_started", task_id=task.task_id)

        try:
            # Extract input data
            infra_yaml = task.input_data.get("infra_yaml", "")
            requirements_yaml = task.input_data.get("requirements_yaml", "")
            project_name = task.input_data.get("project_name", "Project")
            include_sections = task.input_data.get(
                "include_sections",
                DEFAULT_SECTIONS,
            )
            style = task.input_data.get("style", "professional")

            # Parse YAML content
            infra_data = self._parse_yaml(infra_yaml)
            requirements_data = self._parse_yaml(requirements_yaml)

            self._logger.debug(
                "yaml_parsed",
                infra_keys=list(infra_data.keys()) if infra_data else [],
                req_keys=list(requirements_data.keys()) if requirements_data else [],
            )

            # Extract metadata
            project_metadata = self._extract_metadata(
                infra_data,
                requirements_data,
                project_name,
            )

            # Generate section content via LLM
            sections_content = await self._generate_sections(
                infra_data,
                project_metadata,
                include_sections,
                style,
            )

            # Assemble README
            readme_md = self._assemble_readme(
                project_name,
                sections_content,
                include_sections,
            )

            # Extract table of contents
            table_of_contents = self._extract_toc(readme_md)

            self._logger.info(
                "readme_generation_completed",
                task_id=task.task_id,
                content_length=len(readme_md),
                sections_count=len(sections_content),
            )

            return self._create_result(
                task.task_id,
                TaskStatus.COMPLETED,
                {
                    "readme_md": readme_md,
                    "sections_generated": list(sections_content.keys()),
                    "project_metadata": project_metadata,
                    "document_length": len(readme_md),
                    "table_of_contents": table_of_contents,
                    "infra_summary": self._summarize_infra(infra_data),
                    "requirements_summary": self._summarize_requirements(
                        requirements_data,
                    ),
                },
            )

        except Exception as e:
            self._logger.error(
                "readme_generation_failed",
                task_id=task.task_id,
                error=str(e),
            )
            raise

    # =========================================================================
    # YAML Parsing
    # =========================================================================

    def _parse_yaml(self, yaml_content: str) -> dict[str, Any]:
        """Parse YAML content string to dictionary.

        Args:
            yaml_content: YAML string to parse.

        Returns:
            Parsed YAML as dictionary, or empty dict if parsing fails.
        """
        if not yaml_content or not isinstance(yaml_content, str):
            return {}

        try:
            data = yaml.safe_load(yaml_content)
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError as e:
            self._logger.warning("yaml_parse_failed", error=str(e))
            return {}

    # =========================================================================
    # Pipeline Type Detection
    # =========================================================================

    def _detect_pipeline_type(self, requirements_data: dict[str, Any]) -> str:
        """Detect which requirements template was used based on discriminating keys."""
        keys = set(requirements_data.keys())
        if {"sources", "destination", "pipeline_type", "quality_requirements"}.issubset(keys):
            return "data-pipeline"
        if {"problem_type", "ml_type", "training_data", "model_requirements"}.issubset(keys):
            return "ml-pipeline"
        if {"project_type", "knowledge_sources"}.issubset(keys):
            return "rag-llm"
        if {"agent_architecture", "agents", "autonomy_rules"}.issubset(keys):
            return "agentic-ops"
        if {"integration_type", "existing_systems"}.issubset(keys):
            return "integration"
        return "general"

    def _extract_pipeline_specific(
        self, pipeline_type: str, requirements_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract type-specific fields from requirements based on detected pipeline type."""
        if pipeline_type == "data-pipeline":
            return {
                "pipeline_type": requirements_data.get("pipeline_type", ""),
                "architecture": requirements_data.get("architecture", ""),
                "sources": requirements_data.get("sources", []),
                "destination": requirements_data.get("destination", {}),
                "quality_requirements": requirements_data.get("quality_requirements", {}),
                "schedule": requirements_data.get("schedule", {}),
                "consumers": requirements_data.get("consumers", []),
            }
        if pipeline_type == "ml-pipeline":
            return {
                "problem_type": requirements_data.get("problem_type", ""),
                "ml_type": requirements_data.get("ml_type", ""),
                "deployment": requirements_data.get("deployment", ""),
                "business_impact": requirements_data.get("business_impact", {}),
                "training_data": requirements_data.get("training_data", {}),
                "features": requirements_data.get("features", {}),
                "model_requirements": requirements_data.get("model_requirements", {}),
                "inference": requirements_data.get("inference", {}),
                "retraining": requirements_data.get("retraining", {}),
            }
        if pipeline_type == "rag-llm":
            return {
                "project_type": requirements_data.get("project_type", ""),
                "use_case": requirements_data.get("use_case", ""),
                "knowledge_sources": requirements_data.get("knowledge_sources", []),
                "users": requirements_data.get("users", {}),
                "quality": requirements_data.get("quality", {}),
                "budget": requirements_data.get("budget", {}),
            }
        if pipeline_type == "agentic-ops":
            return {
                "agent_architecture": requirements_data.get("agent_architecture", ""),
                "orchestration": requirements_data.get("orchestration", ""),
                "domain": requirements_data.get("domain", ""),
                "agents": requirements_data.get("agents", []),
                "autonomy_rules": requirements_data.get("autonomy_rules", {}),
                "integrations": requirements_data.get("integrations", []),
                "llm_config": requirements_data.get("llm_config", {}),
                "safety": requirements_data.get("safety", {}),
            }
        if pipeline_type == "integration":
            return {
                "integration_type": requirements_data.get("integration_type", ""),
                "scope": requirements_data.get("scope", ""),
                "existing_systems": requirements_data.get("existing_systems", []),
                "target": requirements_data.get("target", {}),
                "strategy": requirements_data.get("strategy", {}),
                "constraints": requirements_data.get("constraints", {}),
            }
        # general
        return {
            "domain": requirements_data.get("domain", ""),
            "features": requirements_data.get("features", []),
            "users": requirements_data.get("users", {}),
            "performance": requirements_data.get("performance", {}),
            "integrations": requirements_data.get("integrations", []),
        }

    # =========================================================================
    # Metadata Extraction
    # =========================================================================

    def _extract_metadata(
        self,
        infra_data: dict[str, Any],
        requirements_data: dict[str, Any],
        project_name: str,
    ) -> dict[str, Any]:
        """Extract key metadata from infrastructure and requirements data.

        Args:
            infra_data: Parsed infrastructure YAML.
            requirements_data: Parsed requirements YAML.
            project_name: Project name.

        Returns:
            Dictionary with extracted metadata.
        """
        pipeline_type = self._detect_pipeline_type(requirements_data)

        # For integration infra, compute/storage/monitoring may live under a 'target' key
        infra_compute = infra_data.get("compute") or infra_data.get("target", {}).get("compute", {})
        infra_storage = infra_data.get("storage") or infra_data.get("target", {}).get("storage", {})
        infra_monitoring = infra_data.get("monitoring") or infra_data.get("target", {}).get("monitoring", {})
        infra_orchestration = (infra_data.get("orchestration") or
                               infra_data.get("target", {}).get("orchestration", {}))

        compliance = requirements_data.get("compliance", {})

        return {
            "detected_pipeline_type": pipeline_type,
            "project_name": requirements_data.get("project_name", project_name) or project_name,
            "organization": infra_data.get("organization", ""),
            "team": requirements_data.get("team", ""),
            "contact_email": requirements_data.get("contact_email", ""),
            "priority": requirements_data.get("priority", "high"),
            "target_date": requirements_data.get("target_date", ""),
            "description": requirements_data.get("description", ""),
            "notes": requirements_data.get("notes", ""),
            "success_criteria": requirements_data.get("success_criteria", []),
            "compliance_regulations": compliance.get("regulations", []) if isinstance(compliance, dict) else [],
            "preferences": requirements_data.get("preferences", {}),
            "compute_platforms": list(infra_compute.keys()) if isinstance(infra_compute, dict) else [],
            "storage_systems": list(infra_storage.keys()) if isinstance(infra_storage, dict) else [],
            "monitoring_tools": list(infra_monitoring.keys()) if isinstance(infra_monitoring, dict) else [],
            "orchestration_tools": list(infra_orchestration.keys()) if isinstance(infra_orchestration, dict) else [],
            "ci_cd_provider": infra_data.get("ci_cd", {}).get("provider", ""),
            "constraints": infra_data.get("constraints", {}),
            "pipeline_specific": self._extract_pipeline_specific(pipeline_type, requirements_data),
        }

    # =========================================================================
    # LLM Content Generation
    # =========================================================================

    async def _generate_sections(
        self,
        infra_data: dict[str, Any],
        metadata: dict[str, Any],
        sections_to_generate: list[str],
        style: str,
    ) -> dict[str, str]:
        """Generate README sections using LLM.

        Args:
            infra_data: Parsed infrastructure data.
            metadata: Extracted metadata (includes pipeline_specific and constraints).
            sections_to_generate: List of section names to generate.
            style: Documentation style preference.

        Returns:
            Dictionary mapping section names to generated content.
        """
        sections = {}

        success_criteria = metadata.get("success_criteria", [])
        success_criteria_text = (
            "\n".join(f"- {c}" for c in success_criteria if c)
            if success_criteria
            else "Not specified"
        )
        compliance_regs = metadata.get("compliance_regulations", [])
        preferences = metadata.get("preferences", {})
        pipeline_specific_text = yaml.dump(
            metadata.get("pipeline_specific", {}), default_flow_style=False
        )
        constraints_text = yaml.dump(
            metadata.get("constraints", {}), default_flow_style=False
        )

        # Build context for LLM
        context = f"""
Project Information:
- Name: {metadata.get('project_name')}
- Organization: {metadata.get('organization')}
- Team: {metadata.get('team')}
- Contact Email: {metadata.get('contact_email')}
- Description: {metadata.get('description')}
- Priority: {metadata.get('priority')}
- Target Date: {metadata.get('target_date')}
- Pipeline Type: {metadata.get('detected_pipeline_type')}

Success Criteria:
{success_criteria_text}

Compliance Regulations: {', '.join(compliance_regs) if compliance_regs else 'None specified'}
Technology Preferences: {yaml.dump(preferences, default_flow_style=True).strip() if preferences else 'Not specified'}

Infrastructure Capabilities:
- Compute Platforms: {', '.join(metadata.get('compute_platforms', []))}
- Storage Systems: {', '.join(metadata.get('storage_systems', []))}
- Monitoring Tools: {', '.join(metadata.get('monitoring_tools', []))}
- Orchestration Tools: {', '.join(metadata.get('orchestration_tools', []))}
- CI/CD Provider: {metadata.get('ci_cd_provider')}

Infrastructure Constraints:
{constraints_text}

Pipeline-Specific Requirements:
{pipeline_specific_text}

Infrastructure Details:
{yaml.dump(infra_data, default_flow_style=False)}

Documentation Style: {style}
"""

        # Generate each section with requirements-focused prompts
        section_prompts = {
            "project_overview": """Provide a high-level project overview including:
- Project name and organization
- Business drivers and strategic importance
- Key stakeholders and decision-makers
- Timeline and priority level
- Success vision statement""",
            "business_requirements": """Document the business requirements including:
- Primary business objectives and goals
- Key success metrics and KPIs
- Stakeholder needs and expectations
- Budget and resource constraints
- Timeline and delivery milestones
- Regulatory and compliance requirements""",
            "technical_requirements": """List technical requirements including:
- System performance requirements (throughput, latency, availability)
- Scalability and growth projections
- Technology stack constraints and preferences
- Integration requirements with existing systems
- Data requirements and volumes
- Security and compliance requirements
- Infrastructure and deployment constraints""",
            "use_cases": """Define user scenarios and use cases including:
- Primary user personas and roles
- Main workflows and user journeys
- Business value for each use case
- Priority ranking of use cases
- Data inputs and expected outputs
- User interactions and decision points""",
            "system_workflow": """Describe the system architecture and workflows:
- High-level system components and their interactions
- Data flow diagrams (in text/markdown format)
- Processing workflows and pipelines
- System dependencies and integrations
- User workflows and touchpoints
- Error handling and exception flows""",
            "data_architecture": """Detail the data architecture including:
- Data sources and data ownership
- Data models and schemas
- Data flow from source to destination
- Data quality requirements
- Data retention and lifecycle policies
- Privacy and data protection requirements""",
            "integration_points": """Document integration requirements:
- External systems that need integration
- Integration patterns and protocols
- APIs and data exchange formats
- Third-party services and dependencies
- Synchronization requirements
- Error recovery and fallback mechanisms""",
            "api_endpoints": """Document API endpoints and contracts including:
- REST/GraphQL/gRPC endpoint definitions (if applicable)
- HTTP methods and paths for each endpoint
- Request and response schemas/examples
- Authentication and authorization requirements
- Rate limiting and quota policies
- Error responses and status codes
- Versioning strategy
- Webhook/event subscriptions (if applicable)
- API documentation links or OpenAPI/Swagger specs""",
            "security_systems": """Detail security systems and methodologies including:
- Authentication mechanisms (OAuth2, JWT, SAML, etc.)
- Authorization and access control models (RBAC, ABAC, etc.)
- Encryption standards (TLS, AES, etc.)
- Data protection and privacy measures
- Secrets management and credential handling
- Security compliance frameworks (SOC 2, ISO 27001, etc.)
- Vulnerability scanning and patch management
- DDoS protection and rate limiting strategies
- Audit logging and monitoring
- Security testing and penetration testing plans""",
            "success_criteria": """Define success metrics and criteria:
- Quantifiable success metrics
- Performance baselines and targets
- User adoption targets
- Business value realization milestones
- Quality acceptance criteria
- Risk mitigation targets""",
            "compliance_requirements": """Document compliance and governance:
- Regulatory requirements
- Industry standards and certifications needed
- Data protection and privacy regulations
- Audit and monitoring requirements
- Governance policies and approval processes
- Change management requirements""",
        }

        # Generate each section
        for section in sections_to_generate:
            if section not in SECTION_TEMPLATES:
                continue

            section_specific_prompt = section_prompts.get(
                section,
                f"Generate a detailed {section} section."
            )

            user_prompt = f"""Generate a {section} section for the project documentation.

Project Context:
{context}

Requirements for this section:
{section_specific_prompt}

Guidelines:
- Use markdown formatting with clear structure
- Focus on requirements and specifications, NOT tutorials or setup instructions
- Use tables for requirement matrices where appropriate
- Be comprehensive but well-organized
- Use bullet points and numbered lists for clarity
- Match the {style} style

Generate ONLY the section content without the heading."""

            try:
                llm_response = await self._llm_provider.generate_with_system(
                    system_prompt=README_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    context_entries=[
                        ContextEntry(
                            context_file="project_requirements.md",
                            section_heading=f"## {section.replace('_', ' ').upper()}",
                            content=context,
                            agent_id=self.agent_id,
                        ),
                    ],
                )
                sections[section] = llm_response.content.strip()
                self._logger.debug(
                    "section_generated",
                    section=section,
                    content_length=len(llm_response.content),
                )
            except Exception as e:
                self._logger.warning(
                    "section_generation_failed",
                    section=section,
                    error=str(e),
                )
                sections[section] = f"*{section.replace('_', ' ').capitalize()} details to be added*"

        return sections

    # =========================================================================
    # README Assembly
    # =========================================================================

    def _assemble_readme(
        self,
        project_name: str,
        sections: dict[str, str],
        section_order: list[str],
    ) -> str:
        """Assemble README from individual sections.

        Args:
            project_name: Project name for title.
            sections: Dictionary of section content.
            section_order: Order to arrange sections.

        Returns:
            Complete README.md content.
        """
        parts = [
            f"# {project_name}\n\n",
            "*Auto-generated by ConductorAI ReadmeGeneratorAgent*\n",
            "*Last Updated: {timestamp}*\n\n".format(
                timestamp=__import__('datetime').datetime.now().isoformat()
            ),
        ]

        # Add table of contents
        toc = "## Table of Contents\n\n"
        for section in section_order:
            if section in sections:
                section_title = section.replace('_', ' ').title()
                anchor = section.lower().replace(' ', '-')
                toc += f"- [{section_title}](#{anchor})\n"
        parts.append(toc + "\n")

        # Add sections
        for section in section_order:
            if section in sections:
                section_title = section.replace('_', ' ').title()
                heading = f"## {section_title}\n\n"
                parts.append(heading + sections[section] + "\n\n")

        # Add footer with metadata
        parts.append(
            "\n---\n\n"
            "## Document Information\n\n"
            "- **Generated By**: ConductorAI ReadmeGeneratorAgent\n"
            "- **Purpose**: Project Requirements and Architecture Documentation\n"
            "- **Document Type**: Requirements Specification\n\n"
            "*For questions or updates regarding project requirements, "
            "contact the project team.*\n"
        )

        return "".join(parts)

    # =========================================================================
    # Utilities
    # =========================================================================

    def _extract_toc(self, readme: str) -> str:
        """Extract table of contents from README.

        Args:
            readme: Complete README content.

        Returns:
            Extracted table of contents.
        """
        lines = readme.split("\n")
        toc_lines = []
        in_toc = False

        for line in lines:
            if line.startswith("## Table of Contents"):
                in_toc = True
                continue
            if in_toc and line.startswith("## ") and "Table of Contents" not in line:
                break
            if in_toc and line.strip().startswith("-"):
                toc_lines.append(line)

        return "\n".join(toc_lines)

    def _summarize_infra(self, infra_data: dict[str, Any]) -> str:
        """Create a text summary of infrastructure capabilities.

        Args:
            infra_data: Parsed infrastructure data.

        Returns:
            Human-readable infrastructure summary.
        """
        if not infra_data:
            return "No infrastructure data provided."

        summary = []
        for category, details in infra_data.items():
            if isinstance(details, dict):
                services = list(details.keys())
                summary.append(f"**{category.title()}**: {', '.join(services)}")
            elif isinstance(details, list):
                summary.append(f"**{category.title()}**: {', '.join(details)}")

        return "\n".join(summary)

    def _summarize_requirements(
        self,
        requirements_data: dict[str, Any],
    ) -> str:
        """Create a text summary of project requirements.

        Args:
            requirements_data: Parsed requirements data.

        Returns:
            Human-readable requirements summary.
        """
        if not requirements_data:
            return "No requirements data provided."

        summary = []

        # Project basics
        if "project_name" in requirements_data:
            summary.append(f"**Project**: {requirements_data['project_name']}")
        if "description" in requirements_data:
            desc = requirements_data["description"]
            if isinstance(desc, str) and len(desc) > 200:
                desc = desc[:200] + "..."
            summary.append(f"**Description**: {desc}")

        # Scope
        if "features" in requirements_data:
            features = requirements_data["features"]
            if isinstance(features, list):
                summary.append(f"**Features**: {len(features)} defined")

        # Performance
        if "performance" in requirements_data:
            perf = requirements_data["performance"]
            if isinstance(perf, dict):
                if "availability" in perf:
                    summary.append(f"**Availability Target**: {perf['availability']}")

        return "\n".join(summary)

