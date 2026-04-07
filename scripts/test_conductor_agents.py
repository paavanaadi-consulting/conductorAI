#!/usr/bin/env python3
"""
Test ConductorAI framework agents using MockLLMProvider or the live Anthropic API.

Validates that each specialized agent (CodingAgent, ReviewAgent, etc.)
correctly handles task validation, execution, and result generation.

Usage:
    # Test all agents (mock, no API key needed):
    python scripts/test_conductor_agents.py

    # Test a specific agent type:
    python scripts/test_conductor_agents.py --agent coding

    # Test with live Anthropic API:
    python scripts/test_conductor_agents.py --live
    python scripts/test_conductor_agents.py --live --api-key sk-ant-...

    # Verbose output (show full output_data):
    python scripts/test_conductor_agents.py --verbose
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
from conductor.core.enums import AgentType, TaskStatus
from conductor.core.models import TaskDefinition
from conductor.integrations.llm.mock import MockLLMProvider


# ── Agent definitions: type key → (factory, mock responses, task input_data) ──

AGENT_SPECS: dict[str, dict] = {
    "coding": {
        "factory": lambda config, provider: CodingAgent(
            "coding-test", config, llm_provider=provider
        ),
        "responses": ["def hello(name: str) -> str:\n    return f'Hello, {name}!'"],
        "task": TaskDefinition(
            name="Generate Hello Function",
            assigned_to=AgentType.CODING,
            input_data={
                "specification": "Create a greeting function that accepts a name",
                "language": "python",
            },
        ),
        "checks": lambda r: (
            r.status == TaskStatus.COMPLETED
            and "code" in r.output_data
            and r.output_data["language"] == "python"
        ),
    },
    "review": {
        "factory": lambda config, provider: ReviewAgent(
            "review-test", config, llm_provider=provider
        ),
        "responses": [
            "## Code Review\n\n**Score**: 8/10\n\n"
            "### Findings\n1. Good structure\n\n"
            "### Recommendations\n1. Add type hints\n\n"
            "**Verdict**: APPROVED"
        ],
        "task": TaskDefinition(
            name="Review Hello Function",
            assigned_to=AgentType.REVIEW,
            input_data={
                "code": "def hello(name): return f'Hello, {name}!'",
                "review_criteria": ["style", "correctness"],
            },
        ),
        "checks": lambda r: (
            r.status == TaskStatus.COMPLETED
            and "review" in r.output_data
            and "approved" in r.output_data
        ),
    },
    "test_data": {
        "factory": lambda config, provider: TestDataAgent(
            "testdata-test", config, llm_provider=provider
        ),
        "responses": [
            'VALID_NAMES = ["Alice", "Bob", ""]\n'
            'EDGE_CASES = [None, 123, " "]'
        ],
        "task": TaskDefinition(
            name="Generate Test Data",
            assigned_to=AgentType.TEST_DATA,
            input_data={
                "code": "def hello(name: str) -> str:\n    return f'Hello, {name}!'",
            },
        ),
        "checks": lambda r: (
            r.status == TaskStatus.COMPLETED and "test_data" in r.output_data
        ),
    },
    "test": {
        "factory": lambda config, provider: TestAgent(
            "test-test", config, llm_provider=provider
        ),
        "responses": [
            "import pytest\n\n"
            "def test_hello_valid():\n"
            "    assert hello('World') == 'Hello, World!'\n\n"
            "def test_hello_empty():\n"
            "    assert hello('') == 'Hello, !'\n"
        ],
        "task": TaskDefinition(
            name="Generate Unit Tests",
            assigned_to=AgentType.TEST,
            input_data={
                "code": "def hello(name: str) -> str:\n    return f'Hello, {name}!'",
            },
        ),
        "checks": lambda r: (
            r.status == TaskStatus.COMPLETED and "tests" in r.output_data
        ),
    },
    "devops": {
        "factory": lambda config, provider: DevOpsAgent(
            "devops-test", config, llm_provider=provider
        ),
        "responses": [
            "name: CI\non:\n  push:\n    branches: [main]\n"
            "jobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - uses: actions/checkout@v4\n"
        ],
        "task": TaskDefinition(
            name="Create CI Config",
            assigned_to=AgentType.DEVOPS,
            input_data={
                "code": "def hello(name): return f'Hello, {name}!'",
                "platform": "github_actions",
            },
        ),
        "checks": lambda r: (
            r.status == TaskStatus.COMPLETED
            and "config" in r.output_data
            and "platform" in r.output_data
        ),
    },
    "deploying": {
        "factory": lambda config, provider: DeployingAgent(
            "deploying-test", config, llm_provider=provider
        ),
        "responses": [
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n"
            "  name: hello-app\nspec:\n  replicas: 2\n"
        ],
        "task": TaskDefinition(
            name="Create Deployment Config",
            assigned_to=AgentType.DEPLOYING,
            input_data={
                "target_environment": "staging",
                "deployment_type": "kubernetes",
            },
        ),
        "checks": lambda r: (
            r.status == TaskStatus.COMPLETED
            and "deployment_config" in r.output_data
            and r.output_data["target_environment"] == "staging"
        ),
    },
    "monitor": {
        "factory": lambda config, provider: MonitorAgent(
            "monitor-test", config, llm_provider=provider
        ),
        "responses": [
            "Severity: low\n\n"
            "### Issues Found\n1. High memory usage on pod-3\n\n"
            "### Recommendations\n1. Increase memory limit to 512Mi\n\n"
            "### Feedback for Development\nConsider using generators for large datasets."
        ],
        "task": TaskDefinition(
            name="Monitor Deployment",
            assigned_to=AgentType.MONITOR,
            input_data={
                "deployment_result": "Deployment to staging completed. 3 pods running.",
                "metrics": "cpu: 45%, memory: 89%, latency_p99: 230ms",
            },
        ),
        "checks": lambda r: (
            r.status == TaskStatus.COMPLETED
            and "analysis" in r.output_data
            and "severity" in r.output_data
        ),
    },
}


async def test_agent_validation(
    agent_key: str,
    spec: dict,
    config: ConductorConfig,
    verbose: bool,
) -> bool:
    """Test that an agent rejects invalid input_data."""
    provider = MockLLMProvider()
    agent = spec["factory"](config, provider)
    await agent.start()

    invalid_task = TaskDefinition(
        name="Invalid Task",
        assigned_to=spec["task"].assigned_to,
        input_data={},  # empty — should fail validation
    )

    try:
        result = await agent.execute_task(invalid_task)
        # If we get here with a FAILED status, that's also acceptable
        if result.status == TaskStatus.FAILED:
            return True
        print(f"    WARN: Expected validation failure but got {result.status.value}")
        return False
    except Exception:
        # AgentError on validation failure is expected
        return True
    finally:
        await agent.stop()


async def test_agent_execution(
    agent_key: str,
    spec: dict,
    config: ConductorConfig,
    verbose: bool,
    live_provider=None,
) -> bool:
    """Test that an agent produces a valid result for a well-formed task."""
    if live_provider is not None:
        provider = live_provider
    else:
        provider = MockLLMProvider()
        for resp in spec["responses"]:
            provider.queue_response(resp)

    agent = spec["factory"](config, provider)
    await agent.start()

    try:
        result = await agent.execute_task(spec["task"])

        checks_passed = spec["checks"](result)
        if not checks_passed:
            print(f"    FAIL: Output checks did not pass")
            print(f"    Status: {result.status.value}")
            if result.error_message:
                print(f"    Error: {result.error_message}")

        if verbose and result.output_data:
            print(f"    Output keys: {list(result.output_data.keys())}")
            for k, v in result.output_data.items():
                val_str = str(v)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                print(f"      {k}: {val_str}")

        if live_provider is not None and result.output_data:
            model = result.output_data.get("llm_model", "?")
            usage = result.output_data.get("llm_usage", {})
            print(f"    Model: {model}")
            print(f"    Tokens: {usage.get('prompt_tokens', '?')} in / "
                  f"{usage.get('completion_tokens', '?')} out")

        return checks_passed
    except Exception as e:
        print(f"    FAIL: Unexpected exception: {type(e).__name__}: {e}")
        return False
    finally:
        await agent.stop()


async def test_agent_lifecycle(
    agent_key: str,
    spec: dict,
    config: ConductorConfig,
    verbose: bool,
) -> bool:
    """Test agent start/stop lifecycle and state transitions."""
    from conductor.core.enums import AgentStatus

    provider = MockLLMProvider()
    agent = spec["factory"](config, provider)

    # Before start
    if agent.status != AgentStatus.IDLE:
        print(f"    FAIL: Expected IDLE before start, got {agent.status.value}")
        return False

    await agent.start()
    if agent.status != AgentStatus.IDLE:
        print(f"    FAIL: Expected IDLE after start, got {agent.status.value}")
        return False

    await agent.stop()
    if agent.status != AgentStatus.CANCELLED:
        print(f"    FAIL: Expected CANCELLED after stop, got {agent.status.value}")
        return False

    return True


def create_live_provider(api_key: str | None, model: str) -> object:
    """Create a live Anthropic LLM provider."""
    from conductor.core.config import LLMConfig
    from conductor.integrations.llm.factory import create_llm_provider

    llm_config = LLMConfig(
        provider="anthropic",
        model=model,
        api_key=api_key,
    )
    return create_llm_provider(llm_config)


async def run_tests(
    agent_filter: str | None,
    verbose: bool,
    live: bool = False,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> bool:
    """Run all agent tests and return True if all pass."""
    config = ConductorConfig()
    live_provider = None

    if live:
        live_provider = create_live_provider(api_key, model)
        is_valid = await live_provider.validate()
        if not is_valid:
            print("ERROR: Anthropic API key not found or invalid.")
            print("Set ANTHROPIC_API_KEY or pass --api-key.")
            return False
        print(f"Mode: LIVE (model={model})")
    else:
        print("Mode: MOCK (use --live for real Anthropic API)")

    agents_to_test = AGENT_SPECS
    if agent_filter:
        if agent_filter not in AGENT_SPECS:
            print(f"ERROR: Unknown agent '{agent_filter}'.")
            print(f"Available: {', '.join(AGENT_SPECS.keys())}")
            return False
        agents_to_test = {agent_filter: AGENT_SPECS[agent_filter]}

    print(f"Testing {len(agents_to_test)} ConductorAI agent(s)\n")

    total = 0
    passed = 0

    for agent_key, spec in agents_to_test.items():
        agent_name = spec["factory"](config, MockLLMProvider()).__class__.__name__
        print(f"{'='*60}")
        print(f"  {agent_name} ({agent_key})")
        print(f"{'='*60}")

        # Test 1: Lifecycle (always uses mock — no LLM calls)
        total += 1
        print(f"  [lifecycle] ", end="")
        ok = await test_agent_lifecycle(agent_key, spec, config, verbose)
        print("PASS" if ok else "FAIL")
        passed += ok

        # Test 2: Validation (always uses mock — no LLM calls)
        total += 1
        print(f"  [validation] ", end="")
        ok = await test_agent_validation(agent_key, spec, config, verbose)
        print("PASS" if ok else "FAIL")
        passed += ok

        # Test 3: Execution (uses live provider if --live)
        total += 1
        print(f"  [execution{' LIVE' if live else ''}] ", end="")
        ok = await test_agent_execution(
            agent_key, spec, config, verbose, live_provider=live_provider,
        )
        print("PASS" if ok else "FAIL")
        passed += ok

        print()

    print(f"{'='*60}")
    print(f"  Results: {passed}/{total} passed")
    print(f"{'='*60}")

    return passed == total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test ConductorAI framework agents (mock or live Anthropic API)"
    )
    parser.add_argument(
        "--agent",
        choices=list(AGENT_SPECS.keys()),
        help="Test a specific agent type (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output data from agent execution",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real Anthropic API instead of MockLLMProvider",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Anthropic model to use with --live (default: claude-sonnet-4-20250514)",
    )
    args = parser.parse_args()

    success = asyncio.run(run_tests(
        args.agent, args.verbose, args.live, args.api_key, args.model,
    ))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
