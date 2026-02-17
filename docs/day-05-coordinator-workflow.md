# Day 5: Agent Coordinator & Workflow Engine

**Date**: Day 5 of 10-Day Build
**Components**: `AgentCoordinator`, `WorkflowEngine`, `PHASE_AGENT_TYPES`
**Tests**: 38 tests (20 coordinator + 18 workflow engine)
**Status**: ✅ Complete — 278 total tests passing

---

## Overview

Day 5 brings the two highest-level orchestration components: the **Agent Coordinator** (agent registry + task dispatch) and the **Workflow Engine** (multi-phase workflow execution). Together, they complete the Orchestration Layer — from this point forward, ConductorAI can register agents, dispatch tasks, execute multi-phase workflows, enforce policies, and handle errors.

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LAYER                       │
│                                                             │
│  ┌──────────────────────────────────────────┐              │
│  │         WorkflowEngine (Day 5)            │              │
│  │  run_workflow() → phase loop → results    │              │
│  └──────────────┬───────────────────────────┘              │
│                 │ dispatch_task()                            │
│  ┌──────────────▼───────────────────────────┐              │
│  │      AgentCoordinator (Day 5)             │              │
│  │  agent registry + dispatch + sync         │              │
│  └──┬──────────┬──────────┬─────────────┬──┘              │
│     │          │          │             │                    │
│  ┌──▼──┐  ┌──▼──────┐ ┌▼─────────┐ ┌▼──────────┐       │
│  │Msg  │  │State    │ │Policy    │ │Error      │       │
│  │Bus  │  │Manager  │ │Engine   │ │Handler    │       │
│  │(D3) │  │(D3)     │ │(D4)     │ │(D4)       │       │
│  └─────┘  └─────────┘ └─────────┘ └───────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## Agent Coordinator

### What It Does

The **AgentCoordinator** is the central nerve center for agent management. It owns the agent registry, handles task dispatch, and keeps the StateManager in sync.

**File**: `src/conductor/orchestration/agent_coordinator.py`

### Core Responsibilities

| Responsibility | Description |
|---|---|
| **Agent Registry** | Register/unregister agents with unique IDs |
| **Task Dispatch** | Find the best available agent and execute a task |
| **State Sync** | Persist agent state to StateManager after every change |
| **Policy Check** | Consult PolicyEngine before dispatching (optional) |
| **Error Routing** | Route failures to ErrorHandler (optional) |

### Task Dispatch Algorithm

The `dispatch_task()` method follows a strict pipeline:

```
dispatch_task(task)
   │
   ├─ 1. Check assigned_to type exists → NO_AGENT_TYPE error
   │
   ├─ 2. Find available agents (status == IDLE, matching type)
   │     └─ None available → NO_AVAILABLE_AGENT error
   │
   ├─ 3. Policy check (if PolicyEngine configured)
   │     └─ Fails → POLICY_VIOLATION error
   │
   ├─ 4. Execute via agent.execute_task(task)
   │     │
   │     ├─ Success → TaskResult(COMPLETED), sync state, save result
   │     │
   │     └─ Failure → BaseAgent catches & returns TaskResult(FAILED)
   │              └─ Coordinator saves the FAILED result normally
   │
   └─ 5. Return TaskResult to caller
```

### Agent Registration Flow

```python
await coordinator.register_agent(agent)
# 1. Check for duplicate agent_id → AGENT_ALREADY_REGISTERED
# 2. Start the agent (sets status to IDLE)
# 3. Add to internal registry dict
# 4. Persist initial state to StateManager
# 5. Log the registration

await coordinator.unregister_agent("coding-01")
# 1. Look up agent in registry → False if not found
# 2. Stop the agent (calls agent.stop())
# 3. Remove from registry
# 4. Delete from StateManager
```

### Query Methods

```python
# Lookup by ID
agent = coordinator.get_agent("coding-01")

# Filter by type
coding_agents = coordinator.get_agents_by_type(AgentType.CODING)

# Available (IDLE) agents, optionally filtered by type
available = coordinator.get_available_agents(AgentType.CODING)

# All registered agents
all_agents = coordinator.list_agents()

# Quick counts
count = coordinator.agent_count
is_running = coordinator.is_started
```

---

## Workflow Engine

### What It Does

