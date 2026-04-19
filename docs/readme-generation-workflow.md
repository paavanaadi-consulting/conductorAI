"""
Documentation: README Generation Workflow in ConductorAI
=========================================================

This document explains how to use ConductorAI's ReadmeGeneratorAgent to
automatically generate professional README.md documentation from infrastructure
and requirements specifications.

Author: ConductorAI
Date: 2024
"""

# =============================================================================
# Overview
# =============================================================================

The README Generation workflow demonstrates ConductorAI's ability to
generate structured documentation from structured specifications.

Key Components:
  1. ReadmeGeneratorAgent - Generates README.md from YAML specs
  2. Workflow Engine - Orchestrates the generation task
  3. LLM Provider - Powers content generation (Anthropic, OpenAI, Mock)
  4. Infrastructure & Requirements YAML - Input specifications

# =============================================================================
# Architecture
# =============================================================================

The workflow follows the standard ConductorAI agent lifecycle:

┌─────────────────────────────────────────────────────────────────────┐
│                    ConductorAI Orchestration                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  WorkflowEngine                                                     │
│      ↓                                                              │
│  AgentCoordinator - routes task to ReadmeGeneratorAgent            │
│      ↓                                                              │
│  ReadmeGeneratorAgent                                              │
│      ├─ Parse YAML specifications                                 │
│      ├─ Extract metadata and structure                            │
│      ├─ Call LLM for each section                                 │
│      ├─ Assemble README.md                                        │
│      └─ Return TaskResult with generated content                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

Data Flow:

    Input (YAML files)
         ↓
    [infra_yaml, requirements_yaml, project_name, style]
         ↓
    ReadmeGeneratorAgent
         ├─ Parse both YAML files to dict
         ├─ Extract key metadata
         ├─ For each section:
         │  ├─ Build LLM prompt with context
         │  ├─ Call LLM
         │  └─ Collect generated content
         └─ Assemble sections into README.md
              ↓
         Output (TaskResult)
              ↓
    [readme_md, sections_generated, project_metadata, ...]

# =============================================================================
# Input Specification
# =============================================================================

The ReadmeGeneratorAgent accepts the following input_data:

{
    "infra_yaml": str,              # Required: Infrastructure YAML content
    "requirements_yaml": str,       # Required: Requirements YAML content
    "project_name": str,            # Optional: Project name for title
    "include_sections": [str],      # Optional: Sections to generate
    "style": str,                   # Optional: "minimal" | "standard" | "professional"
}

Example:

```python
task = TaskDefinition(
    name="Generate README",
    assigned_to=AgentType.CODING,
    input_data={
        "infra_yaml": infra_content,
        "requirements_yaml": requirements_content,
        "project_name": "My Awesome API",
        "include_sections": [
            "overview",
            "architecture",
            "setup",
            "usage",
            "testing",
            "deployment",
            "monitoring",
            "troubleshooting",
        ],
        "style": "professional",
    },
)
```

# =============================================================================
# Output Specification
# =============================================================================

The agent returns a TaskResult with the following output_data:

{
    "readme_md": str,                       # Complete README.md content
    "sections_generated": [str],            # List of sections included
    "project_metadata": {                   # Extracted metadata
        "project_name": str,
        "organization": str,
        "team": str,
        "contact_email": str,
        "priority": str,
        "description": str,
        "domain": str,
        "compute_platforms": [str],
        "storage_systems": [str],
        "monitoring_tools": [str],
        "ci_cd_provider": str,
    },
    "document_length": int,                 # Character count
    "table_of_contents": str,               # Generated TOC
    "infra_summary": str,                   # Infrastructure summary
    "requirements_summary": str,            # Requirements summary
}

Example output structure:

```python
result = await conductor.dispatch_task(task)

# Access generated README
readme = result.output_data["readme_md"]

# Access metadata
metadata = result.output_data["project_metadata"]
print(f"Project: {metadata['project_name']}")
print(f"Organization: {metadata['organization']}")

# Check what sections were generated
sections = result.output_data["sections_generated"]
print(f"Generated {len(sections)} sections")

# Get summaries
print(result.output_data["infra_summary"])
print(result.output_data["requirements_summary"])
```

