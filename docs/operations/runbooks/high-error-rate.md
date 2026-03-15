# Runbook: High Error Rate

**Severity:** High to Critical (depending on scope)
**Components Affected:** Agents, WorkflowEngine, ErrorHandler, CircuitBreakers
**Last Updated:** 2026-03-14

---

## Alert / Symptoms

### How This Is Detected

- Prometheus alert `ConductorAIHighWorkflowFailureRate` fires when the ratio of failed workflows exceeds threshold
- Prometheus alert `ConductorAIHighTaskErrorRate` fires when per-agent task failure rate is elevated
- PagerDuty/OpsGenie incident triggered by configured alert rules

### Alert Definitions

```promql
# Primary alert: workflow failure rate
rate(conductorai_workflows_total{status="failure"}[5m])
  / rate(conductorai_workflows_total[5m]) > 0.3

# Secondary alert: task error rate by agent type
rate(conductorai_tasks_total{status="failure"}[5m])
  / rate(conductorai_tasks_total[5m]) > 0.5

# Error counter spike
rate(conductorai_errors_total[5m]) > 1.0
```

### Observable Symptoms

1. **Elevated `conductorai_errors_total`**: Counter increasing rapidly, segmented by `error_code` label
2. **Workflow completions dropping**: `conductorai_workflows_total{status="success"}` rate decreasing or flat while `{status="failure"}` rate increasing
3. **Task failures by agent type**: `conductorai_tasks_total{status="failure"}` increasing for specific `agent_type` labels (coding, review, test, devops, etc.)
4. **Task durations anomalous**: `conductorai_task_duration_seconds` showing either extremely short durations (immediate failures) or extremely long durations (timeouts)
5. **Structlog error volume**: High density of error-level log entries:
   ```
   event="task_execution_failed" agent_id="coding-01" agent_type="coding" error="..." task_id="..."
   event="task_dispatch_error_handled" error_action="retry" agent_id="..." error="..."
   event="workflow_failed" workflow_id="..." error="..."
   ```

---

## Impact

| Impact Area | Description |
|---|---|
| **Workflow Reliability** | Workflows are completing with `status=failed`. `WorkflowState.error_log` accumulates error entries. Users/callers receive failed `WorkflowState` from `ConductorAI.run_workflow()`. |
| **Agent Availability** | Failing agents accumulate `error_count` in `AgentState`. Circuit breakers may open, removing agents from the available pool. `conductorai_active_agents` gauge drops. |
| **Dead Letter Queue Growth** | ErrorHandler parks unrecoverable failures in the DLQ. DLQ entries require manual inspection and reprocessing. |
| **Cascading Failures** | If CODING agent fails, dependent REVIEW and TEST tasks in the same workflow phase also fail. If the DEVELOPMENT phase fails entirely, DEVOPS and MONITORING phases may be skipped. |

---

## Triage Steps

### Step 1: Identify Error Distribution by Error Code

```promql
# Top error codes in the last 15 minutes
topk(10, sum by (error_code) (increase(conductorai_errors_total[15m])))
```

Common error codes and their meaning:

| Error Code | Source | Meaning |
|---|---|---|
| `TASK_EXECUTION_FAILED` | `BaseAgent.execute_task()` | Generic agent task failure |
| `LLM_AUTH_ERROR` | OpenAI/Anthropic provider | API key invalid (401) |
| `LLM_RATE_LIMIT` | OpenAI/Anthropic provider | Rate limit exceeded (429) |
| `LLM_CONNECTION_ERROR` | OpenAI/Anthropic provider | Network failure to LLM API |
| `LLM_API_ERROR` | OpenAI/Anthropic provider | Provider server error (5xx) |
| `NO_AVAILABLE_AGENT` | `AgentCoordinator.dispatch_task()` | No IDLE agent of required type |
| `AGENT_ALREADY_REGISTERED` | `AgentCoordinator.register_agent()` | Duplicate agent registration |
| `TASK_VALIDATION_FAILED` | `BaseAgent.execute_task()` | Task input data missing/invalid |
| `POLICY_VIOLATION` | `AgentCoordinator.dispatch_task()` | PolicyEngine blocked dispatch |
| `NO_AGENT_TYPE` | `AgentCoordinator.dispatch_task()` | Task has no `assigned_to` |
| `STATE_WRITE_FAILED` | `StateManager` | Redis write failure |
| `STATE_ERROR` | `StateManager` | Generic state operation failure |
| `MESSAGE_BUS_ERROR` | `MessageBus` | Pub/sub failure |
| `PUBLISH_FAILED` | `MessageBus` | Failed to publish message |
| `MAX_FEEDBACK_LOOPS` | `WorkflowEngine` | Feedback loop limit exceeded |

