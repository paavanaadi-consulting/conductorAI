"""
Full Workflow Example — ConductorAI End-to-End Pipeline
=========================================================

This example demonstrates a complete ConductorAI workflow running through
all three phases:

    DEVELOPMENT → DEVOPS → MONITORING

Phase Breakdown:
    1. DEVELOPMENT:
        - CodingAgent generates code from a specification
        - ReviewAgent reviews the generated code
        - TestDataAgent generates test fixtures
        - TestAgent generates test suites

    2. DEVOPS:
        - DevOpsAgent creates CI/CD configuration
        - DeployingAgent creates deployment manifests

    3. MONITORING:
        - MonitorAgent analyzes the deployment result

All agents use MockLLMProvider for deterministic, offline execution.
Each agent makes exactly one LLM call, so we queue 7 responses.

Usage:
    python examples/full_workflow.py
"""

from __future__ import annotations

import asyncio

from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.development.test_data_agent import TestDataAgent
from conductor.agents.devops.deploying_agent import DeployingAgent
from conductor.agents.devops.devops_agent import DevOpsAgent
from conductor.agents.monitoring.monitor_agent import MonitorAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.facade import ConductorAI
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Mock LLM Responses
# =============================================================================
# Each agent calls the LLM exactly once. We queue responses in the order
# agents will be dispatched: coding → review → test_data → test → devops
# → deploying → monitor.
# =============================================================================

CODING_RESPONSE = """\
def create_user(name: str, email: str) -> dict:
    \"\"\"Create a new user in the system.\"\"\"
    if not name or not email:
        raise ValueError("Name and email are required")
    return {
        "id": generate_id(),
        "name": name,
        "email": email,
        "created_at": datetime.utcnow().isoformat(),
    }

def get_user(user_id: str) -> dict:
    \"\"\"Retrieve a user by ID.\"\"\"
    user = db.find_one({"id": user_id})
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    return user
"""

REVIEW_RESPONSE = """\
## Code Review Summary

**Overall Quality**: Good
**Score**: 8/10

### Findings

1. **Style**: Code follows PEP 8 conventions.
2. **Documentation**: Docstrings present and descriptive.
3. **Error Handling**: Input validation present. Consider logging.
4. **Performance**: No issues at current scale.

### Recommendations

- Add type hints to return values.
- Consider adding logging for audit trail.

**Verdict**: APPROVED with minor suggestions.
"""

TEST_DATA_RESPONSE = """\
## Test Data Fixtures

```python
VALID_USERS = [
    {"name": "Alice Smith", "email": "alice@example.com"},
    {"name": "Bob Jones", "email": "bob@example.com"},
]

INVALID_USERS = [
    {"name": "", "email": "bad@example.com"},
    {"name": "No Email", "email": ""},
]

EDGE_CASES = [
    {"name": "A" * 256, "email": "long@example.com"},
]
```
"""

TEST_RESPONSE = """\
## Test Suite

```python
import pytest

def test_create_user_valid():
    result = create_user("Alice", "alice@example.com")
    assert result["name"] == "Alice"
    assert "id" in result

def test_create_user_empty_name():
    with pytest.raises(ValueError):
        create_user("", "alice@example.com")

def test_get_user_not_found():
    with pytest.raises(NotFoundError):
        get_user("nonexistent-id")
```
"""

DEVOPS_RESPONSE = """\
## Docker Configuration

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: "3.8"
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://db:5432/app
```
"""

DEPLOYING_RESPONSE = """\
## Deployment Configuration

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: user-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: user-service
  template:
    spec:
      containers:
        - name: user-service
          image: user-service:latest
          ports:
            - containerPort: 8000
```
"""

MONITOR_RESPONSE = """\
## Monitoring Analysis

Severity: none

### Issues Found
(No issues detected)

### Recommendations
1. Add health check endpoint for readiness probes
2. Configure resource limits for containers

### Feedback for Development
All systems operating normally. No action required.
"""


