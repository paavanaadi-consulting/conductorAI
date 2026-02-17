# Day 3: Message Bus and State Manager

## Overview

Day 3 builds the **communication and persistence infrastructure** for ConductorAI.
These two components sit at the heart of the orchestration layer:

- **Message Bus** — the communication backbone (pub/sub + request-response)
- **State Manager** — the persistent storage layer (agent states, workflow states, task results)

Together, they enable agents to communicate without direct coupling and persist
their state across operations.

## Architecture Context

```
                     ┌─────────────────────────────────────┐
                     │         Orchestration Layer          │
                     │                                     │
                     │  ┌─────────────┐  ┌──────────────┐  │
                     │  │ Message Bus │  │ State Manager│  │
                     │  │ (Pub/Sub +  │  │ (Agent +     │  │
                     │  │  Request/   │  │  Workflow +  │  │
                     │  │  Response)  │  │  TaskResult) │  │
                     │  └──────┬──────┘  └──────┬───────┘  │
                     │         │                │          │
                     └─────────┼────────────────┼──────────┘
                               │                │
                     ┌─────────▼────────────────▼──────────┐
                     │            Agent Layer               │
                     │  Coding │ Review │ Test │ DevOps ... │
                     └─────────────────────────────────────┘
```

**Why separate Message Bus from State Manager?**

| Concern          | Message Bus              | State Manager              |
|------------------|--------------------------|----------------------------|
| Access pattern   | Write-heavy (publish)    | Read-heavy (get)           |
| Durability       | Transient (fire-forget)  | Must persist               |
| Backend          | Redis Pub/Sub            | Redis Hashes/Strings       |
| Coupling         | Async, decoupled         | Synchronous reads          |

## Files Created / Modified

| File | Description |
|------|-------------|
| `src/conductor/orchestration/__init__.py` | Package init with re-exports |
| `src/conductor/orchestration/message_bus.py` | MessageBus ABC + InMemoryMessageBus + RedisMessageBus stub |
| `src/conductor/orchestration/state_manager.py` | StateManager ABC + InMemoryStateManager |
| `tests/test_orchestration/__init__.py` | Test package init |
| `tests/test_orchestration/test_message_bus.py` | 21 tests covering pub/sub, request-response, lifecycle |
| `tests/test_orchestration/test_state_manager.py` | 24 tests covering CRUD for all 3 entity types |

## Component Deep Dive

### Message Bus (`message_bus.py`)

The Message Bus supports two communication patterns:

#### 1. Pub/Sub (Fire-and-Forget)

```python
# Publisher sends to a channel; all subscribers receive it
bus = InMemoryMessageBus()
await bus.connect()

async def handler(msg: AgentMessage) -> None:
    print(f"Received: {msg.message_type}")

await bus.subscribe("conductor:agent:coding-01", handler)

msg = AgentMessage(
    message_type=MessageType.TASK_ASSIGNMENT,
    sender_id="coordinator",
)
await bus.publish("conductor:agent:coding-01", msg)
```

#### 2. Request-Response (Synchronous over Async)

```python
# Coordinator sends task and waits for result
async def agent_handler(msg: AgentMessage) -> None:
    response = msg.create_response(
        sender_id="coding-01",
        message_type=MessageType.TASK_RESULT,
        payload={"code": "generated_code_here"},
    )
    await bus.publish("conductor:response", response)

await bus.subscribe("conductor:agent:coding-01", agent_handler)

response = await bus.request(
    "conductor:agent:coding-01",
    request_msg,
    timeout=30.0,
)
```

#### Channel Naming Convention

| Channel Pattern | Use Case | Example |
|----------------|----------|---------|
| `conductor:agent:{id}` | Direct message to agent | `conductor:agent:coding-01` |
| `conductor:broadcast` | Broadcast to all | System announcements |
| `conductor:phase:{name}` | Phase-scoped messages | `conductor:phase:development` |
| `conductor:workflow:{id}` | Workflow-scoped messages | `conductor:workflow:wf-abc` |
| `conductor:dlq` | Dead letter queue | Failed message storage |

