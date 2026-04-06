---
description: Scaffold a new workflow pipeline for the ConductorAI orchestration engine.
---

Create a new workflow in `src/conductor/orchestration/` following the project's conventions:

1. Read existing workflow patterns in `src/conductor/orchestration/`.
2. Define the workflow stages using the project's enum and model patterns.
3. Implement async orchestration logic with proper error handling using `src/conductor/core/exceptions.py`.
4. Add message bus integration for agent communication.
5. Create tests in `tests/unit/orchestration/` with `@pytest.mark.unit`.

Ensure the workflow integrates with the coordinator and state manager.