The **WorkflowEngine** is the top-level orchestrator. It takes a `WorkflowDefinition` (phases + tasks) and executes it end-to-end, delegating task execution to the `AgentCoordinator`.

**File**: `src/conductor/orchestration/workflow_engine.py`

### Phase-to-Agent Type Mapping

The engine uses a static mapping to determine which agents belong to each phase:

```python
PHASE_AGENT_TYPES = {
    WorkflowPhase.DEVELOPMENT: {
        AgentType.CODING,      # Generates code
        AgentType.REVIEW,      # Reviews code
        AgentType.TEST_DATA,   # Generates test data
        AgentType.TEST,        # Runs tests
    },
    WorkflowPhase.DEVOPS: {
        AgentType.DEVOPS,      # CI/CD configuration
        AgentType.DEPLOYING,   # Deployment execution
    },
    WorkflowPhase.MONITORING: {
        AgentType.MONITOR,     # Monitors deployed services
    },
}
```

### Workflow Execution Flow

```
run_workflow(definition)
   │
   ├─ Create WorkflowState(status=IN_PROGRESS)
   │
   ├─ For each phase in definition.phases:
   │     │
   │     ├─ Filter tasks for this phase (PHASE_AGENT_TYPES mapping)
   │     │
   │     ├─ No tasks? → Record "skipped" in phase_history, continue
   │     │
   │     ├─ Execute each task via coordinator.dispatch_task()
   │     │     └─ Best-effort: failures recorded, execution continues
   │     │
   │     └─ Record phase completion in phase_history
   │
   ├─ All phases done → status = COMPLETED
   │
   └─ Exception → status = FAILED, error recorded in error_log
```

### Best-Effort Failure Strategy

The workflow engine uses a **best-effort** strategy for task failures:

1. If `dispatch_task()` raises an exception (e.g., NO_AVAILABLE_AGENT), the engine catches it, creates a FAILED TaskResult, adds it to `error_log`, and continues.
2. If `dispatch_task()` returns a FAILED result (BaseAgent caught the error), it's recorded normally in `task_results` — no error_log entry because no exception occurred.

This design ensures one failing task doesn't block the entire workflow.

### Feedback Loop

The Monitor Agent can trigger a feedback loop that re-executes the DEVELOPMENT phase:

```
MONITORING Phase
   │
   └─ Monitor detects issue
        │
        └─ trigger_feedback_loop(state, definition, feedback)
              │
              ├─ Check feedback_count < max_feedback_loops
              │     └─ Exceeded → WorkflowError("MAX_FEEDBACK_LOOPS")
              │
              ├─ Increment feedback_count
              ├─ Set current_phase = DEVELOPMENT
              └─ Re-execute DEVELOPMENT phase tasks
```

The loop limit prevents infinite cycles (default: 3 iterations).

### Phase Gate

Before advancing between phases, the engine can check a **phase gate**:

```python
# With PolicyEngine + PhaseGatePolicy registered
can_advance = await engine.check_phase_gate(state)
# Evaluates success rate of completed tasks against threshold
```

Without a PolicyEngine, the gate always passes.

---

## Design Decisions

### 1. BaseAgent Error Containment

**Decision**: BaseAgent catches non-AgentError exceptions and returns a FAILED TaskResult.

**Rationale**: The Template Method pattern in BaseAgent wraps raw exceptions into structured results. This means:
- The coordinator's `dispatch_task()` receives a FAILED result (no exception)
- The workflow engine records it in `task_results` without needing try/except
- Only AgentErrors (validation failures) and coordinator-level errors propagate as exceptions

This is a deliberate design choice: the **agent layer normalizes failures into data**, and the **orchestration layer decides what to do with failed results**.

### 2. Sequential Task Execution Within Phases

**Decision**: Tasks within a phase execute sequentially.

**Rationale**: This is the simplest correct approach for Day 5. Parallel execution within phases (using `asyncio.gather` or `TaskGroup`) is a Day 8-9 optimization. Sequential execution makes debugging easier and avoids concurrent state mutations.

### 3. Coordinator Owns State Sync

**Decision**: The coordinator syncs agent state after every change (register, dispatch, failure).

**Rationale**: Centralized state sync ensures consistency. Without it, each agent would need to know about the StateManager, breaking the separation of concerns.

