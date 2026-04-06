---
description: Scaffold a new specialized agent for the ConductorAI framework.
---

Create a new agent in `src/conductor/agents/` following the project's conventions:

1. Read `src/conductor/agents/base.py` to understand the base agent interface.
2. Create a new file `src/conductor/agents/{agent_name}.py` with:
   - A class inheriting from the base agent
   - Async `execute` method
   - Pydantic model for agent config
   - Proper type annotations
3. Register the agent in `src/conductor/agents/__init__.py`.
4. Create a test file `tests/unit/agents/test_{agent_name}.py` with basic unit tests using `@pytest.mark.unit`.

Follow existing agent patterns (development, devops, monitoring) as reference.