### Step 2: Identify the Failing Agent Type

```promql
# Task failure rate by agent type
sum by (agent_type) (rate(conductorai_tasks_total{status="failure"}[5m]))

# Compare with success rate
sum by (agent_type) (rate(conductorai_tasks_total{status="success"}[5m]))
```

If failures are concentrated on a single `agent_type`:
- **coding**: Check LLM provider, code generation prompts
- **review**: Check LLM provider, code review input data
- **test / test_data**: Check LLM provider, test generation logic
- **devops**: Check LLM provider, pipeline template generation
- **deploying**: Check deployment targets, infrastructure connectivity
- **monitor**: Check monitoring data sources, feedback loop logic

### Step 3: Check Task Duration Anomalies

```promql
# P99 task duration by agent type
histogram_quantile(0.99, sum by (agent_type, le) (rate(conductorai_task_duration_seconds_bucket[5m])))

# P50 task duration (median)
histogram_quantile(0.5, sum by (agent_type, le) (rate(conductorai_task_duration_seconds_bucket[5m])))

# Check specific bucket boundaries for the histogram:
# 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0 seconds
```

Interpretation:
- **Very short durations (< 0.1s) with failures**: Tasks are failing immediately at validation (`_validate_task()` returning False) or connection errors
- **Very long durations (> 60s)**: Tasks are timing out waiting for LLM responses or stuck in execution
- **Normal durations with failures**: Tasks are running but producing bad output

### Step 4: Check Circuit Breaker Status

```bash
# Look for circuit breaker state transitions in logs
kubectl logs -l app=conductorai -n conductorai --tail=300 | \
  grep -E "circuit_breaker_opened|circuit_breaker_half_open|circuit_breaker_closed|dead_letter"

# Check which agents are being rejected by open circuit breakers
kubectl logs -l app=conductorai -n conductorai --tail=300 | \
  grep "error_action=dead_letter"
```

Circuit breaker state transitions:
- `CLOSED -> OPEN`: Agent hit `failure_threshold` (default 5) consecutive failures. All new requests are immediately rejected.
- `OPEN -> HALF_OPEN`: After `recovery_timeout` (default 60s), limited test requests are allowed.
- `HALF_OPEN -> CLOSED`: After `success_threshold` (default 2) consecutive successes, normal operation resumes.
- `HALF_OPEN -> OPEN`: Any failure during half-open test reverts to fully open.

### Step 5: Check LLM Request/Token Metrics

```promql
# LLM request rate by provider and model
sum by (provider, model) (rate(conductorai_llm_requests_total[5m]))

# Token consumption rate by provider
sum by (provider, token_type) (rate(conductorai_llm_tokens_total[5m]))
```

High token consumption with high error rates may indicate:
- Retries burning through API quota
- Rate limits being hit due to retry storms

### Step 6: Examine Application Logs

```bash
# Get recent errors with full context
kubectl logs -l app=conductorai -n conductorai --tail=300 | \
  grep -E "level.*error" | tail -50

# Filter for specific workflow failures
kubectl logs -l app=conductorai -n conductorai --tail=300 | \
  grep "workflow_failed" | tail -20

# Get the error handler's decisions
kubectl logs -l app=conductorai -n conductorai --tail=300 | \
  grep "task_dispatch_error_handled" | tail -20
```

---

## Resolution Steps

### Based on Root Cause

#### If LLM Provider Errors (LLM_*)
See [LLM Provider Outage Runbook](./llm-provider-outage.md).

#### If Redis/State Errors (STATE_*, MESSAGE_BUS_*)
See [Redis Connection Failure Runbook](./redis-connection-failure.md).

#### If Agent Availability Errors (NO_AVAILABLE_AGENT)

All agents of a required type are busy or have open circuit breakers.

1. **Check agent count by type:**
   ```promql
   conductorai_active_agents
   ```

2. **If circuit breakers are blocking agents**, wait for `recovery_timeout` (60s default) for the circuit to transition to `HALF_OPEN`, or restart the application to reset circuit breakers:
   ```bash
   kubectl rollout restart deployment/conductorai -n conductorai
   ```

3. **If all agents are genuinely busy**, scale up by registering additional agent instances in your initialization code.

#### If Task Validation Errors (TASK_VALIDATION_FAILED)

Tasks are being dispatched with missing or invalid `input_data`.

1. **Check the failing task definitions:**
   ```bash
   kubectl logs -l app=conductorai -n conductorai --tail=200 | \
     grep "task_validation_failed"
   ```

