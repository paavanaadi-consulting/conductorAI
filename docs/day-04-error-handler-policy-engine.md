# Day 4: Error Handler and Policy Engine

## Overview

Day 4 adds the **resilience and governance layers** to ConductorAI:

- **Error Handler** — decides what to do when agents fail (retry, escalate, dead-letter)
- **Policy Engine** — evaluates rules before actions are taken (concurrency, timeouts, phase gates)

Together, they make the system robust and controllable.

## Architecture Context

```
    ┌──────────────────────────────────────────────────────────────────┐
    │                      Orchestration Layer                         │
    │                                                                  │
    │  ┌──────────────┐      ┌────────────────┐     ┌──────────────┐ │
    │  │   Policy      │      │  Error          │     │  Message     │ │
    │  │   Engine      │      │  Handler        │     │  Bus         │ │
    │  │  ┌──────────┐ │      │  ┌───────────┐  │     └──────────────┘ │
    │  │  │Policy 1  │ │      │  │RetryPolicy│  │                      │
    │  │  │Policy 2  │ │      │  │CircuitBrkr│  │     ┌──────────────┐ │
    │  │  │Policy 3  │ │      │  │Dead Letter│  │     │  State       │ │
    │  │  └──────────┘ │      │  └───────────┘  │     │  Manager     │ │
    │  └──────────────┘      └────────────────┘     └──────────────┘ │
    └──────────────────────────────────────────────────────────────────┘
```

## Files Created / Modified

| File | Description |
|------|-------------|
| `src/conductor/orchestration/error_handler.py` | ErrorAction, RetryPolicy, CircuitBreaker, ErrorHandler |
| `src/conductor/orchestration/policy_engine.py` | Policy ABC, PolicyResult, PolicyEngine, 4 built-in policies |
| `src/conductor/orchestration/__init__.py` | Updated exports for all Day 4 components |
| `tests/test_orchestration/test_error_handler.py` | 24 tests covering retry, circuit breaker, DLQ, escalation |
| `tests/test_orchestration/test_policy_engine.py` | 27 tests covering all 4 policies + engine mechanics |
| `docs/day-04-error-handler-policy-engine.md` | This documentation file |

## Component Deep Dive

### Error Handler (`error_handler.py`)

Three resilience patterns working together:

#### 1. RetryPolicy (Exponential Backoff with Jitter)

```python
policy = RetryPolicy(
    max_retries=3,            # Give up after 3 attempts
    initial_delay=1.0,        # First retry after ~1 second
    backoff_multiplier=2.0,   # Double the delay each time
    max_delay=60.0,           # Never wait longer than 60s
    retryable_errors=[        # Only retry these error codes
        "LLM_TIMEOUT", "LLM_RATE_LIMIT", "TRANSIENT_ERROR"
    ],
)

# Delay progression: ~1s → ~2s → ~4s → (give up)
delay = policy.calculate_delay(attempt=2)  # ~4.0s + jitter
```

#### 2. CircuitBreaker (Per-Agent Health Tracking)

```
CLOSED ──(5 failures)──→ OPEN ──(60s elapsed)──→ HALF_OPEN
   ↑                                                   │
   └────────────── (2 successes) ──────────────────────┘
```

```python
breaker = CircuitBreaker(
    failure_threshold=5,      # Open after 5 consecutive failures
    recovery_timeout=60.0,    # Wait 60s before testing recovery
    success_threshold=2,      # Need 2 successes to confirm recovery
)

if await breaker.can_execute():
    try:
        result = await agent.execute(task)
        await breaker.record_success()
    except Exception:
        await breaker.record_failure()
```

#### 3. ErrorHandler (Decision Engine)

```python
handler = ErrorHandler(bus, state_manager, RetryPolicy(max_retries=3))

try:
    result = await agent.execute(task)
except AgentError as e:
    action = await handler.handle_error(e, {
        "agent_id": "coding-01",
        "task_id": "task-123",
        "attempt": current_attempt,
    })

    if action == ErrorAction.RETRY:
        await handler.retry_task("task-123", "coding-01", current_attempt)
        # ... re-execute the task
    elif action == ErrorAction.ESCALATE:
        # Error was published to conductor:errors for coordinator
        pass
    elif action == ErrorAction.DEAD_LETTER:
        # Error stored in DLQ: handler.get_dead_letter_queue()
        pass
```

