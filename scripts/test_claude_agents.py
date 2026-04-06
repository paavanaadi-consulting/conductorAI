#!/usr/bin/env python3
"""
Test .claude/agents individually using the Anthropic API.

Leverages the existing AnthropicProvider from conductor.integrations.llm
to send each agent's system prompt + a small test task to Claude.

Usage:
    # Test all agents:
    python scripts/test_claude_agents.py

    # Test a specific agent:
    python scripts/test_claude_agents.py --agent code-reviewer

    # Use a specific model:
    python scripts/test_claude_agents.py --model claude-sonnet-4-20250514

    # Set max tokens:
    python scripts/test_claude_agents.py --max-tokens 1024

Requires:
    ANTHROPIC_API_KEY environment variable (or pass --api-key)
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

# Add src to path so we can import conductor
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from conductor.core.config import LLMConfig
from conductor.integrations.llm.factory import create_llm_provider


# ── Agent definitions: name → small test task ──────────────────────────────
AGENT_TEST_TASKS: dict[str, str] = {
    "code-reviewer": (
        "Review this Python function for issues:\n\n"
        "```python\n"
        "async def fetch_data(url):\n"
        "    import requests\n"
        "    resp = requests.get(url)\n"
        "    data = resp.json()\n"
        "    return data\n"
        "```"
    ),
    "test-writer": (
        "Write unit tests for this function:\n\n"
        "```python\n"
        "async def add_numbers(a: int, b: int) -> int:\n"
        "    if not isinstance(a, int) or not isinstance(b, int):\n"
        "        raise TypeError('Both arguments must be integers')\n"
        "    return a + b\n"
        "```"
    ),
    "doc-generator": (
        "Generate documentation for this class:\n\n"
        "```python\n"
        "class TaskQueue:\n"
        "    def __init__(self, max_size: int = 100):\n"
        "        self._queue: list[dict] = []\n"
        "        self._max_size = max_size\n\n"
        "    async def enqueue(self, task: dict) -> str:\n"
        "        if len(self._queue) >= self._max_size:\n"
        "            raise OverflowError('Queue is full')\n"
        "        self._queue.append(task)\n"
        "        return task.get('id', 'unknown')\n\n"
        "    async def dequeue(self) -> dict | None:\n"
        "        return self._queue.pop(0) if self._queue else None\n"
        "```"
    ),
}

AGENTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "agents"


def parse_agent_md(path: Path) -> tuple[str, str]:
    """Parse an agent markdown file, returning (name, system_prompt)."""
    content = path.read_text()

    # Extract name from frontmatter
    name = path.stem
    fm_match = re.search(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"')
        # System prompt is everything after frontmatter
        system_prompt = content[fm_match.end():].strip()
    else:
        system_prompt = content.strip()

    return name, system_prompt


async def test_agent(
    provider,
    agent_name: str,
    system_prompt: str,
    test_task: str,
) -> None:
    """Test a single agent by sending its system prompt + test task to the API."""
    print(f"\n{'='*70}")
    print(f"  AGENT: {agent_name}")
    print(f"{'='*70}")
    print(f"System prompt: {system_prompt[:120]}...")
    print(f"Test task: {test_task[:80]}...")
    print(f"{'-'*70}")

    try:
        response = await provider.generate_with_system(
            system_prompt=system_prompt,
            user_prompt=test_task,
        )
        print(f"\nModel: {response.model}")
        print(f"Tokens: {response.usage.prompt_tokens} in / {response.usage.completion_tokens} out")
        print(f"Finish reason: {response.finish_reason}")
        print(f"Latency: {response.metadata.get('latency_ms', '?')}ms")
        print(f"\n--- Response ---\n{response.content}\n")
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test .claude/agents with Anthropic API")
    parser.add_argument("--agent", help="Test a specific agent by name (default: all)")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Model to use")
    parser.add_argument("--api-key", default=None, help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    parser.add_argument("--max-tokens", type=int, default=1024, help="Max response tokens")
    parser.add_argument("--temperature", type=float, default=0.3, help="Temperature (0-1)")
    args = parser.parse_args()

    # Create provider using existing infra
    llm_config = LLMConfig(
        provider="anthropic",
        model=args.model,
        api_key=args.api_key,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    provider = create_llm_provider(llm_config)

    # Validate
    if not await provider.validate():
        print("ERROR: No Anthropic API key found. Set ANTHROPIC_API_KEY or pass --api-key.")
        sys.exit(1)

    # Discover agents
    if not AGENTS_DIR.exists():
        print(f"ERROR: Agents directory not found: {AGENTS_DIR}")
        sys.exit(1)

    agent_files = sorted(AGENTS_DIR.glob("*.md"))
    if not agent_files:
        print(f"ERROR: No agent files found in {AGENTS_DIR}")
        sys.exit(1)

    # Parse all agents
    agents: dict[str, str] = {}
    for f in agent_files:
        name, system_prompt = parse_agent_md(f)
        agents[name] = system_prompt

    # Filter to specific agent if requested
    if args.agent:
        if args.agent not in agents:
            print(f"ERROR: Agent '{args.agent}' not found. Available: {', '.join(agents)}")
            sys.exit(1)
        agents = {args.agent: agents[args.agent]}

    print(f"Testing {len(agents)} agent(s) with model={args.model}")
    print(f"Agents: {', '.join(agents)}")

    # Run tests
    for agent_name, system_prompt in agents.items():
        test_task = AGENT_TEST_TASKS.get(
            agent_name,
            "Briefly introduce yourself and describe what you can help with.",
        )
        await test_agent(provider, agent_name, system_prompt, test_task)

    print(f"\n{'='*70}")
    print(f"  Done — tested {len(agents)} agent(s)")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
