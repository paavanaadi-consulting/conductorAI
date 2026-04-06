# Testing Claude Agents & Skills — Usage Guide

## Overview

This project includes custom `.claude/agents/` and `.claude/skills/` that extend Claude Code with ConductorAI-specific capabilities. The `test_claude_agents.py` script lets you test each agent individually against the real Anthropic API using the existing `AnthropicProvider` infrastructure.

---

## Prerequisites

1. **Install project dependencies** (includes the `anthropic` SDK):

   ```bash
   pip install -e ".[dev]"
   ```

2. **Set your Anthropic API key** (one of):

   ```bash
   # Option A: Environment variable (recommended)
   export ANTHROPIC_API_KEY=sk-ant-api03-...

   # Option B: Pass inline
   python scripts/test_claude_agents.py --api-key sk-ant-api03-...
   ```

---

## Agents (`.claude/agents/`)

| Agent             | File                  | Purpose                                              |
|-------------------|-----------------------|------------------------------------------------------|
| `code-reviewer`   | `code-reviewer.md`    | Reviews code for async correctness, types, conventions |
| `test-writer`     | `test-writer.md`      | Generates tests following project test patterns       |
| `doc-generator`   | `doc-generator.md`    | Generates documentation for modules and APIs          |

### How agents work

Each `.md` file contains:
- **Frontmatter** (`---` block): Agent `name` and `description`
- **Body**: The system prompt sent to Claude as the agent's persona/instructions

The test script reads these files, extracts the system prompt, and calls the Anthropic API via `AnthropicProvider.generate_with_system()`.

---

## Skills (`.claude/skills/`)

| Skill              | File                | Purpose                                        |
|--------------------|---------------------|------------------------------------------------|
| `add-agent`        | `add-agent.md`      | Scaffold a new specialized agent               |
| `add-workflow`     | `add-workflow.md`   | Scaffold a new workflow pipeline               |
| `debug-pipeline`   | `debug-pipeline.md` | Debug failing pipelines (logs, state, agents)  |

Skills are invoked directly in Claude Code (e.g., via slash commands) and are not tested through the API script.

---

## Running the Test Script

### Test all agents

```bash
python scripts/test_claude_agents.py
```

### Test a single agent

```bash
python scripts/test_claude_agents.py --agent code-reviewer
python scripts/test_claude_agents.py --agent test-writer
python scripts/test_claude_agents.py --agent doc-generator
```

### Choose a model

```bash
# Default: claude-sonnet-4-20250514
python scripts/test_claude_agents.py --model claude-sonnet-4-20250514

# Cheaper/faster for quick iteration
python scripts/test_claude_agents.py --model claude-3-5-haiku-20241022

# Most capable
python scripts/test_claude_agents.py --model claude-opus-4-0-20250514
```

### Tune generation parameters

```bash
# Lower tokens for faster/cheaper responses
python scripts/test_claude_agents.py --max-tokens 512

# More deterministic output
python scripts/test_claude_agents.py --temperature 0.1

# More creative output
python scripts/test_claude_agents.py --temperature 0.9
```

### Combined example

```bash
python scripts/test_claude_agents.py \
  --agent code-reviewer \
  --model claude-3-5-haiku-20241022 \
  --max-tokens 512 \
  --temperature 0.2
```

---

## What the Script Does

For each agent:

1. **Parses** the `.claude/agents/<name>.md` file (frontmatter + system prompt)
2. **Sends** the system prompt + a small test task to the Anthropic API
3. **Prints** the response with metadata:
   - Model used
   - Token usage (input / output)
   - Finish reason
   - Latency in milliseconds
   - Full response text

### Built-in Test Tasks

| Agent           | Test Task                                                    |
|-----------------|--------------------------------------------------------------|
| code-reviewer   | Review an async function that uses blocking `requests.get()` |
| test-writer     | Write unit tests for an `add_numbers()` async function       |
| doc-generator   | Generate docs for a `TaskQueue` class                        |

---

## Architecture — How It Leverages Existing Infra

The script reuses the ConductorAI LLM provider stack:

```
scripts/test_claude_agents.py
    │
    ├── LLMConfig(provider="anthropic", model=..., api_key=...)
    │       ↓
    ├── create_llm_provider(config)      # factory.py
    │       ↓
    ├── AnthropicProvider(config)         # anthropic_provider.py
    │       ↓
    └── provider.generate_with_system(system_prompt, user_prompt)
                ↓
        AsyncAnthropic → Anthropic Messages API → LLMResponse
```

No new dependencies. No duplicate API logic. Just the existing provider wired to your agent definitions.

---

## Adding a New Agent

1. Create `.claude/agents/my-agent.md`:

   ```markdown
   ---
   name: my-agent
   description: Does something useful.
   ---

   You are a specialist that does X. When given Y, you should...
   ```

2. (Optional) Add a test task in `scripts/test_claude_agents.py`:

   ```python
   AGENT_TEST_TASKS: dict[str, str] = {
       ...
       "my-agent": "Your test prompt here.",
   }
   ```

3. Run:

   ```bash
   python scripts/test_claude_agents.py --agent my-agent
   ```

   If no custom test task is defined, the script falls back to:
   *"Briefly introduce yourself and describe what you can help with."*

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ERROR: No Anthropic API key found` | Set `ANTHROPIC_API_KEY` env var or pass `--api-key` |
| `LLMProviderError: anthropic package required` | Run `pip install anthropic` or `pip install -e ".[dev]"` |
| `ERROR: Agent 'foo' not found` | Check available agents with `ls .claude/agents/` |
| Rate limit errors | Use `--model claude-3-5-haiku-20241022` (lower tier) or wait and retry |
| Truncated responses | Increase `--max-tokens` (default: 1024) |
