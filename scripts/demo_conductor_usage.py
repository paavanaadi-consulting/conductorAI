#!/usr/bin/env python3
"""
ConductorAI Usage Demos — runnable examples of the multi-agent framework.

Demonstrates how to:
    1. Dispatch a single task to one agent
    2. Run a single-phase DEVELOPMENT workflow
    3. Run a full 3-phase pipeline (DEVELOPMENT → DEVOPS → MONITORING)
    4. Use artifacts to persist and retrieve outputs
    5. Register multiple agents of the same type

All demos use MockLLMProvider so no API keys are needed.

Usage:
    # Run all demos:
    python scripts/demo_conductor_usage.py

    # Run a specific demo:
    python scripts/demo_conductor_usage.py --demo single-task
    python scripts/demo_conductor_usage.py --demo dev-workflow
    python scripts/demo_conductor_usage.py --demo full-pipeline
    python scripts/demo_conductor_usage.py --demo artifacts
    python scripts/demo_conductor_usage.py --demo multi-agent
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path so we can import conductor
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.development.test_data_agent import TestDataAgent
from conductor.agents.devops.deploying_agent import DeployingAgent
from conductor.agents.devops.devops_agent import DevOpsAgent
from conductor.agents.monitoring.monitor_agent import MonitorAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, TaskStatus, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.facade import ConductorAI
from conductor.infrastructure.artifact_store import Artifact
from conductor.integrations.llm.mock import MockLLMProvider


def section(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def subsection(title: str) -> None:
    print(f"  --- {title} ---")


# =============================================================================
# Demo 1: Single Task Dispatch
# =============================================================================

async def demo_single_task() -> None:
    """Dispatch a single coding task without a workflow."""
    section("Demo 1: Single Task Dispatch")
    print("  Dispatching one task directly to a CodingAgent.\n")

    config = ConductorConfig()
    provider = MockLLMProvider()
    provider.queue_response(
        "def fibonacci(n: int) -> list[int]:\n"
        '    """Return the first n Fibonacci numbers."""\n'
        "    if n <= 0:\n"
        "        return []\n"
        "    fibs = [0, 1]\n"
        "    while len(fibs) < n:\n"
        "        fibs.append(fibs[-1] + fibs[-2])\n"
        "    return fibs[:n]\n"
    )

    async with ConductorAI(config) as conductor:
        # Step 1: Register an agent
        await conductor.register_agent(
            CodingAgent("coding-01", config, llm_provider=provider)
        )

        # Step 2: Create a task
        task = TaskDefinition(
            name="Generate Fibonacci Function",
            assigned_to=AgentType.CODING,
            input_data={
                "specification": "Create a function that returns the first N Fibonacci numbers",
                "language": "python",
            },
        )

        # Step 3: Dispatch and inspect result
        result = await conductor.dispatch_task(task)

        print(f"  Status:   {result.status.value}")
        print(f"  Agent:    {result.agent_id}")
        print(f"  Duration: {result.duration_seconds:.3f}s")
        print(f"  Language: {result.output_data.get('language')}")
        print(f"\n  Generated code:\n")
        for line in result.output_data["code"].splitlines():
            print(f"    {line}")

    print(f"\n  Result: {'PASS' if result.status == TaskStatus.COMPLETED else 'FAIL'}")


# =============================================================================
# Demo 2: Development Phase Workflow
# =============================================================================

async def demo_dev_workflow() -> None:
    """Run a DEVELOPMENT-only workflow with 4 agents."""
    section("Demo 2: Development Phase Workflow")
    print("  Running DEVELOPMENT phase: Code → Review → Test Data → Tests\n")

    config = ConductorConfig()
    provider = MockLLMProvider()

    # Queue responses for each agent (code gen + context gen per agent)
    provider.queue_response("def add(a: int, b: int) -> int:\n    return a + b")
    provider.queue_response("APPROVED. Score: 9/10. Clean implementation.")
    provider.queue_response('TEST_CASES = [{"a": 1, "b": 2, "expected": 3}]')
    provider.queue_response(
        "def test_add():\n    assert add(1, 2) == 3\n\n"
        "def test_add_negative():\n    assert add(-1, 1) == 0\n"
    )

    async with ConductorAI(config) as conductor:
        # Register all development-phase agents
        await conductor.register_agent(
            CodingAgent("coding-01", config, llm_provider=provider)
        )
        await conductor.register_agent(
            ReviewAgent("review-01", config, llm_provider=provider)
        )
        await conductor.register_agent(
            TestDataAgent("testdata-01", config, llm_provider=provider)
        )
        await conductor.register_agent(
            TestAgent("test-01", config, llm_provider=provider)
        )

        # Define the workflow
        workflow = WorkflowDefinition(
            name="Build Add Function",
            phases=[WorkflowPhase.DEVELOPMENT],
            tasks=[
                TaskDefinition(
                    name="Generate Code",
                    assigned_to=AgentType.CODING,
                    input_data={
                        "specification": "Create a function that adds two integers",
                        "language": "python",
                    },
                ),
                TaskDefinition(
                    name="Review Code",
                    assigned_to=AgentType.REVIEW,
                    input_data={
                        "code": "def add(a: int, b: int) -> int:\n    return a + b",
                        "review_criteria": ["correctness", "style", "documentation"],
                    },
                ),
                TaskDefinition(
                    name="Generate Test Data",
                    assigned_to=AgentType.TEST_DATA,
                    input_data={
                        "code": "def add(a: int, b: int) -> int:\n    return a + b",
                    },
                ),
                TaskDefinition(
                    name="Generate Tests",
                    assigned_to=AgentType.TEST,
                    input_data={
                        "code": "def add(a: int, b: int) -> int:\n    return a + b",
                    },
                ),
            ],
        )

        # Execute
        state = await conductor.run_workflow(workflow)

        # Report
        print(f"  Workflow:  {workflow.name}")
        print(f"  Status:   {state.status.value}")
        print(f"  Phases:   {[p['phase'] for p in state.phase_history]}")
        print(f"  Tasks:    {state.completed_task_count} completed, "
              f"{state.failed_task_count} failed")

        subsection("Task Results")
        for task_id, task_result in state.task_results.items():
            print(f"    {task_result.agent_id}: {task_result.status.value}")

    print(f"\n  Result: {'PASS' if state.status == TaskStatus.COMPLETED else 'FAIL'}")


# =============================================================================
# Demo 3: Full 3-Phase Pipeline
# =============================================================================

async def demo_full_pipeline() -> None:
    """Run a full DEVELOPMENT → DEVOPS → MONITORING pipeline."""
    section("Demo 3: Full 3-Phase Pipeline")
    print("  Running: DEVELOPMENT → DEVOPS → MONITORING\n")

    config = ConductorConfig()
    provider = MockLLMProvider()

    # Queue one response per agent task
    provider.queue_response("from fastapi import FastAPI\napp = FastAPI()\n\n"
                            "@app.get('/health')\ndef health(): return {'status': 'ok'}")
    provider.queue_response("APPROVED. Score: 8/10. Good structure.")
    provider.queue_response('[{"endpoint": "/health", "method": "GET"}]')
    provider.queue_response("def test_health():\n    response = client.get('/health')\n"
                            "    assert response.status_code == 200")
    provider.queue_response("name: CI\non: [push]\njobs:\n  test:\n"
                            "    runs-on: ubuntu-latest")
    provider.queue_response("apiVersion: apps/v1\nkind: Deployment\n"
                            "metadata:\n  name: api-service")
    provider.queue_response(
        "Severity: none\n\n"
        "### Issues Found\n(none)\n\n"
        "### Recommendations\n1. Add readiness probe\n2. Set resource limits\n\n"
        "### Feedback for Development\nAll checks passed. API is healthy."
    )

    async with ConductorAI(config) as conductor:
        # Register all 7 agents
        agents = [
            CodingAgent("coding-01", config, llm_provider=provider),
            ReviewAgent("review-01", config, llm_provider=provider),
            TestDataAgent("testdata-01", config, llm_provider=provider),
            TestAgent("test-01", config, llm_provider=provider),
            DevOpsAgent("devops-01", config, llm_provider=provider),
            DeployingAgent("deploying-01", config, llm_provider=provider),
            MonitorAgent("monitor-01", config, llm_provider=provider),
        ]
        for agent in agents:
            await conductor.register_agent(agent)

        workflow = WorkflowDefinition(
            name="Deploy Health API",
            phases=[
                WorkflowPhase.DEVELOPMENT,
                WorkflowPhase.DEVOPS,
                WorkflowPhase.MONITORING,
            ],
            tasks=[
                # Development phase
                TaskDefinition(
                    name="Generate API Code",
                    assigned_to=AgentType.CODING,
                    input_data={
                        "specification": "FastAPI health check endpoint",
                        "language": "python",
                        "framework": "fastapi",
                    },
                ),
                TaskDefinition(
                    name="Review API Code",
                    assigned_to=AgentType.REVIEW,
                    input_data={
                        "code": "from fastapi import FastAPI\napp = FastAPI()",
                        "review_criteria": ["security", "performance"],
                    },
                ),
                TaskDefinition(
                    name="Generate Test Data",
                    assigned_to=AgentType.TEST_DATA,
                    input_data={"code": "app = FastAPI()"},
                ),
                TaskDefinition(
                    name="Generate Tests",
                    assigned_to=AgentType.TEST,
                    input_data={"code": "app = FastAPI()"},
                ),
                # DevOps phase
                TaskDefinition(
                    name="Create CI Pipeline",
                    assigned_to=AgentType.DEVOPS,
                    input_data={
                        "code": "app = FastAPI()",
                        "platform": "github_actions",
                    },
                ),
                TaskDefinition(
                    name="Create K8s Deployment",
                    assigned_to=AgentType.DEPLOYING,
                    input_data={
                        "target_environment": "staging",
                        "deployment_type": "kubernetes",
                    },
                ),
                # Monitoring phase
                TaskDefinition(
                    name="Monitor Deployment",
                    assigned_to=AgentType.MONITOR,
                    input_data={
                        "deployment_result": "3 pods running in staging",
                        "metrics": "cpu: 12%, memory: 45%, p99: 50ms",
                    },
                ),
            ],
        )

        state = await conductor.run_workflow(workflow)

        print(f"  Workflow: {workflow.name}")
        print(f"  Status:  {state.status.value}")
        print(f"  Phases:  {[p['phase'] for p in state.phase_history]}")
        print(f"  Tasks:   {state.completed_task_count} completed, "
              f"{state.failed_task_count} failed")

        subsection("Phase Summary")
        for phase in state.phase_history:
            print(f"    {phase['phase'].upper()}: "
                  f"{phase.get('completed_tasks', '?')} tasks completed")

    print(f"\n  Result: {'PASS' if state.status == TaskStatus.COMPLETED else 'FAIL'}")


# =============================================================================
# Demo 4: Artifact Management
# =============================================================================

async def demo_artifacts() -> None:
    """Save and retrieve artifacts through the ConductorAI facade."""
    section("Demo 4: Artifact Management")
    print("  Saving and retrieving workflow artifacts.\n")

    config = ConductorConfig()

    async with ConductorAI(config) as conductor:
        workflow_id = "demo-wf-001"

        # Save artifacts from different agents
        artifacts_data = [
            ("coding-01", "code", "def hello(): return 'world'"),
            ("review-01", "review", "APPROVED. Score: 9/10"),
            ("devops-01", "config", "name: CI\non: [push]"),
        ]

        for agent_id, artifact_type, content in artifacts_data:
            artifact = Artifact(
                workflow_id=workflow_id,
                task_id=f"task-{agent_id}",
                agent_id=agent_id,
                artifact_type=artifact_type,
                content=content,
            )
            await conductor.save_artifact(artifact)
            print(f"  Saved: {artifact_type} from {agent_id} "
                  f"(id={artifact.artifact_id[:8]}...)")

        # Retrieve all artifacts for the workflow
        all_artifacts = await conductor.get_workflow_artifacts(workflow_id)
        print(f"\n  Retrieved {len(all_artifacts)} artifacts for workflow {workflow_id}")

        for a in all_artifacts:
            print(f"    [{a.artifact_type}] {a.agent_id}: {a.content[:50]}...")

        # Retrieve a single artifact by ID
        single = await conductor.get_artifact(all_artifacts[0].artifact_id)
        print(f"\n  Single lookup: {single.artifact_type} = {single.content[:50]}...")

        # Non-existent artifact
        missing = await conductor.get_artifact("does-not-exist")
        print(f"  Missing lookup: {missing}")

    print(f"\n  Result: PASS")


# =============================================================================
# Demo 5: Multiple Agents of Same Type
# =============================================================================

async def demo_multi_agent() -> None:
    """Register multiple agents of the same type for parallel capacity."""
    section("Demo 5: Multiple Agents of Same Type")
    print("  Registering 3 CodingAgents and dispatching tasks.\n")

    config = ConductorConfig()

    # Each agent gets its own provider with a queued response
    providers = []
    for i in range(3):
        p = MockLLMProvider()
        p.queue_response(f"# Generated by coding-0{i+1}\ndef func_{i+1}(): pass")
        providers.append(p)

    async with ConductorAI(config) as conductor:
        # Register 3 coding agents
        for i, provider in enumerate(providers):
            agent = CodingAgent(
                f"coding-0{i+1}", config, llm_provider=provider,
                name=f"Coder #{i+1}",
            )
            await conductor.register_agent(agent)
            print(f"  Registered: {agent.agent_id} ({agent.identity.name})")

        print(f"\n  Total agents: {conductor.coordinator.agent_count}")

        # Dispatch tasks — coordinator picks an available agent
        for i in range(3):
            task = TaskDefinition(
                name=f"Generate Function {i+1}",
                assigned_to=AgentType.CODING,
                input_data={
                    "specification": f"Create utility function #{i+1}",
                    "language": "python",
                },
            )
            result = await conductor.dispatch_task(task)
            print(f"  Task {i+1}: {result.status.value} (agent={result.agent_id})")

        # Unregister one agent
        await conductor.unregister_agent("coding-03")
        print(f"\n  After unregister: {conductor.coordinator.agent_count} agents")

    print(f"\n  Result: PASS")


# =============================================================================
# Runner
# =============================================================================

DEMOS = {
    "single-task": demo_single_task,
    "dev-workflow": demo_dev_workflow,
    "full-pipeline": demo_full_pipeline,
    "artifacts": demo_artifacts,
    "multi-agent": demo_multi_agent,
}


async def run_all_demos(demo_filter: str | None) -> bool:
    demos = DEMOS
    if demo_filter:
        if demo_filter not in DEMOS:
            print(f"ERROR: Unknown demo '{demo_filter}'.")
            print(f"Available: {', '.join(DEMOS.keys())}")
            return False
        demos = {demo_filter: DEMOS[demo_filter]}

    print(f"Running {len(demos)} demo(s)...\n")

    for name, fn in demos.items():
        try:
            await fn()
        except Exception as e:
            print(f"\n  FAILED: {type(e).__name__}: {e}")
            return False

    section("All Demos Complete")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ConductorAI usage demos with MockLLMProvider"
    )
    parser.add_argument(
        "--demo",
        choices=list(DEMOS.keys()),
        help="Run a specific demo (default: all)",
    )
    args = parser.parse_args()

    success = asyncio.run(run_all_demos(args.demo))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
