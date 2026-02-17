# Day 9: ConductorAI Facade

## Overview

Day 9 delivers the crown jewel of the framework — the **ConductorAI facade**,
the single entry point that ties together every layer built over the previous
eight days into a clean, easy-to-use API.

```
┌──────────────────────────────────────────────────┐
│              ConductorAI (Facade)                 │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │         Orchestration Layer                   │ │
│  │  WorkflowEngine, Coordinator, MessageBus     │ │
│  │  StateManager, PolicyEngine, ErrorHandler    │ │
│  └─────────────────────┬───────────────────────┘ │
│                        │                          │
│  ┌─────────────────────▼───────────────────────┐ │
│  │            Agent Layer                        │ │
│  │  CodingAgent, ReviewAgent, TestAgent, etc.   │ │
│  └─────────────────────┬───────────────────────┘ │
│                        │                          │
│  ┌─────────────────────▼───────────────────────┐ │
│  │         Infrastructure Layer                  │ │
│  │  ArtifactStore, (Storage, Repos, ...)         │ │
│  └─────────────────────┬───────────────────────┘ │
│                        │                          │
│  ┌─────────────────────▼───────────────────────┐ │
│  │         Integration Layer                     │ │
│  │  LLM Providers, Notifications                 │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

## Components Built

### 1. ConductorAI Facade (`facade.py`)

The top-level facade that manages the lifecycle of all internal components.

**Design Pattern:** This is a classic **Facade Pattern** — it provides a
simplified interface to a complex subsystem. Users never need to wire
internal components together manually.

**Constructor:**
```python
class ConductorAI:
    def __init__(
        self,
        config: Optional[ConductorConfig] = None,
        *,
        message_bus: Optional[MessageBus] = None,
        state_manager: Optional[StateManager] = None,
        artifact_store: Optional[ArtifactStore] = None,
        error_handler: Optional[ErrorHandler] = None,
        policy_engine: Optional[PolicyEngine] = None,
        max_feedback_loops: int = 3,
    ) -> None:
```

All parameters are optional — ConductorAI creates sensible defaults
(InMemory implementations) when nothing is provided. This makes it
zero-configuration for development and testing.

**Lifecycle Management:**
| Method | Description |
|--------|-------------|
| `initialize()` | Starts MessageBus, StateManager, Coordinator. Idempotent. |
| `shutdown()` | Stops Coordinator, disconnects StateManager and MessageBus. Idempotent. |
| `async with ConductorAI() as c:` | Context manager that calls init/shutdown automatically |

**Initialization Order:**
1. Connect MessageBus (communication layer must be ready first)
2. Connect StateManager (state persistence must be ready)
3. Start Coordinator (depends on both MessageBus and StateManager)

**Shutdown Order (reverse):**
1. Stop Coordinator (stops all registered agents)
2. Disconnect StateManager
3. Disconnect MessageBus

**Agent Management:**
| Method | Description |
|--------|-------------|
| `register_agent(agent)` | Registers and starts an agent via the Coordinator |
| `unregister_agent(agent_id)` | Stops and removes an agent from the Coordinator |

Both methods require initialization — calling without `initialize()` raises
`RuntimeError`.

**Workflow Execution:**
| Method | Description |
|--------|-------------|
| `run_workflow(definition)` | Executes a multi-phase workflow through the WorkflowEngine |
| `dispatch_task(task)` | Dispatches a single task to an appropriate agent |

`run_workflow()` is the primary method. It delegates to the WorkflowEngine
which handles phase iteration, task dispatch, phase gate checks, feedback
loops, and state persistence.

`dispatch_task()` is a convenience method for one-off tasks without a full
workflow — useful for debugging or simple agent interactions.

**Artifact Management:**
| Method | Description |
|--------|-------------|
| `save_artifact(artifact)` | Saves an artifact to the ArtifactStore |
| `get_artifact(artifact_id)` | Retrieves an artifact by ID |
| `get_workflow_artifacts(workflow_id)` | Gets all artifacts for a workflow |

**Property Access:**
All internal components are accessible via read-only properties:
- `config` — ConductorConfig
- `coordinator` — AgentCoordinator
- `workflow_engine` — WorkflowEngine
- `message_bus` — MessageBus
- `state_manager` — StateManager
- `artifact_store` — ArtifactStore
- `error_handler` — ErrorHandler
- `policy_engine` — PolicyEngine
- `is_initialized` — bool

### 2. Public Package API (`__init__.py`)

The top-level `conductor` package now exports ConductorAI:
```python
from conductor.facade import ConductorAI

