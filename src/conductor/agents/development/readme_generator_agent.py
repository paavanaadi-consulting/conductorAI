"""
conductor.agents.development.readme_generator_agent - README Generation Agent
==============================================================================

This module implements the ReadmeGeneratorAgent — a specialized agent that
generates comprehensive README.md files from infrastructure and requirements
YAML specifications.

Architecture Context:
    The ReadmeGeneratorAgent is part of the DEVELOPMENT phase. It generates
    project documentation based on infrastructure and requirements definitions.

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
                "overview", "architecture", "setup", "usage", "testing", 
                "deployment", "monitoring", "troubleshooting"
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

How README Generation Works:
    1. ReadmeGeneratorAgent receives task with infra_yaml and requirements_yaml.
    2. It parses both YAML files to extract metadata.
    3. It constructs a structured prompt with the parsed data.
    4. It calls the LLM to generate README sections.
    5. It assembles sections into a complete README.md.
    6. It validates and formats the output.

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
    ...     name="Generate README",
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
# System Prompt Template
# =============================================================================
README_SYSTEM_PROMPT = """You are an expert technical writer specializing in software 
project documentation. Your role is to generate clear, comprehensive README.md files 
that guide developers and users through project setup, usage, and deployment.

Guidelines:
- Create well-structured, easy-to-navigate documentation
- Include practical examples and clear instructions
- Follow markdown best practices with proper formatting
- Organize content with clear table of contents
- Use code blocks with proper language syntax highlighting
- Include architecture diagrams described in text format
- Provide troubleshooting and FAQ sections where relevant
- Make content accessible to both beginners and experienced developers

Output Format:
Generate ONLY the README.md content in valid markdown format. 
Do NOT include any explanations, metadata, or comments outside the markdown."""


# =============================================================================
# Default Sections
# =============================================================================
DEFAULT_SECTIONS = [
    "overview",
    "architecture",
    "setup",
    "usage",
    "testing",
    "deployment",
    "monitoring",
    "troubleshooting",
]

SECTION_TEMPLATES = {
    "overview": "## Overview\n\n{content}\n",
    "architecture": "## Architecture\n\n{content}\n",
    "setup": "## Setup and Installation\n\n{content}\n",
    "usage": "## Usage\n\n{content}\n",
    "testing": "## Testing\n\n{content}\n",
    "deployment": "## Deployment\n\n{content}\n",
    "monitoring": "## Monitoring and Observability\n\n{content}\n",
    "troubleshooting": "## Troubleshooting\n\n{content}\n",
    "contributing": "## Contributing\n\n{content}\n",
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
                requirements_data,
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
        return {
            "project_name": project_name,
            "organization": requirements_data.get("organization", ""),
            "team": requirements_data.get("team", ""),
            "contact_email": requirements_data.get("contact_email", ""),
            "priority": requirements_data.get("priority", "high"),
            "target_date": requirements_data.get("target_date", ""),
            "description": requirements_data.get("description", ""),
            "domain": requirements_data.get("domain", ""),
            "compute_platforms": list(infra_data.get("compute", {}).keys()),
            "storage_systems": list(infra_data.get("storage", {}).keys()),
            "monitoring_tools": list(infra_data.get("monitoring", {}).keys()),
            "ci_cd_provider": infra_data.get("ci_cd", {}).get("provider", ""),
        }

    # =========================================================================
    # LLM Content Generation
    # =========================================================================

    async def _generate_sections(
        self,
        infra_data: dict[str, Any],
        requirements_data: dict[str, Any],
        metadata: dict[str, Any],
        sections_to_generate: list[str],
        style: str,
    ) -> dict[str, str]:
        """Generate README sections using LLM.

        Args:
            infra_data: Parsed infrastructure data.
            requirements_data: Parsed requirements data.
            metadata: Extracted metadata.
            sections_to_generate: List of section names to generate.
            style: Documentation style preference.

        Returns:
            Dictionary mapping section names to generated content.
        """
        sections = {}

        # Build context for LLM
        context = f"""
Project Information:
- Name: {metadata.get('project_name')}
- Organization: {metadata.get('organization')}
- Team: {metadata.get('team')}
- Description: {metadata.get('description')}
- Priority: {metadata.get('priority')}
- Domain: {metadata.get('domain')}

Infrastructure Capabilities:
- Compute Platforms: {', '.join(metadata.get('compute_platforms', []))}
- Storage Systems: {', '.join(metadata.get('storage_systems', []))}
- Monitoring Tools: {', '.join(metadata.get('monitoring_tools', []))}
- CI/CD Provider: {metadata.get('ci_cd_provider')}

Infrastructure Details:
{yaml.dump(infra_data, default_flow_style=False)}

Requirements:
{yaml.dump(requirements_data, default_flow_style=False)}

Documentation Style: {style}
"""

        # Generate each section
        for section in sections_to_generate:
            if section not in SECTION_TEMPLATES:
                continue

            user_prompt = f"""Generate a {section} section for the README.md file 
for this project. Use the context provided above.

Requirements:
- Use markdown formatting
- Include practical examples where applicable
- Make it comprehensive but concise
- Match the {style} style

Section Name: {section.upper()}

Generate ONLY the section content without the heading."""

            try:
                content = await self._llm_provider.generate_with_system(
                    system_prompt=README_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    context_entries=[
                        ContextEntry(
                            key="project_context",
                            value=context,
                            source="metadata_extractor",
                        ),
                    ],
                )
                sections[section] = content.strip()
                self._logger.debug(
                    "section_generated",
                    section=section,
                    content_length=len(content),
                )
            except Exception as e:
                self._logger.warning(
                    "section_generation_failed",
                    section=section,
                    error=str(e),
                )
                sections[section] = f"*{section.capitalize()} section coming soon...*"

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
            f"# {project_name}\n",
            "*Auto-generated by ConductorAI ReadmeGeneratorAgent*\n\n",
        ]

        # Add table of contents
        toc = "## Table of Contents\n\n"
        for section in section_order:
            if section in sections:
                toc += f"- [{section.capitalize()}](#{section})\n"
        parts.append(toc + "\n")

        # Add sections
        for section in section_order:
            if section in sections:
                heading = f"## {section.replace('_', ' ').title()}\n\n"
                parts.append(heading + sections[section] + "\n\n")

        # Add footer
        parts.append(
            "\n---\n\n"
            "*This README was generated by ConductorAI. "
            "For questions or updates, contact the project team.*\n"
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

