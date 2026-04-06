---
description: Debug a failing ConductorAI pipeline by inspecting logs, state, and agent outputs.
---

Debug the specified pipeline issue:

1. Check recent test output: `pytest -x -v --tb=long` for the relevant test files.
2. Inspect the pipeline's state manager and message bus interactions.
3. Review structlog output for error traces.
4. Check agent execution order and message flow.
5. Verify Pydantic model validation on inputs/outputs.
6. Identify root cause and suggest a fix with minimal changes.

Focus on async-related issues (race conditions, missing awaits) as these are common in this codebase.
