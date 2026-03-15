# Runbook: Workflow Stuck in IN_PROGRESS

**Severity:** High
**Components Affected:** WorkflowEngine, StateManager, AgentCoordinator
**Last Updated:** 2026-03-14

---

## Alert / Symptoms

### How This Is Detected

- Prometheus alert `ConductorAIWorkflowStuck` fires when a workflow has been `IN_PROGRESS` longer than `workflow_timeout_seconds` (default 300s, configurable 10-3600s)
- Monitoring dashboard shows workflows with `status=in_progress` and `started_at` older than expected
- Structlog entries stop appearing for the stuck workflow -- no `phase_completed`, `task_completed`, or `workflow_completed` events

### Observable Symptoms

1. **Workflow state frozen**: `WorkflowState.status` remains `IN_PROGRESS` with `completed_at=None` long past the expected duration
2. **Current phase stalled**: `WorkflowState.current_phase` does not advance (stuck at `development`, `devops`, or `monitoring`)
3. **Agent stuck in RUNNING**: One or more agents show `AgentState.status=RUNNING` with a stale `current_task_id` that never completes
4. **Heartbeat stale**: `AgentState.last_heartbeat` has not been updated (indicates agent process may be dead or hung)
5. **No new task results**: `WorkflowState.task_results` dict stops growing -- no new `TaskResult` entries are being added
6. **Phase history incomplete**: `WorkflowState.phase_history` shows a phase `started_at` but no corresponding `completed_at`

---

## Impact

| Impact Area | Description |
|---|---|
| **Blocked Workflows** | The stuck workflow consumes agent capacity. Agents assigned to the stuck task remain in `RUNNING` status and are unavailable for new task dispatch (`AgentCoordinator.get_available_agents()` skips non-IDLE agents). |
| **Resource Leak** | If the agent is awaiting an LLM response that will never arrive, the async task holds resources indefinitely. |
| **Cascading Stalls** | Other workflows waiting for agents of the same `AgentType` will fail with `AgentError(error_code="NO_AVAILABLE_AGENT")` if all agents of that type are stuck. |
| **State Inconsistency** | The `WorkflowState` in the StateManager reflects a workflow that is neither complete nor failed, making it invisible to cleanup processes. |

---

## Diagnosis Steps

### Step 1: Identify Stuck Workflows

Query the StateManager for workflows with `status=in_progress`:

```bash
# If using Redis-backed StateManager:
redis-cli KEYS "conductor:workflow:*" | while read key; do
  status=$(redis-cli GET "$key" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['status'])")
  started=$(redis-cli GET "$key" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['started_at'])")
  if [ "$status" = "in_progress" ]; then
    echo "STUCK: $key started_at=$started"
  fi
done
```

Or check via application logs:
```bash
kubectl logs -l app=conductorai -n conductorai --tail=500 | \
  grep -E "workflow_starting|workflow_completed|workflow_failed" | tail -20
```

Look for `workflow_starting` events without a corresponding `workflow_completed` or `workflow_failed`.

### Step 2: Check the Stuck Workflow's Current Phase

```bash
# Get workflow state from Redis
redis-cli GET "conductor:workflow:<workflow_id>" | python3 -m json.tool
```

Key fields to examine:
- `current_phase`: Which phase is stuck (`development`, `devops`, `monitoring`)
- `task_results`: Which tasks completed vs. which are missing
- `error_log`: Any errors recorded during execution
- `phase_history`: Check the last phase entry -- does it have `completed_at`?

### Step 3: Check Agent States for Stale RUNNING Status

```bash
# List all agent states
redis-cli KEYS "conductor:agent:*" | while read key; do
  redis-cli GET "$key" | python3 -c "
import sys, json
state = json.loads(sys.stdin.read())
if state['status'] == 'running':
    print(f\"STUCK AGENT: {state['agent_id']} type={state['agent_type']} task={state['current_task_id']} updated={state['updated_at']}\")
"
done
```

### Step 4: Check Agent Heartbeats

