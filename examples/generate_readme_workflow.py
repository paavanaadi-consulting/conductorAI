"""
README Generation Workflow Example
===================================

This example demonstrates how to use the ReadmeGeneratorAgent to generate
comprehensive README.md documentation from infrastructure and requirements
YAML specifications.

Usage:
    python examples/generate_readme_workflow.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from conductor.agents.development import ReadmeGeneratorAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType
from conductor.core.models import TaskDefinition
from conductor.facade import ConductorAI
from conductor.integrations.llm.mock import MockLLMProvider


README_MOCK_RESPONSE = """\
# Project Documentation

This project leverages modern cloud infrastructure with containerized deployments,
scalable databases, and comprehensive monitoring.

## Overview
Enterprise REST API for managing distributed microservices.

## Architecture
Microservices architecture deployed on Kubernetes.

## Setup and Installation
1. Clone repository
2. Install dependencies
3. Configure environment
4. Run migrations
5. Start server

## Usage
REST API endpoints via JWT authentication.

## Testing
Run: pytest --cov=src tests/

## Deployment
Docker with Kubernetes orchestration.

## Monitoring
Prometheus, Grafana, Filebeat, Jaeger.

## Troubleshooting
Common issues documented.
"""


async def main() -> None:
    """Run README generation workflow."""
    print("\n" + "=" * 80)
    print("README Generation Workflow Example")
    print("=" * 80 + "\n")

    config = ConductorConfig()
    mock_llm = MockLLMProvider()
    mock_llm.queue_response(README_MOCK_RESPONSE)

    conductor = ConductorAI(config=config)
    await conductor.start()

    print("✓ ConductorAI initialized\n")

    readme_agent = ReadmeGeneratorAgent(
        "readme-01",
        config=config,
        llm_provider=mock_llm,
    )
    await conductor.register_agent(readme_agent)
    print("✓ ReadmeGeneratorAgent registered\n")

    infra_yaml = """\
registry_version: "1.0"
organization: "Example Corp"
compute:
  kubernetes:
    clusters: ["eks-prod"]
storage:
  rds:
    engines: ["postgres15"]
monitoring:
  metrics: "prometheus"
"""

    requirements_yaml = """\
project_name: "enterprise-api"
team: "Platform Engineering"
priority: "high"
description: Enterprise REST API
performance:
  availability: "99.95%"
"""

    print("✓ Sample YAML files loaded\n")

    task = TaskDefinition(
        name="Generate Comprehensive README",
        assigned_to=AgentType.CODING,
        input_data={
            "infra_yaml": infra_yaml,
            "requirements_yaml": requirements_yaml,
            "project_name": "Enterprise API",
            "include_sections": [
                "overview",
                "architecture",
                "setup",
                "usage",
                "testing",
                "deployment",
                "monitoring",
            ],
        },
    )

    print(f"✓ Task created: {task.name}\n")
    print("Generating README...\n")

    try:
        result = await conductor.dispatch_task(task)
        print(f"✓ Task completed: {result.status.value}\n")

        readme_content = result.output_data.get("readme_md", "")
        sections = result.output_data.get("sections_generated", [])

        print(f"Generated Sections: {', '.join(sections)}\n")
        print("=" * 80)
        print("GENERATED README")
        print("=" * 80)
        print(readme_content)
        print("=" * 80 + "\n")

        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)
        readme_path = output_dir / "README.md"
        readme_path.write_text(readme_content)
        print(f"✓ README saved to: {readme_path}\n")

    except Exception as e:
        print(f"✗ Task failed: {e}\n")
        raise

    await conductor.stop()
    print("\n✓ Workflow completed successfully!\n")


if __name__ == "__main__":
    asyncio.run(main())

