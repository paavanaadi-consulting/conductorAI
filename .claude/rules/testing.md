---
paths:
  - tests/**
---

# Testing Rules

- Use pytest markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`
- asyncio_mode is "auto" — do not add `@pytest.mark.asyncio` to async tests
- Test files mirror the source structure: `src/conductor/core/config.py` -> `tests/test_core/test_config.py`
- Use fixtures from `tests/conftest.py` for shared setup
- Prefer real objects over mocks when practical; mock external services (Redis, LLM APIs)