__all__ = ["ConductorAI", "__version__"]
```

This means users can simply write:
```python
from conductor import ConductorAI
```

## Usage Examples

### Basic Usage with Context Manager
```python
from conductor import ConductorAI
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.agents import CodingAgent, ReviewAgent
from conductor.integrations.llm.mock import MockLLMProvider

# Create with defaults (zero configuration)
async with ConductorAI() as conductor:
    # Register agents
    provider = MockLLMProvider()
    await conductor.register_agent(CodingAgent("coder-01", config, llm_provider=provider))
    await conductor.register_agent(ReviewAgent("reviewer-01", config, llm_provider=provider))

    # Run a workflow
    workflow = WorkflowDefinition(
        name="Feature Implementation",
        phases=[WorkflowPhase.DEVELOPMENT],
        tasks=[
            TaskDefinition(
                name="Generate API",
                assigned_to=AgentType.CODING,
                input_data={"specification": "REST API for users", "language": "python"},
            ),
        ],
    )
    state = await conductor.run_workflow(workflow)
    print(f"Workflow completed with status: {state.status}")
```

### Manual Lifecycle Management
```python
conductor = ConductorAI(ConductorConfig())

# Manual lifecycle
await conductor.initialize()

try:
    await conductor.register_agent(my_agent)
    state = await conductor.run_workflow(my_workflow)
finally:
    await conductor.shutdown()
```

### Single Task Dispatch
```python
async with ConductorAI() as conductor:
    await conductor.register_agent(coding_agent)

    # Dispatch a single task (no workflow needed)
    result = await conductor.dispatch_task(
        TaskDefinition(
            name="Quick Code Gen",
            assigned_to=AgentType.CODING,
            input_data={"specification": "Hello World", "language": "python"},
        )
    )
    print(f"Result: {result.status}, Agent: {result.agent_id}")
```

### Artifact Management
```python
from conductor.infrastructure.artifact_store import Artifact

async with ConductorAI() as conductor:
    # Save an artifact
    artifact = Artifact(
        workflow_id="wf-001",
        task_id="task-abc",
        agent_id="coding-01",
        artifact_type="code",
        content="def hello(): return 'Hello!'",
    )
    await conductor.save_artifact(artifact)

    # Retrieve it
    retrieved = await conductor.get_artifact(artifact.artifact_id)
    print(f"Content: {retrieved.content}")

    # Get all artifacts for a workflow
    all_artifacts = await conductor.get_workflow_artifacts("wf-001")
    print(f"Total artifacts: {len(all_artifacts)}")
```

### Custom Components (Dependency Injection)
```python
from conductor.orchestration.message_bus import InMemoryMessageBus
from conductor.orchestration.state_manager import InMemoryStateManager
from conductor.infrastructure.artifact_store import InMemoryArtifactStore