### 4. Optional Dependencies

**Decision**: PolicyEngine and ErrorHandler are optional (can be None).

**Rationale**: This allows testing components in isolation. The coordinator works without policies (useful for tests), and the workflow engine works without a policy engine (skipping phase gates).

---

## Testing Summary

### Agent Coordinator Tests (20 tests)

| Category | Tests | What's Verified |
|---|---|---|
| Lifecycle | 2 | start(), stop() clears agents |
| Registration | 5 | register, duplicate rejection, state persistence, multi-agent, unregister |
| Queries | 4 | by ID, by type, available agents, list all |
| Task Dispatch | 8 | success, saves result, no type, no agent, FAILED result, state sync, policy, error handler |
| Validation | 1 | RejectingAgent raises TASK_VALIDATION_FAILED |

### Workflow Engine Tests (18 tests)

| Category | Tests | What's Verified |
|---|---|---|
| Phase Mapping | 3 | DEVELOPMENT, DEVOPS, MONITORING agent types |
| Single Phase | 2 | one task, multiple tasks |
| Multi Phase | 1 | two-phase sequential execution |
| Failure Handling | 2 | task failure recorded, no-agent failure |
| Empty Workflow | 2 | empty tasks, no matching tasks (skipped phase) |
| State Persistence | 1 | final state saved to StateManager |
| Phase Gate | 2 | without policy engine, with PhaseGatePolicy |
| Feedback Loop | 3 | trigger, max exceeded, count increment |
| Phase Filtering | 4 | CODING→DEV, DEVOPS→DEVOPS, empty, no match |

---

## Usage Examples

### Basic Workflow

```python
from conductor.orchestration import (
    AgentCoordinator,
    WorkflowEngine,
    InMemoryMessageBus,
    InMemoryStateManager,
)
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.core.enums import AgentType, WorkflowPhase

# Setup infrastructure
bus = InMemoryMessageBus()
sm = InMemoryStateManager()
await bus.connect()
await sm.connect()

# Create coordinator and register agents
coordinator = AgentCoordinator(bus, sm)
await coordinator.start()
await coordinator.register_agent(coding_agent)
await coordinator.register_agent(review_agent)

# Create workflow engine
engine = WorkflowEngine(coordinator, sm)

# Define and run workflow
definition = WorkflowDefinition(
    name="Build User Service",
    phases=[WorkflowPhase.DEVELOPMENT, WorkflowPhase.DEVOPS],
    tasks=[
        TaskDefinition(name="Generate API", assigned_to=AgentType.CODING),
        TaskDefinition(name="Review API", assigned_to=AgentType.REVIEW),
        TaskDefinition(name="Deploy", assigned_to=AgentType.DEVOPS),
    ],
)

state = await engine.run_workflow(definition)
print(f"Status: {state.status}")           # COMPLETED
print(f"Tasks: {state.completed_task_count}")  # 3
print(f"Phases: {len(state.phase_history)}")   # 2
```

### With Policies and Error Handling

```python
from conductor.orchestration import PolicyEngine, ErrorHandler

# Add policies
policy_engine = PolicyEngine()
policy_engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=10))
policy_engine.register_policy(PhaseGatePolicy(required_success_rate=0.8))

# Add error handler
error_handler = ErrorHandler(bus, sm)

# Create coordinator with all features
coordinator = AgentCoordinator(bus, sm, policy_engine, error_handler)

# Engine uses policy engine for phase gates
engine = WorkflowEngine(coordinator, sm, policy_engine, max_feedback_loops=5)
```

---

## Orchestration Layer Complete

With Day 5, the **entire Orchestration Layer** is now built:

| Component | Day | Purpose |
|---|---|---|
| MessageBus | 3 | Async pub/sub + request-response |
| StateManager | 3 | Agent/Workflow/TaskResult persistence |
| ErrorHandler | 4 | Retry, escalate, dead-letter, circuit breaker |
| PolicyEngine | 4 | Policy evaluation + enforcement |
| AgentCoordinator | 5 | Agent registry + task dispatch |
| WorkflowEngine | 5 | Multi-phase workflow execution |

**Next**: Day 6 starts the **Agent Layer** — building the first specialized agents (CodingAgent, ReviewAgent) that plug into this orchestration infrastructure.
