"""
ConductorAI UI — Workflow Builder

Maps UI component checkboxes to WorkflowDefinition with correct
phases, agent types, and task definitions.
"""

from __future__ import annotations

from conductor.core.enums import AgentType, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition


# Component name → (AgentType, WorkflowPhase)
COMPONENT_MAP: dict[str, tuple[AgentType, WorkflowPhase]] = {
    "code": (AgentType.CODING, WorkflowPhase.DEVELOPMENT),
    "unit_test": (AgentType.TEST, WorkflowPhase.DEVELOPMENT),
    "test_data": (AgentType.TEST_DATA, WorkflowPhase.DEVELOPMENT),
    "deployment": (AgentType.DEVOPS, WorkflowPhase.DEVOPS),
    "monitoring": (AgentType.MONITOR, WorkflowPhase.MONITORING),
}

# Canonical phase ordering
PHASE_ORDER = [
    WorkflowPhase.DEVELOPMENT,
    WorkflowPhase.DEVOPS,
    WorkflowPhase.MONITORING,
]


def build_workflow_definition(
    project_id: str,
    project_name: str,
    github_repo: str,
    requirements_yaml: str,
    infra_yaml: str,
    pipeline_yaml: str,
    selected_components: list[str],
) -> WorkflowDefinition:
    """Build a WorkflowDefinition from project data and selected components."""

    tasks: list[TaskDefinition] = []
    phases_needed: set[WorkflowPhase] = set()

    base_input = {
        "specification": pipeline_yaml,
        "requirements_yaml": requirements_yaml,
        "infra_yaml": infra_yaml,
        "project_name": project_name,
        "github_repo": github_repo,
    }

    for component in selected_components:
        if component not in COMPONENT_MAP:
            continue

        agent_type, phase = COMPONENT_MAP[component]
        phases_needed.add(phase)

        tasks.append(
            TaskDefinition(
                name=f"{component.replace('_', ' ').title()} Generation",
                description=f"Generate {component} for {project_name}",
                assigned_to=agent_type,
                input_data={**base_input, "component": component},
            )
        )

        # Deployment also requires DEPLOYING agent
        if component == "deployment":
            tasks.append(
                TaskDefinition(
                    name="Deploy to Environment",
                    description=f"Deploy {project_name} artifacts",
                    assigned_to=AgentType.DEPLOYING,
                    input_data={**base_input, "component": "deploy"},
                )
            )

    # Auto-add code review when code generation is selected
    if "code" in selected_components:
        tasks.append(
            TaskDefinition(
                name="Code Review",
                description=f"Review generated code for {project_name}",
                assigned_to=AgentType.REVIEW,
                input_data={
                    **base_input,
                    "code": "",  # Populated at runtime from coding output
                    "language": "python",
                },
            )
        )

    # Build ordered phase list
    phases = [p for p in PHASE_ORDER if p in phases_needed]

    return WorkflowDefinition(
        name=f"Workflow for {project_name}",
        description=f"Generated workflow for project {project_name}",
        phases=phases,
        tasks=tasks,
        metadata={
            "project_id": project_id,
            "github_repo": github_repo,
            "selected_components": selected_components,
        },
    )