```bash
# Look for stale heartbeats (agents that stopped reporting)
redis-cli KEYS "conductor:agent:*" | while read key; do
  redis-cli GET "$key" | python3 -c "
import sys, json
from datetime import datetime, timezone
state = json.loads(sys.stdin.read())
hb = state.get('last_heartbeat')
if hb:
    print(f\"{state['agent_id']}: last_heartbeat={hb} status={state['status']}\")
else:
    print(f\"{state['agent_id']}: NO HEARTBEAT status={state['status']}\")
"
done
```

An agent with `status=running` and a `last_heartbeat` older than 60 seconds (or `None`) is likely dead or hung.

### Step 5: Check Message Bus for Pending Messages

```bash
# Check if there are messages waiting for delivery
redis-cli PUBSUB CHANNELS "conductor:agent:*"

# Check request-response pending futures
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -E "request_timeout|response_timeout|correlation_id"
```

### Step 6: Check Application Logs for the Stuck Task

```bash
# Filter logs for the specific workflow and task
kubectl logs -l app=conductorai -n conductorai --tail=500 | \
  grep "<workflow_id>" | tail -30

# Look for the last activity
kubectl logs -l app=conductorai -n conductorai --tail=500 | \
  grep "<stuck_task_id>" | tail -20
```

Common stuck patterns:
- `task_execution_starting` with no subsequent `task_execution_completed` or `task_execution_failed`
- `openai_api_call` or `anthropic_api_call` with no subsequent `openai_api_response` or `anthropic_api_response` (LLM call hung)

### Step 7: Check Prometheus Metrics

```promql
# Active agents -- should be 0 if system is idle, >0 if work is happening
conductorai_active_agents

# Task duration -- look for extremely long-running tasks
histogram_quantile(0.99, rate(conductorai_task_duration_seconds_bucket[1h]))

# Error rate during the stuck period
rate(conductorai_errors_total[5m])

# Workflow completions -- should be >0 if workflows are finishing
rate(conductorai_workflows_total[5m])
```

---

## Resolution Steps

### Option A: Force Workflow Status to FAILED (Manual Resolution)

If the workflow is genuinely stuck and cannot recover, manually update its state:

```bash
# Get the current workflow state
WORKFLOW_STATE=$(redis-cli GET "conductor:workflow:<workflow_id>")

# Update status to FAILED and set completed_at
echo "$WORKFLOW_STATE" | python3 -c "
import sys, json
from datetime import datetime, timezone
state = json.loads(sys.stdin.read())
state['status'] = 'failed'
state['completed_at'] = datetime.now(timezone.utc).isoformat()
state['error_log'].append({
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'error': 'Manually failed by operator: workflow stuck in IN_PROGRESS',
    'error_type': 'ManualIntervention'
})
print(json.dumps(state))
" | redis-cli -x SET "conductor:workflow:<workflow_id>"
```

### Option B: Reset Stuck Agent to IDLE

If an agent is stuck in `RUNNING` with a stale task:

```bash
# Get agent state
AGENT_STATE=$(redis-cli GET "conductor:agent:<agent_id>")

# Reset to IDLE
echo "$AGENT_STATE" | python3 -c "
import sys, json
from datetime import datetime, timezone
state = json.loads(sys.stdin.read())
stuck_task = state.get('current_task_id')
state['status'] = 'idle'
state['current_task_id'] = None
state['updated_at'] = datetime.now(timezone.utc).isoformat()
if stuck_task:
    state['failed_tasks'].append(stuck_task)
    state['error_count'] = state.get('error_count', 0) + 1
print(json.dumps(state))
" | redis-cli -x SET "conductor:agent:<agent_id>"
```

### Option C: Restart the ConductorAI Application

If multiple workflows or agents are stuck, a full restart is the cleanest resolution:

```bash
# Graceful restart -- triggers ConductorAI.shutdown() which calls:
#   coordinator.stop() -> stops all agents
#   state_manager.disconnect()
#   message_bus.disconnect()
kubectl rollout restart deployment/conductorai -n conductorai
kubectl rollout status deployment/conductorai -n conductorai
```

