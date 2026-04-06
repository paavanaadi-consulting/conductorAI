---
paths:
  - src/conductor/agents/**
---

# Agent Development Rules

- All agents extend `BaseAgent` from `conductor.agents.base`
- Agents communicate through the message bus, never by direct method calls
- Agent methods must be async
- Use Pydantic models for all agent input/output data
- Each agent type lives in its own subdirectory (development/, devops/, monitoring/)
