# Day 01: Foundations — Project Scaffolding, Config, Base Models

## What Was Built

Day 1 establishes the project skeleton and foundational types that every
other module depends on. Nothing in Day 1 has business logic — it's pure
data structures and configuration.

### Files Created

```
conductorAI/
├── pyproject.toml                      # Project metadata, dependencies, tool configs
├── conductor.yaml                      # Example configuration file
├── src/conductor/
│   ├── __init__.py                     # Package version, top-level docstring
│   └── core/
│       ├── __init__.py                 # Re-exports for convenient importing
│       ├── config.py                   # ConductorConfig, RedisConfig, LLMConfig
│       ├── enums.py                    # AgentType, AgentStatus, WorkflowPhase, etc.
│       ├── models.py                   # AgentIdentity, TaskDefinition, TaskResult
│       └── exceptions.py              # ConductorError hierarchy
├── tests/
│   ├── __init__.py
│   └── test_core/
│       ├── __init__.py
│       ├── test_config.py             # Config loading, validation, env var tests
│       └── test_models.py             # Model creation, serialization, validation
├── docs/
│   ├── README.md                       # Documentation index
│   ├── architecture-overview.md        # Full architecture description
│   └── day-01-foundations.md           # This file
└── README.md                           # Project README
```

## Why These Components First?

The dependency rule in ConductorAI is simple:

```
core/ depends on NOTHING in the conductor package.
Everything else depends on core/.
```

By building `core/` first, we create a stable foundation that won't change
as we add agents, orchestration, and integrations in later days.

## Component Details

### Configuration System (`config.py`)

The configuration system uses **Pydantic Settings** for type-safe config
with automatic environment variable loading:

```python
# Zero-config startup (all defaults)
config = ConductorConfig()

# Override via environment variables
# CONDUCTOR_LOG_LEVEL=DEBUG
# CONDUCTOR_LLM__PROVIDER=openai

# Override via YAML file
config = load_config("conductor.yaml")

# Override via constructor
config = ConductorConfig(environment="prod", log_level="WARNING")
```

**Key Design Decision**: We use `BaseSettings` (not `BaseModel`) for the
top-level config. This automatically reads `CONDUCTOR_*` environment variables,
which is standard for 12-factor app deployment.

**Nested configs** use double underscores in env vars:
```
CONDUCTOR_REDIS__URL=redis://prod:6379/0  →  config.redis.url
CONDUCTOR_LLM__API_KEY=sk-xxx            →  config.llm.api_key
```

### Enumerations (`enums.py`)

All enums are `str` + `Enum` hybrids:

```python
class AgentType(str, Enum):
    CODING = "coding"
```

This design means:
- JSON serialization produces strings: `"coding"` (not `"AgentType.CODING"`)
- String comparison works: `AgentType.CODING == "coding"` → `True`
- Pydantic automatically validates: `AgentType("invalid")` → `ValueError`

### Data Models (`models.py`)

Four core models define the data contract for the entire system:

| Model | Purpose | Used By |
|-------|---------|---------|
| `AgentIdentity` | Who is this agent? | Agent registration, logging |
| `TaskDefinition` | What needs to be done? | Workflow engine → Agent |
| `TaskResult` | What happened? | Agent → Workflow engine |
| `WorkflowDefinition` | Full pipeline plan | User → Workflow engine |

**Key Design Decision**: `input_data` and `output_data` are `dict[str, Any]`.
We intentionally keep these flexible because each agent type needs different
data. Type-specific validation happens inside each agent's `_validate_task()`.

### Exception Hierarchy (`exceptions.py`)

```
ConductorError (base)
├── ConfigurationError     → Invalid config (fail fast at startup)
├── AgentError             → Agent execution failures (retryable)
├── WorkflowError          → Workflow orchestration failures
├── MessageBusError        → Communication infrastructure failures
├── StateError             → State persistence failures
└── PolicyViolationError   → Policy rule violations (blocked actions)
```

Every exception carries:
- `message`: Human-readable description
- `error_code`: Machine-readable code (e.g., `"LLM_API_ERROR"`)
- `details`: Arbitrary dict with debugging context

This enables the Error Handler (Day 4) to make programmatic decisions:
```python
if error.error_code in RETRYABLE_ERRORS:
    retry_task(task)
else:
    escalate(error)
```

## Design Decisions & Tradeoffs

### Decision 1: Pydantic v2 for All Models

**Chosen**: Pydantic v2 with `BaseModel` for all data types.

**Why**: Automatic validation, JSON serialization, IDE hints, and documentation.
Pydantic v2 is also 5-17x faster than v1.

**Tradeoff**: Adds a dependency. But Pydantic is the de facto standard for
Python data validation, so this is a very safe bet.

### Decision 2: `str` Enums (not `int`)

**Chosen**: All enums use `str` values like `"coding"`, `"running"`.

**Why**: Human-readable in logs, JSON, and Redis keys. Easier to debug.

**Tradeoff**: Slightly more storage than int enums, but negligible.

### Decision 3: UUID4 for All Identifiers

**Chosen**: Auto-generated UUID4 strings for all IDs.

**Why**: Globally unique without a central ID service. Safe for distributed
systems.

**Tradeoff**: UUIDs are long (36 chars). We accept this for the uniqueness
guarantee.

## How to Run Tests

```bash
# Install the package in development mode
pip install -e ".[dev]"

# Run Day 1 tests
pytest tests/test_core/ -v

# Run with coverage
pytest tests/test_core/ --cov=conductor.core --cov-report=term-missing
```

## What's Next (Day 2)

Day 2 builds the **Core Abstractions**:
- `AgentMessage` — How agents communicate
- `AgentState` / `WorkflowState` — Dynamic state tracking
- `BaseAgent` — The abstract base class all 7 agents inherit from

These abstractions connect the static data models from Day 1 with the
dynamic agent system that gets built in later days.
