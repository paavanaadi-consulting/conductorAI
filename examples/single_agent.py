"""
Single Agent Example — Dispatch a Task to One Agent
=====================================================

This example demonstrates the simplest way to use ConductorAI:
register one agent and dispatch a single task to it, without
running a full multi-phase workflow.

This is useful for:
    - Quick prototyping
    - Debugging an agent in isolation
    - One-off code generation tasks

Usage:
    python examples/single_agent.py
"""

from __future__ import annotations

import asyncio

from conductor.agents.development.coding_agent import CodingAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType
from conductor.core.models import TaskDefinition
from conductor.facade import ConductorAI
from conductor.integrations.llm.mock import MockLLMProvider


async def main() -> None:
    """Dispatch a single coding task and print the result."""
    config = ConductorConfig()

    # Create a mock LLM provider with a specific response
    provider = MockLLMProvider()
    provider.queue_response(
        'def fibonacci(n: int) -> list[int]:\n'
        '    """Generate the first n Fibonacci numbers."""\n'
        '    if n <= 0:\n'
        '        return []\n'
        '    if n == 1:\n'
        '        return [0]\n'
        '    fibs = [0, 1]\n'
        '    for _ in range(2, n):\n'
        '        fibs.append(fibs[-1] + fibs[-2])\n'
        '    return fibs\n'
    )

    async with ConductorAI(config) as conductor:
        # Register one agent
        agent = CodingAgent("coding-01", config, llm_provider=provider)
        await conductor.register_agent(agent)

        # Dispatch a single task (no workflow needed)
        task = TaskDefinition(
            name="Generate Fibonacci Function",
            assigned_to=AgentType.CODING,
            input_data={
                "specification": "Write a function to generate Fibonacci numbers",
                "language": "python",
            },
        )

        result = await conductor.dispatch_task(task)

        # Print results
        print("Single Agent Dispatch")
        print("-" * 40)
        print(f"Status   : {result.status.value}")
        print(f"Agent    : {result.agent_id}")
        print(f"Duration : {result.duration_seconds:.3f}s")
        print(f"Language : {result.output_data.get('language', 'N/A')}")
        print()
        print("Generated Code:")
        print(result.output_data.get("code", "N/A"))


if __name__ == "__main__":
    asyncio.run(main())
