# ConductorAI

**A Multi-Agent AI Framework for Orchestrating Specialized AI Agents**

ConductorAI orchestrates AI agents through a complete software development lifecycle:

```
Code → Review → Test → Deploy → Monitor → Feedback Loop
```

## Architecture

```
┌──────────────────── ORCHESTRATION LAYER ─────────────────────┐
│ Workflow Engine │ Coordinator │ Message Bus │ State Manager   │
│ Policy Engine   │ Error Handler                               │
├──────────────────── AGENT LAYER ─────────────────────────────┤
│ DEVELOPMENT          │ DEVOPS          │ MONITORING           │
│ Coding → Review      │ DevOps →        │ Monitor Agent        │
│ TestData → Test      │ Deploying       │ (feedback loop)      │
├──────────────────── DATA & INFRASTRUCTURE ───────────────────┤
│ Code Repo │ Metadata │ Test Data │ Logs/Metrics │ Knowledge  │
├──────────────────── INTEGRATIONS ────────────────────────────┤
│ LLMs │ Cloud │ Containers │ CI/CD │ Notifications            │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone and install
git clone <repository-url>
cd conductorAI
pip install -e ".[dev]"

# Run tests
pytest

# Run an example (available after Day 10)
python examples/full_workflow.py
```

## Project Structure

```
conductorAI/
├── src/conductor/           # Source code
│   ├── core/                # Config, enums, models, exceptions
│   ├── orchestration/       # Workflow, coordinator, message bus, state
│   ├── agents/              # Base + specialized agents
│   │   ├── development/     # Coding, Review, TestData, Test agents
│   │   ├── devops/          # DevOps, Deploying agents
│   │   └── monitoring/      # Monitor agent
│   ├── infrastructure/      # Storage, repositories, observability
│   └── integrations/        # LLM providers, notifications, CI/CD
├── tests/                   # Comprehensive test suite
├── docs/                    # Full documentation
├── examples/                # Working examples
├── pyproject.toml           # Project config and dependencies
└── conductor.yaml           # Runtime configuration
```

## Build Progress

This project is built incrementally, a few components per day:

| Day | Components | Status |
|-----|-----------|--------|
| 1 | Config, Enums, Models, Exceptions | ✅ Complete (52 tests) |
| 2 | BaseAgent, Messages, State | ✅ Complete (116 tests) |
| 3 | Message Bus, State Manager | ✅ Complete (166 tests) |
| 4 | Error Handler, Policy Engine | ✅ Complete (237 tests) |
| 5 | Agent Coordinator, Workflow Engine | ✅ Complete (278 tests) |
| 6 | LLM Provider, Coding Agent, Review Agent | ✅ Complete (381 tests) |
| 7 | TestDataAgent, TestAgent, DevOpsAgent, DeployingAgent | ✅ Complete (504 tests) |
| 8 | MonitorAgent, ArtifactStore, Feedback Loop | ✅ Complete (569 tests) |
| 9 | ConductorAI Facade, Public API | ✅ Complete (591 tests) |
| 10 | End-to-End Examples, Full Docs | Pending |

## Documentation

All documentation is in the `docs/` folder:

- [Documentation Index](docs/README.md)
- [Architecture Overview](docs/architecture-overview.md)
- [Day 01: Foundations](docs/day-01-foundations.md)

## Tech Stack

- **Python 3.11+** with async/await
- **Pydantic v2** for data validation
- **Redis** for message bus and state persistence
- **httpx** for async HTTP (LLM APIs)
- **structlog** for structured logging
- **pytest** for testing

## License

MIT