# =============================================================================
# Available Sections
# =============================================================================

The agent can generate the following sections:

1. **overview** - High-level project description and purpose
2. **architecture** - System design and technical architecture
3. **setup** - Installation and configuration instructions
4. **usage** - How to use the project/API
5. **testing** - Testing strategy and commands
6. **deployment** - Deployment procedures and environments
7. **monitoring** - Observability, metrics, logging, tracing
8. **troubleshooting** - Common issues and solutions
9. **contributing** - Contributing guidelines (if added)

# =============================================================================
# Usage Examples
# =============================================================================

### Example 1: Basic README Generation

```python
from conductor.agents.development import ReadmeGeneratorAgent
from conductor.core.config import ConductorConfig
from conductor.core.models import TaskDefinition
from conductor.core.enums import AgentType
from conductor.facade import ConductorAI
from conductor.integrations.llm import AnthropicLLMProvider

async def generate_readme():
    config = ConductorConfig()
    conductor = ConductorAI(config=config)
    await conductor.start()

    # Use Anthropic Claude for generation
    llm = AnthropicLLMProvider(config=config)
    agent = ReadmeGeneratorAgent("readme-01", config, llm_provider=llm)
    await conductor.register_agent(agent)

    # Load your YAML files
    with open("infra.yaml") as f:
        infra_yaml = f.read()
    with open("requirements.yaml") as f:
        requirements_yaml = f.read()

    task = TaskDefinition(
        name="Generate README",
        assigned_to=AgentType.CODING,
        input_data={
            "infra_yaml": infra_yaml,
            "requirements_yaml": requirements_yaml,
            "project_name": "My Project",
        },
    )

    result = await conductor.dispatch_task(task)
    readme = result.output_data["readme_md"]

    # Save to file
    with open("README.md", "w") as f:
        f.write(readme)

    await conductor.stop()

asyncio.run(generate_readme())
```

### Example 2: Minimal Style Documentation

```python
task = TaskDefinition(
    name="Generate Minimal README",
    assigned_to=AgentType.CODING,
    input_data={
        "infra_yaml": infra_content,
        "requirements_yaml": requirements_content,
        "project_name": "Quick API",
        "include_sections": ["overview", "setup", "usage"],
        "style": "minimal",  # Concise documentation
    },
)

result = await conductor.dispatch_task(task)
minimal_readme = result.output_data["readme_md"]
```

### Example 3: Professional Enterprise Documentation

```python
task = TaskDefinition(
    name="Generate Enterprise README",
    assigned_to=AgentType.CODING,
    input_data={
        "infra_yaml": infra_content,
        "requirements_yaml": requirements_content,
        "project_name": "Enterprise Data Platform",
        "include_sections": [
            "overview",
            "architecture",
            "setup",
            "usage",
            "testing",
            "deployment",
            "monitoring",
            "troubleshooting",
            "contributing",
        ],
        "style": "professional",  # Comprehensive documentation
    },
)

result = await conductor.dispatch_task(task)
enterprise_readme = result.output_data["readme_md"]
```

# =============================================================================
# Integration with Full Workflows
# =============================================================================

You can integrate README generation into larger workflows:

```python
workflow = WorkflowDefinition(
    name="Complete Project Generation",
    description="Generate code, tests, and documentation",
    phases=[WorkflowPhase.DEVELOPMENT],
    tasks=[
        # Generate code
        TaskDefinition(
            name="Generate Code",
            assigned_to=AgentType.CODING,
            input_data={"specification": "..."},
        ),
        # Generate tests
        TaskDefinition(
            name="Generate Tests",
            assigned_to=AgentType.TEST,
            input_data={"code": "...", "test_data": "..."},
        ),
        # Generate README (parallel or sequential)
        TaskDefinition(
            name="Generate Documentation",
            assigned_to=AgentType.CODING,
            input_data={
                "infra_yaml": infra_yaml,
                "requirements_yaml": requirements_yaml,
                "project_name": "My Project",
            },
        ),
    ],
)

state = await conductor.run_workflow(workflow)
```