After restart:
1. The coordinator's in-memory `_agents` registry is rebuilt from scratch as agents re-register
2. Stuck workflows in the StateManager will still show `IN_PROGRESS` -- manually fail them (Option A) or re-run them

### Option D: Re-dispatch Stuck Tasks

If you identified specific tasks that were stuck but the workflow is still viable:

1. Manually fail the stuck workflow (Option A)
2. Create and run a new workflow with the same `WorkflowDefinition`:
   ```python
   # In application code or admin script:
   new_state = await conductor.run_workflow(original_definition)
   ```

### Post-Resolution Verification

1. **Verify no stuck workflows remain:**
   ```bash
   redis-cli KEYS "conductor:workflow:*" | while read key; do
     status=$(redis-cli GET "$key" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['status'])")
     if [ "$status" = "in_progress" ]; then
       echo "STILL STUCK: $key"
     fi
   done
   ```

2. **Verify all agents are IDLE:**
   ```bash
   redis-cli KEYS "conductor:agent:*" | while read key; do
     status=$(redis-cli GET "$key" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['status'])")
     echo "$key: $status"
   done
   ```

3. **Run a test workflow** to confirm end-to-end operation.

---

## Prevention

### Configuration

The `workflow_timeout_seconds` setting in `ConductorConfig` controls the maximum allowed workflow duration:

```yaml
# conductor.yaml
workflow_timeout_seconds: 300  # default, range: 10-3600

# For long-running workflows (e.g., full pipeline with feedback loops):
workflow_timeout_seconds: 900  # 15 minutes
```

Or via environment variable:
```bash
export CONDUCTOR_WORKFLOW_TIMEOUT_SECONDS=600
```

### Monitoring

```yaml
groups:
  - name: conductorai-workflows
    rules:
      - alert: ConductorAIWorkflowStuck
        expr: |
          (time() - conductorai_workflow_started_timestamp{status="in_progress"}) > 300
        for: 5m
        labels:
          severity: high
        annotations:
          summary: "Workflow stuck in IN_PROGRESS"
          description: "Workflow {{ $labels.workflow_id }} has been IN_PROGRESS for over 5 minutes."

      - alert: ConductorAIAgentStuckRunning
        expr: |
          (time() - conductorai_agent_last_state_change_timestamp{status="running"}) > 120
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Agent stuck in RUNNING state"
          description: "Agent {{ $labels.agent_id }} has been RUNNING for over 2 minutes without completing."

      - alert: ConductorAINoWorkflowCompletions
        expr: rate(conductorai_workflows_total[10m]) == 0
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "No workflows completing"
          description: "No workflows have completed in the last 15 minutes. Possible system-wide stall."
```

### Architectural Recommendations

1. **Implement agent heartbeat monitoring**: `BaseAgent.send_heartbeat()` updates `AgentState.last_heartbeat`. Build a watchdog that detects stale heartbeats and force-resets stuck agents.
2. **Add per-task timeouts**: Use `TaskDefinition.timeout_seconds` (default 300) and enforce it with `asyncio.wait_for()` in the coordinator's dispatch flow.
3. **Feedback loop limit**: `WorkflowEngine._max_feedback_loops` (default 3) prevents infinite Monitor-to-Development cycles. Keep this at 3 or lower.
4. **Set `max_agent_retries`** appropriately: Default is 3. Higher values mean stuck tasks take longer to finally fail.

---

## Escalation

| Level | Condition | Action |
|---|---|---|
| **L1 - On-Call** | Single workflow stuck, other workflows completing normally | Manually fail the stuck workflow (Option A), reset stuck agent (Option B) |
| **L2 - Platform** | Multiple workflows stuck, or agents systematically failing to return | Restart application (Option C), investigate LLM provider connectivity, check Redis connectivity |
| **L3 - Engineering** | Recurring stuck workflows, agent execution never completing, suspected deadlock | Investigate `BaseAgent.execute_task()` flow, check for async task cancellation issues, review `WorkflowEngine._execute_phase_tasks()` error handling |