async def main() -> None:
    """Run a full 3-phase workflow with all 7 agent types."""
    config = ConductorConfig()

    # --- Set up the mock LLM provider with queued responses ---
    # Responses are consumed in FIFO order, one per agent call.
    provider = MockLLMProvider()
    provider.queue_response(CODING_RESPONSE)
    provider.queue_response(REVIEW_RESPONSE)
    provider.queue_response(TEST_DATA_RESPONSE)
    provider.queue_response(TEST_RESPONSE)
    provider.queue_response(DEVOPS_RESPONSE)
    provider.queue_response(DEPLOYING_RESPONSE)
    provider.queue_response(MONITOR_RESPONSE)

    # --- Create the ConductorAI facade and run ---
    async with ConductorAI(config) as conductor:
        # Register all 7 agent types
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

        # --- Define the workflow ---
        workflow = WorkflowDefinition(
            name="User Service — Full Pipeline",
            description="Generate, review, test, deploy, and monitor a user service",
            phases=[
                WorkflowPhase.DEVELOPMENT,
                WorkflowPhase.DEVOPS,
                WorkflowPhase.MONITORING,
            ],
            tasks=[
                # Phase 1: DEVELOPMENT
                TaskDefinition(
                    name="Generate User Service Code",
                    assigned_to=AgentType.CODING,
                    input_data={
                        "specification": "REST API with create_user and get_user endpoints",
                        "language": "python",
                    },
                ),
                TaskDefinition(
                    name="Review Generated Code",
                    assigned_to=AgentType.REVIEW,
                    input_data={
                        "code": CODING_RESPONSE,
                        "review_criteria": ["style", "correctness", "security"],
                    },
                ),
                TaskDefinition(
                    name="Generate Test Fixtures",
                    assigned_to=AgentType.TEST_DATA,
                    input_data={"code": CODING_RESPONSE},
                ),
                TaskDefinition(
                    name="Generate Test Suite",
                    assigned_to=AgentType.TEST,
                    input_data={"code": CODING_RESPONSE},
                ),
                # Phase 2: DEVOPS
                TaskDefinition(
                    name="Create Docker Configuration",
                    assigned_to=AgentType.DEVOPS,
                    input_data={
                        "code": CODING_RESPONSE,
                        "platform": "docker",
                    },
                ),
                TaskDefinition(
                    name="Create Deployment Manifest",
                    assigned_to=AgentType.DEPLOYING,
                    input_data={
                        "target_environment": "staging",
                        "deployment_type": "docker",
                    },
                ),
                # Phase 3: MONITORING
                TaskDefinition(
                    name="Analyze Deployment",
                    assigned_to=AgentType.MONITOR,
                    input_data={
                        "deployment_result": "Deployment successful. All health checks passing.",
                    },
                ),
            ],
        )

        # --- Execute the workflow ---
        print("=" * 60)
        print("  ConductorAI — Full Pipeline Execution")
        print("=" * 60)
        print()

        state = await conductor.run_workflow(workflow)

        # --- Print results ---
        print(f"Workflow Status : {state.status.value}")
        print(f"Completed Tasks : {state.completed_task_count}")
        print(f"Failed Tasks    : {state.failed_task_count}")
        print(f"Feedback Loops  : {state.feedback_count}")
        print()

        # Print phase history
        print("Phase History:")
        for phase_record in state.phase_history:
            phase_name = phase_record.get("phase", "unknown")
            result = phase_record.get("result", "unknown")
            task_count = phase_record.get("task_count", 0)
            print(f"  {phase_name:15s} — {result} ({task_count} tasks)")
        print()

        # Print task results
        print("Task Results:")
        for task_id, result in state.task_results.items():
            agent = result.agent_id
            status = result.status.value
            duration = result.duration_seconds or 0
            print(f"  [{status:9s}] {agent:15s} ({duration:.3f}s)")

        print()
        print("=" * 60)
        print("  Pipeline Complete!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
