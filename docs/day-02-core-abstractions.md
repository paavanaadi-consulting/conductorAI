# Day 02: Core Abstractions — BaseAgent, Messages, State

## What Was Built

Day 2 defines the dynamic runtime abstractions that bring the static models
from Day 1 to life:

- **AgentMessage**: The universal communication envelope for the Message Bus
- **AgentState / WorkflowState**: Dynamic state models for tracking runtime behavior
- **BaseAgent**: The abstract base class all 7 specialized agents inherit from

### Files Created

```
src/conductor/core/messages.py         # AgentMessage + typed payloads
src/conductor/core/state.py            # AgentState + WorkflowState
src/conductor/agents/__init__.py       # Agent package initialization
src/conductor/agents/base.py           # BaseAgent abstract class
tests/test_core/test_messages.py       # Message tests
tests/test_core/test_state.py          # State model tests
tests/test_agents/__init__.py          # Agent test package
tests/test_agents/test_base_agent.py   # BaseAgent tests (using MockAgent)
docs/day-02-core-abstractions.md       # This documentation
```

## Agent Communication: Messages

All agent communication flows through the Message Bus using `AgentMessage`:

```
┌──────────────────────────────────────────────────────┐
│  AgentMessage                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ message_type  │  │  sender_id   │  │ recipient  │ │
│  │ (what kind)   │  │ (who sent)   │  │ (who gets) │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │   payload     │  │ correlation  │  │  priority   │ │
│  │ (the data)    │  │ (thread ID)  │  │ (urgency)  │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Typed Payloads

Rather than unstructured dicts, we have typed payload models:

| Payload | Used For | Key Fields |
|---------|----------|------------|
| `TaskAssignmentPayload` | Coordinator → Agent | task (TaskDefinition) |
| `TaskResultPayload` | Agent → Coordinator | result (TaskResult) |
| `FeedbackPayload` | Monitor → Coordinator | findings, severity, recommendations |
| `ErrorPayload` | Any → ErrorHandler | error_code, error_message, traceback |
| `StatusUpdatePayload` | Agent → All | status, progress_percent |

### Request-Response Pattern

Messages support request-response via `correlation_id`:

```python
# Coordinator sends request
request = AgentMessage(
    message_type=MessageType.TASK_ASSIGNMENT,
    sender_id="coordinator",
    recipient_id="coding-01",
    payload=assignment.model_dump(),
)

# Agent creates linked response
response = request.create_response(
    sender_id="coding-01",
    message_type=MessageType.TASK_RESULT,
    payload=result_payload.model_dump(),
)
# response.correlation_id == request.message_id  ← linked!
```

## State Models

### AgentState vs. AgentIdentity

```
AgentIdentity (Day 1)          AgentState (Day 2)
├── agent_id: "coding-01"      ├── agent_id: "coding-01"
├── agent_type: CODING          ├── agent_type: CODING
├── name: "Primary Coder"      ├── status: RUNNING ←── changes!
└── version: "0.1.0"           ├── current_task_id: "t1" ←── changes!
    (static, never changes)     ├── completed_tasks: [...]
                                ├── error_count: 0
                                └── last_heartbeat: 14:30
                                    (dynamic, changes constantly)
```

### WorkflowState Tracks Everything

WorkflowState is the "master record" that aggregates all state:

```python
WorkflowState(
    workflow_id="wf-123",
    current_phase=WorkflowPhase.DEVOPS,           # Where we are
    phase_history=[{"phase": "development", ...}],  # Where we've been
    agent_states={"coding-01": ..., "review-01": ...},  # Agent snapshots
    task_results={"t1": ..., "t2": ...},            # All results so far
    status=TaskStatus.IN_PROGRESS,
    feedback_count=0,                               # Feedback loop counter
)
```

## BaseAgent: Template Method Pattern

The most important design pattern in the agent layer:

```
┌─────────────────────────────────────────────────────────┐
│  BaseAgent.execute_task(task)       ← You call this     │
│  ┌────────────────────────────────────────────────────┐ │
│  │ 1. _validate_task(task)   ← Subclass overrides     │ │
│  │ 2. Set status → RUNNING                            │ │
│  │ 3. _execute(task)         ← Subclass overrides     │ │
│  │ 4. Set status → COMPLETED/FAILED                   │ │
│  │ 5. Return TaskResult                                │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  BaseAgent handles: lifecycle, timing, error catching    │
│  Subclass handles: actual work (LLM calls, etc.)        │
└─────────────────────────────────────────────────────────┘
```

### Creating a New Agent

```python
class MyCoolAgent(BaseAgent):
    async def _validate_task(self, task):
        # Check task has required input
        return "specification" in task.input_data

    async def _execute(self, task):
        # Do the actual work
        result_data = do_something(task.input_data["specification"])
        return self._create_result(
            task.task_id, TaskStatus.COMPLETED,
            {"output": result_data},
        )
```

That's it. BaseAgent handles status transitions, timing, error catching,
and state management automatically.

## Running Tests

```bash
# Run Day 2 tests
pytest tests/test_core/test_messages.py tests/test_core/test_state.py tests/test_agents/test_base_agent.py -v

# Run all tests (Day 1 + Day 2)
pytest tests/ -v
```

## What's Next (Day 3)

Day 3 builds the **Message Bus and State Manager** — the two orchestration
components that connect agents to each other and persist their state:
- `MessageBus` (abstract + InMemory + Redis implementations)
- `StateManager` (abstract + InMemory + Redis implementations)