**Decision Tree:**
```
Exception → Circuit Breaker OPEN? ──→ DEAD_LETTER
                    │
                    NO
                    │
            Is error retryable? ──→ NO → ESCALATE
                    │
                   YES
                    │
            attempt < max_retries? ──→ NO → DEAD_LETTER
                    │
                   YES → RETRY
```

### Policy Engine (`policy_engine.py`)

The Policy Engine is a gatekeeper — every significant action passes through it.

#### Policy ABC

```python
class MyPolicy(Policy):
    @property
    def name(self) -> str:
        return "MyPolicy"

    @property
    def description(self) -> str:
        return "Checks a custom condition"

    async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
        if condition_met(context):
            return PolicyResult(allowed=True, policy_name=self.name)
        return PolicyResult(
            allowed=False,
            policy_name=self.name,
            reason="Condition not met",
        )
```

#### Built-in Policies

| Policy | Purpose | Context Key | Default |
|--------|---------|-------------|---------|
| `MaxConcurrentTasksPolicy` | Caps running agents | `agent_states` | max 5 |
| `TaskTimeoutPolicy` | Validates timeout bounds | `task` | 0 < t < 3600 |
| `PhaseGatePolicy` | Quality gate for phase transitions | `workflow_state` | 80% success |
| `AgentAvailabilityPolicy` | Checks agent status | `agent_state` | IDLE/COMPLETED ok |

#### Three Evaluation Modes

```python
engine = PolicyEngine()
engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=5))
engine.register_policy(AgentAvailabilityPolicy())

context = {
    "agent_states": all_states,
    "agent_state": target_state,
}

# Mode 1: Get all results (for dashboards)
results = await engine.evaluate_all(context)

# Mode 2: Raise on first violation (for gating)
await engine.enforce(context)  # raises PolicyViolationError if any deny

# Mode 3: Simple bool check (for conditionals)
if await engine.check(context):
    proceed()
```

#### Design Decisions

1. **Fail-open for missing context**: If a required key is missing, the policy allows (doesn't block due to caller error)
2. **Fail-closed on evaluation errors**: If a policy's `evaluate()` throws, it's recorded as denied
3. **Sequential evaluation**: Policies evaluate in registration order for deterministic behavior
4. **Separation of concerns**: PolicyEngine evaluates; caller executes

## Test Results

```
237 tests passed, 0 failed

Error Handler Tests (24):
  - ErrorAction enum values
  - CircuitBreakerState enum values
  - RetryPolicy defaults, delay calculation, jitter, max cap
  - RetryPolicy retryable/non-retryable error codes
  - CircuitBreaker state transitions (CLOSED→OPEN→HALF_OPEN→CLOSED)
  - CircuitBreaker success resets, failure threshold, recovery timeout
  - ErrorHandler RETRY/ESCALATE/DEAD_LETTER decisions
  - Circuit breaker integration with ErrorHandler
  - DLQ accumulation and copy semantics
  - Escalation survives bus failure
  - Generic exceptions get UNKNOWN_ERROR code
  - Per-agent circuit breaker isolation

Policy Engine Tests (27):
  - PolicyResult model correctness
  - MaxConcurrentTasksPolicy (under/at limit, empty, missing context)
  - TaskTimeoutPolicy (valid, default, missing context)
  - PhaseGatePolicy (above/below threshold, no tasks, all pass)
  - AgentAvailabilityPolicy (IDLE, COMPLETED, RUNNING, FAILED)
  - PolicyEngine registration, unregistration, copy semantics
  - evaluate_all (empty, all pass, some fail)
  - enforce (pass, violation raises)
  - check (true, false, empty)
  - Buggy policy error handling
```

## What's Next (Day 5)

Day 5 adds **Agent Coordinator** and **Workflow Engine**:

- `agent_coordinator.py` — Agent registry, task dispatch, lifecycle management
- `workflow_engine.py` — Multi-phase workflow execution, feedback loop handling
