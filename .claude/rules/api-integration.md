---
paths:
  - src/conductor/integrations/**
---

# Integration Rules

- LLM providers implement the base interface in `integrations/llm/base.py`
- Use the factory pattern (`integrations/llm/factory.py`) to create provider instances
- Use httpx for all async HTTP calls
- Never hardcode API keys — use environment variables or the secrets infrastructure