2. **Verify required input_data fields per agent type:**
   - CodingAgent: requires `specification` in `task.input_data`
   - ReviewAgent: requires `code` in `task.input_data`
   - TestAgent: requires `code` in `task.input_data`
   - DevOpsAgent: requires `specification` in `task.input_data`

3. **Fix the WorkflowDefinition** that is producing tasks with missing input data.

#### If Policy Violations (POLICY_VIOLATION)

PolicyEngine is blocking task dispatches.

1. **Check which policy is failing:**
   ```bash
   kubectl logs -l app=conductorai -n conductorai --tail=200 | \
     grep "POLICY_VIOLATION"
   ```

2. Common policy violations:
   - `MaxConcurrentTasksPolicy`: Too many tasks on one agent. Increase limit or scale agents.
   - `PhaseGatePolicy`: Phase success rate below threshold. Fix failing tasks in the current phase before advancing.

### General Recovery: Reset Error State

If the root cause has been fixed but circuit breakers remain open or error counts are high:

```bash
# Full restart resets all in-memory state (circuit breakers, error counts)
kubectl rollout restart deployment/conductorai -n conductorai

# Verify recovery
kubectl rollout status deployment/conductorai -n conductorai
```

After restart, confirm:
```promql
# Error rate should drop
rate(conductorai_errors_total[5m])

# Workflow success rate should recover
rate(conductorai_workflows_total{status="success"}[5m])
```

---

## Prevention

### Monitoring

```yaml
groups:
  - name: conductorai-errors
    rules:
      - alert: ConductorAIHighWorkflowFailureRate
        expr: |
          (
            rate(conductorai_workflows_total{status="failure"}[5m])
            / rate(conductorai_workflows_total[5m])
          ) > 0.3
        for: 5m
        labels:
          severity: high
        annotations:
          summary: "High workflow failure rate ({{ $value | humanizePercentage }})"
          description: "More than 30% of workflows are failing in the last 5 minutes."

      - alert: ConductorAIHighTaskErrorRate
        expr: |
          sum by (agent_type) (
            rate(conductorai_tasks_total{status="failure"}[5m])
          ) /
          sum by (agent_type) (
            rate(conductorai_tasks_total[5m])
          ) > 0.5
        for: 3m
        labels:
          severity: high
        annotations:
          summary: "High task error rate for {{ $labels.agent_type }}"
          description: "Agent type {{ $labels.agent_type }} has >50% task failure rate."

      - alert: ConductorAIErrorRateSpike
        expr: rate(conductorai_errors_total[5m]) > 1.0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "ConductorAI error rate spike"
          description: "Error rate is {{ $value }}/s. Check error_code breakdown."

      - alert: ConductorAICircuitBreakerOpen
        expr: conductorai_circuit_breaker_state{state="open"} > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Circuit breaker open for {{ $labels.agent_id }}"
          description: "Agent {{ $labels.agent_id }} circuit breaker is OPEN. Tasks are being rejected."
```

### Grafana Dashboard Panels

Recommended panels for an error rate dashboard:

1. **Workflow Success/Failure Rate** (timeseries): `rate(conductorai_workflows_total[5m])` by status
2. **Error Code Distribution** (bar chart): `sum by (error_code) (increase(conductorai_errors_total[1h]))`
3. **Task Failure Rate by Agent Type** (timeseries): `rate(conductorai_tasks_total{status="failure"}[5m])` by agent_type
4. **Task Duration P99** (timeseries): `histogram_quantile(0.99, ...)` by agent_type
5. **Active Agents** (gauge): `conductorai_active_agents` by agent_type
6. **LLM Request Rate** (timeseries): `rate(conductorai_llm_requests_total[5m])` by provider

---

## Escalation Matrix

| Level | Condition | Action | Contact |
|---|---|---|---|
| **L1 - On-Call** | Error rate > 30% for < 10 min, single agent type affected | Check logs, identify error code, apply runbook for specific error type | On-call engineer |
| **L2 - Platform** | Error rate > 50% for > 10 min, multiple agent types affected, circuit breakers open | Restart application, switch LLM provider if needed, check Redis | Platform team lead |
| **L3 - Engineering** | Error rate not recovering after restart, systematic task validation failures, PolicyEngine misconfiguration | Code-level investigation of `BaseAgent.execute_task()`, `WorkflowEngine._execute_phase_tasks()`, ErrorHandler configuration | ConductorAI dev team |
| **L4 - Management** | Sustained outage > 30 min affecting production workloads | Incident commander, stakeholder communication, post-incident review | Engineering management |
