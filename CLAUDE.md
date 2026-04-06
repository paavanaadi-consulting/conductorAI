# ConductorAI - Claude Code Instructions

## Project Overview

ConductorAI is a multi-agent AI framework for orchestrating specialized agents through Development, DevOps, and Monitoring pipelines. Python 3.11+, async-first, src layout.

## Build & Run

```bash
pip install -e ".[dev]"       # Install with dev deps
pytest --cov=conductor -q     # Run all tests with coverage
pytest -m unit -q             # Unit tests only
pytest -m integration -q      # Integration tests only
ruff check src/ tests/        # Lint
ruff format src/ tests/       # Format
mypy src/conductor/           # Type check
```

## Architecture

- **src/conductor/core/** - Config, enums, models, exceptions, messages, state, RBAC
- **src/conductor/orchestration/** - Workflow engine, coordinator, message bus, state manager, policy engine, error handler
- **src/conductor/agents/** - Base agent + specialized agents (development, devops, monitoring, pipeline)
- **src/conductor/infrastructure/** - Artifact store, metrics, tracing, health, secrets
- **src/conductor/integrations/llm/** - LLM providers (Anthropic, OpenAI, mock) with factory pattern
- **src/conductor/facade.py** - Public API facade (ConductorAI entry point)

## Key Patterns

- **Pydantic v2** for all models and validation
- **async/await** throughout — all agents and orchestration are async
- **src layout** — package is at `src/conductor/`, imported as `conductor`
- **structlog** for structured logging
- **Redis** for message bus (pub/sub) and state persistence
- Test markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`
- asyncio_mode = "auto" in pytest (no need for `@pytest.mark.asyncio`)

## Conventions

- Line length: 100 chars
- Imports sorted with isort rules via ruff
- Type annotations required on all function signatures (mypy strict)
- Errors use custom exception hierarchy in `core/exceptions.py`
- Agent communication via message bus, not direct calls