#### Key Design Decisions

1. **Correlation-based request-response**: The `request()` method uses `asyncio.Future` keyed by `correlation_id`. When a response with a matching `correlation_id` is published, the Future resolves.

2. **Self-resolution guard**: The `publish()` method skips resolving a Future when the message being published IS the original request (detected by `correlation_id == message_id`). This prevents the request from resolving with itself instead of waiting for the actual response.

3. **Callback error isolation**: A failing subscriber callback does NOT prevent other subscribers from receiving the message, and does NOT propagate to the publisher.

4. **Expired message filtering**: Messages past their TTL are silently dropped in `publish()`.

### State Manager (`state_manager.py`)

The State Manager provides CRUD operations for three entity types:

| Entity | Key Pattern | Use Case |
|--------|-------------|----------|
| `AgentState` | `agent:{agent_id}` | Per-agent lifecycle tracking |
| `WorkflowState` | `workflow:{workflow_id}` | Per-workflow aggregate state |
| `TaskResult` | `task_result:{task_id}` | Per-task execution results |

```python
sm = InMemoryStateManager()
await sm.connect()

# Agent state
await sm.save_agent_state(agent_state)
state = await sm.get_agent_state("coding-01")
all_states = await sm.list_agent_states()
deleted = await sm.delete_agent_state("coding-01")

# Workflow state
await sm.save_workflow_state(workflow_state)
wf = await sm.get_workflow_state("wf-01")

# Task results
await sm.save_task_result(task_result)
result = await sm.get_task_result("task-01")

await sm.disconnect()
```

#### Key Design Decisions

1. **Last-write-wins**: Saving with the same ID overwrites the previous value. No versioning or conflict resolution.
2. **Disconnect clears all state**: The InMemory implementation clears all stored data on disconnect, preventing stale data across sessions.
3. **Entity isolation**: Agent states, workflow states, and task results use independent storage dicts, so IDs can overlap without conflict.

## Class Hierarchy

```
MessageBus (ABC)
├── InMemoryMessageBus   ← Development/Testing
└── RedisMessageBus      ← Production (stub)

StateManager (ABC)
├── InMemoryStateManager ← Development/Testing
└── (Future) RedisStateManager ← Production
```

## Test Results

```
166 tests passed, 0 failed

Message Bus Tests (21):
  - ABC conformance
  - Basic pub/sub (publish, subscribe, delivery)
  - No-subscriber publish (fire-and-forget)
  - Multiple subscribers (fan-out)
  - Unsubscribe (channel-based removal, isolation, idempotent)
  - Channel isolation (multiple channels)
  - Request-response (correlation, priority inheritance)
  - Request timeout (MessageBusError with error code)
  - Auto correlation_id setting
  - Connect/disconnect lifecycle (reset, cleanup)
  - Not-connected guards (publish, subscribe, unsubscribe, request)
  - Message count tracking
  - Expired message filtering (TTL)
  - Callback error isolation
  - Disconnect cancels pending requests

State Manager Tests (24):
  - ABC conformance
  - Agent state CRUD (save, get, delete, list)
  - Missing key returns None
  - Overwrite behavior (last-write-wins)
  - Multiple entity independence
  - Workflow state CRUD (save, get)
  - Task result CRUD (save, get)
  - Connection lifecycle (connect, disconnect, idempotent)
  - Entity type isolation
  - Rich data persistence (task history, nested models)
```

## What's Next (Day 4)

Day 4 adds **Error Handler** and **Policy Engine**:

- `error_handler.py` — RetryPolicy, CircuitBreaker, ErrorHandler (retry, escalate, dead letter queue)
- `policy_engine.py` — Policy ABC, PolicyEngine, built-in policies (MaxConcurrentTasks, TaskTimeout, PhaseGate)
