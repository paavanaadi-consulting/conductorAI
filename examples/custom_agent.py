"""
Custom Agent Example — Extending BaseAgent
=============================================

This example shows how to create your own agent by subclassing BaseAgent.
A custom agent must implement two abstract methods:

    _validate_task(task)  — Check if the task has required input fields.
    _execute(task)        — Perform the agent's core work and return a result.

Optionally, you can override lifecycle hooks:
    _on_start()  — Custom initialization (connections, caches, etc.)
    _on_stop()   — Custom cleanup (close connections, flush buffers, etc.)

In this example, we build a DocumentationAgent that generates API docs
from source code using the LLM provider.

Usage:
    python examples/custom_agent.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from conductor.agents.base import BaseAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, TaskStatus
from conductor.core.models import TaskDefinition, TaskResult
from conductor.facade import ConductorAI
from conductor.integrations.llm.base import BaseLLMProvider
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Custom Agent: DocumentationAgent
# =============================================================================
# Note: We use AgentType.CODING as a stand-in because custom agent types
# aren't in the enum. In production, you'd extend the enum or use a
# generic type. The agent_type determines which tasks the coordinator
# routes to this agent.
# =============================================================================
class DocumentationAgent(BaseAgent):
    """Generates API documentation from source code.

    This agent takes source code as input and uses an LLM to produce
    structured Markdown documentation including function signatures,
    descriptions, parameters, and return values.

    Input Requirements:
        - code (str): The source code to document.
        - format (str, optional): Output format (default: "markdown").
    """

    def __init__(
        self,
        agent_id: str,
        config: ConductorConfig,
        *,
        llm_provider: BaseLLMProvider,
    ) -> None:
        # Initialize BaseAgent with CODING type as a stand-in
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.CODING,
            config=config,
            name=f"docs-{agent_id}",
            description="Generates API documentation from source code",
        )
        self._llm_provider = llm_provider

    async def _on_start(self) -> None:
        """Custom startup hook — called when agent is registered."""
        self._logger.info("documentation_agent_ready")

    async def _on_stop(self) -> None:
        """Custom shutdown hook — called when agent is unregistered."""
        self._logger.info("documentation_agent_stopped")

    async def _validate_task(self, task: TaskDefinition) -> bool:
        """Check that the task contains source code to document."""
        return "code" in task.input_data

    async def _execute(self, task: TaskDefinition) -> TaskResult:
        """Generate documentation using the LLM provider."""
        code = task.input_data["code"]
        output_format = task.input_data.get("format", "markdown")

        # Build the prompt for the LLM
        system_prompt = (
            "You are a technical writer. Generate clear, concise API "
            "documentation from the given source code. Include function "
            "signatures, descriptions, parameters, and return values. "
            f"Output format: {output_format}."
        )
        user_prompt = f"Generate documentation for this code:\n\n{code}"

        # Call the LLM
        response = await self._llm_provider.generate_with_system(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        return self._create_result(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "documentation": response.content,
                "format": output_format,
                "llm_model": response.model,
            },
        )


# =============================================================================
# Main
# =============================================================================

async def main() -> None:
    """Create a DocumentationAgent and use it to generate docs."""
    config = ConductorConfig()

    # Set up mock LLM with a documentation response
    provider = MockLLMProvider()
    provider.queue_response(
        "# API Reference\n\n"
        "## `fibonacci(n: int) -> list[int]`\n\n"
        "Generate the first `n` Fibonacci numbers.\n\n"
        "**Parameters:**\n"
        "- `n` (int): How many Fibonacci numbers to generate.\n\n"
        "**Returns:**\n"
        "- `list[int]`: The first `n` Fibonacci numbers.\n\n"
        "**Raises:**\n"
        "- None\n\n"
        "**Example:**\n"
        "```python\n"
        "fibonacci(5)  # [0, 1, 1, 2, 3]\n"
        "```\n"
    )

    async with ConductorAI(config) as conductor:
        # Register our custom agent
        agent = DocumentationAgent("doc-01", config, llm_provider=provider)
        await conductor.register_agent(agent)

        # Dispatch a documentation task
        task = TaskDefinition(
            name="Generate Fibonacci Docs",
            assigned_to=AgentType.CODING,
            input_data={
                "code": "def fibonacci(n: int) -> list[int]: ...",
                "format": "markdown",
            },
        )

        result = await conductor.dispatch_task(task)

        print("Custom Agent — Documentation Generator")
        print("-" * 45)
        print(f"Status : {result.status.value}")
        print(f"Agent  : {result.agent_id}")
        print(f"Format : {result.output_data.get('format')}")
        print()
        print("Generated Documentation:")
        print(result.output_data.get("documentation", "N/A"))


if __name__ == "__main__":
    asyncio.run(main())