conductor = ConductorAI(
    config=ConductorConfig(),
    message_bus=InMemoryMessageBus(),        # Custom message bus
    state_manager=InMemoryStateManager(),    # Custom state manager
    artifact_store=InMemoryArtifactStore(),  # Custom artifact store
    max_feedback_loops=5,                    # Allow more feedback iterations
)
```

## Design Decisions

### 1. Facade Pattern
The ConductorAI class uses the Facade pattern to hide the complexity of
wiring together 8+ internal components. Without the facade, users would
need to manually create and connect:
- MessageBus, StateManager, ErrorHandler, PolicyEngine
- AgentCoordinator (depends on all 4 above)
- WorkflowEngine (depends on Coordinator, StateManager, PolicyEngine)
- ArtifactStore

The facade reduces this to a single constructor call.

### 2. Optional Dependency Injection
All internal components are optional constructor parameters with sensible
defaults. This enables:
- **Zero-config for dev/test** — just `ConductorAI()` with no arguments
- **Full customization for production** — inject Redis-backed implementations
- **Testing** — inject mocks for any component

### 3. Idempotent Lifecycle Methods
Both `initialize()` and `shutdown()` are idempotent — safe to call
multiple times. This prevents errors from:
- Double-initialization
- Double-shutdown
- Shutdown without initialization

### 4. Guard Clause Pattern
All public methods that require initialization use `_ensure_initialized()`,
which raises a clear `RuntimeError` with instructions on how to fix:
```
RuntimeError: ConductorAI has not been initialized.
Call await conductor.initialize() or use 'async with ConductorAI() as conductor:'
```

### 5. Async Context Manager
The `async with` pattern is the recommended usage because it guarantees
cleanup even if an exception occurs. The `__aexit__` method always calls
`shutdown()`, preventing resource leaks.

## Package Structure

```
src/conductor/
├── __init__.py              # Exports ConductorAI (updated Day 9)
├── facade.py                # Day 9 ← NEW (ConductorAI facade)
├── core/                    # Days 1-2
├── orchestration/           # Days 3-5
├── agents/                  # Days 6-8
│   ├── development/         # CodingAgent, ReviewAgent, TestDataAgent, TestAgent
│   ├── devops/              # DevOpsAgent, DeployingAgent
│   └── monitoring/          # MonitorAgent
├── infrastructure/          # Day 8
└── integrations/            # Day 6
    └── llm/                 # BaseLLMProvider, MockLLMProvider, OpenAIProvider
```

## Test Coverage

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_facade.py` | 22 | Init, shutdown, context manager, agents, workflow, tasks, artifacts, properties |
| **Day 9 Total** | **22** | |
| **Cumulative** | **591** | |

### Test Breakdown

| Test Class | Tests | What It Verifies |
|------------|-------|------------------|
| `TestConductorAIInit` | 6 | Default/custom init, initialize, shutdown, idempotency |
| `TestConductorAIContextManager` | 3 | async with enter/exit, self-return |
| `TestConductorAIAgentManagement` | 3 | Register single/multiple agents, uninitialized error |
| `TestConductorAIWorkflow` | 2 | Simple workflow execution, uninitialized error |
| `TestConductorAITaskDispatch` | 2 | Single task dispatch, uninitialized error |
| `TestConductorAIArtifacts` | 3 | Save/get artifact, workflow artifacts |
| `TestConductorAIProperties` | 3 | Property access, custom stores, repr |

## Component Wiring Summary

Here's how ConductorAI wires all internal components:

```
ConductorAI.__init__()
│
├── config = ConductorConfig()
│
├── artifact_store = InMemoryArtifactStore()
│
├── message_bus = InMemoryMessageBus()
│
├── state_manager = InMemoryStateManager()
│
├── error_handler = ErrorHandler(message_bus, state_manager)
│
├── policy_engine = PolicyEngine()
│
├── coordinator = AgentCoordinator(
│       message_bus, state_manager, policy_engine, error_handler)
│
└── workflow_engine = WorkflowEngine(
        coordinator, state_manager, policy_engine, max_feedback_loops)
```

## What's Next (Day 10)

Day 10 will add:
- **End-to-End Examples** — Full Dev->DevOps->Monitor workflow example
- **Integration Tests** — Complete system test with all agents
- **Full Documentation** — Getting Started, API Reference, Extension Guide
- **Polish** — Final README, conftest fixtures, code cleanup