# =============================================================================
# YAML Specifications Format
# =============================================================================

### Infrastructure YAML (infra.yaml)

```yaml
registry_version: "1.0"
organization: "Company Name"
last_updated: "2024-01-15"

compute:
  kubernetes:
    clusters: ["eks-prod", "eks-staging"]
    max_nodes: 30
  docker:
    registry: "ecr.aws/..."

storage:
  rds:
    engines: ["postgres15"]
    multi_az: true
  s3:
    buckets_allowed: true

networking:
  vpc: ["vpc-prod"]
  cdn: "cloudfront"

monitoring:
  metrics: "prometheus"
  logging: "elasticsearch"
  tracing: "jaeger"

security:
  secrets_manager: "aws_secrets_manager"
  waf: true
```

### Requirements YAML (requirements.yaml)

```yaml
project_name: "my-api"
team: "Platform Team"
description: |
  REST API for managing resources.
  
domain: "fintech"

features:
  - name: "Authentication"
    must_have: true
  - name: "Rate Limiting"
    must_have: false

performance:
  expected_throughput: "10000 req/min"
  response_time_target: "< 100ms"
  availability: "99.95%"

compliance:
  regulations: ["SOC2", "GDPR"]
  encryption_required: true
```

# =============================================================================
# Best Practices
# =============================================================================

1. **Provide Complete YAML Specifications**
   - Include all relevant infrastructure and requirements
   - More detail = better generated documentation

2. **Choose Appropriate Style**
   - "minimal": Quick reference guides
   - "standard": General purpose documentation
   - "professional": Enterprise-grade comprehensive docs

3. **Select Relevant Sections**
   - Include sections that matter for your project
   - Remove unnecessary sections for clarity

4. **Review Generated Content**
   - Use generated README as a starting point
   - Add project-specific information manually
   - Keep custom sections when updating

5. **Integrate with CI/CD**
   - Generate README as part of build pipeline
   - Commit generated docs to repository
   - Update on requirements changes

6. **Use Real LLM Providers**
   - MockLLMProvider for testing/demo
   - AnthropicLLMProvider or OpenAILLMProvider for production
   - Configure API keys in conductor.yaml or environment

# =============================================================================
# Troubleshooting
# =============================================================================

### Issue: Generated README is too generic

**Solution**: Provide more detailed YAML specifications or use "professional"
style with all sections enabled.

### Issue: LLM API timeout

**Solution**: Increase timeout in ConductorConfig or use a faster LLM model.

### Issue: YAML parsing errors

**Solution**: Ensure YAML files are valid. Test with:
```python
import yaml
yaml.safe_load(yaml_content)
```

### Issue: Generated sections are missing

**Solution**: Check that section names in include_sections match available
sections. Invalid sections are skipped silently.

# =============================================================================
# Extending the Agent
# =============================================================================

You can extend ReadmeGeneratorAgent to customize behavior:

```python
class CustomReadmeGenerator(ReadmeGeneratorAgent):
    async def _generate_sections(self, ...):
        # Override to add custom sections or modify generation
        sections = await super()._generate_sections(...)
        # Custom logic here
        return sections

    def _assemble_readme(self, ...):
        # Override to customize assembly
        readme = super()._assemble_readme(...)
        # Custom modifications
        return readme
```

# =============================================================================
# Running the Example
# =============================================================================

```bash
# From project root
python examples/generate_readme_workflow.py

# Output will be saved to: outputs/README.md
```

# =============================================================================
# Summary
# =============================================================================

The README Generation workflow showcases ConductorAI's ability to:

✓ Parse structured specifications (YAML)
✓ Extract and organize metadata
✓ Generate contextual content via LLM
✓ Assemble professional documentation
✓ Integrate with larger workflows

This pattern can be applied to generate other documentation (API docs, 
architecture diagrams, deployment guides, etc.).

For more information, see:
- examples/generate_readme_workflow.py
- src/conductor/agents/development/readme_generator_agent.py
- docs/day-06-dev-agents-llm.md

