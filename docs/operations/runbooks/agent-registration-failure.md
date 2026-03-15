# Runbook: Agent Registration Failure

**Severity:** Medium to High
**Components Affected:** AgentCoordinator, BaseAgent, StateManager
**Last Updated:** 2026-03-14

---

## Alert / Symptoms

### How This Is Detected

- Application startup logs show agent registration errors
- Prometheus metric `conductorai_active_agents` is 0 or lower than expected for one or more `agent_type` labels
- Workflow dispatches fail with `AgentError(error_code="NO_AVAILABLE_AGENT")`
- Health check returns `healthy` (infrastructure is fine) but workflows fail immediately

### Observable Symptoms

1. **Agent not appearing in coordinator registry**: After application startup, `AgentCoordinator.agent_count` is lower than expected. `get_agents_by_type(AgentType.CODING)` returns empty list for the missing type.
2. **Tasks not being dispatched**: `AgentCoordinator.dispatch_task()` raises `AgentError` with:
   ```
   error_code="NO_AVAILABLE_AGENT"
   message="No available agent of type 'coding'. Registered agents of this type: 0"
   ```
3. **Structlog showing registration failure**:
   ```
   event="agent_starting" agent_id="coding-01" agent_type="coding"
   [error follows -- agent.start() or register_agent() failed]
   ```
4. **Duplicate registration attempts**:
   ```
   event="AgentError" error_code="AGENT_ALREADY_REGISTERED" message="Agent 'coding-01' is already registered"
   ```

---

## Impact

| Impact Area | Description |
|---|---|
| **Workflow Execution** | Workflows requiring the unregistered agent type will fail. The `WorkflowEngine._execute_phase_tasks()` creates `TaskResult(status=FAILED, error_message="No available agent...")` for affected tasks. |
| **Phase Blocking** | If the missing agent is in the DEVELOPMENT phase (CODING, REVIEW, TEST, TEST_DATA), the entire workflow is blocked at phase 1. If missing from DEVOPS (DEVOPS, DEPLOYING) or MONITORING (MONITOR), those phases fail. |
| **Partial Workflows** | The WorkflowEngine uses a "best effort" strategy -- it continues executing remaining tasks even if some fail. So the workflow may partially complete with gaps where the missing agent should have contributed. |

### Phase-to-Agent Mapping

The `WorkflowEngine` dispatches tasks based on this mapping:

| Workflow Phase | Agent Types |
|---|---|
| `DEVELOPMENT` | `CODING`, `REVIEW`, `TEST_DATA`, `TEST` |
| `DEVOPS` | `DEVOPS`, `DEPLOYING` |
| `MONITORING` | `MONITOR` |

A missing agent from any phase means tasks assigned to that `AgentType` will fail with `NO_AVAILABLE_AGENT`.

---

## Diagnosis Steps

### Step 1: Check Agent Registration Logs at Startup

```bash
# Look for the full registration sequence
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -E "agent_starting|agent_started|agent_registered|agent_registration_failed|AGENT_ALREADY_REGISTERED"
```

A successful registration produces this log sequence:
```
event="agent_starting" agent_id="coding-01" agent_type="coding"
event="agent_started" agent_id="coding-01" agent_type="coding"
event="agent_registered" agent_id="coding-01" agent_type="coding" total_agents=1
```

If the sequence is interrupted, the agent failed to register.

### Step 2: Check for Startup Errors

```bash
# Look for errors during ConductorAI initialization
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -E "error|Error|exception|Exception|failed|Failed" | head -30

# Specifically check for agent start() failures
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -E "agent_start|_on_start"
```

Common startup errors:
- `LLMProviderError(error_code="LLM_MISSING_DEPENDENCY")`: The agent requires an LLM provider but the SDK package is not installed
- `ConfigurationError`: Bad configuration prevented agent initialization
- `ImportError`: Agent class could not be imported (missing dependency)

### Step 3: Verify AgentType Mapping in Code

Each agent is constructed with an `AgentType` enum value. Verify the agent being registered uses the correct type:

```python
# Correct: agent_type matches the expected role
coding_agent = CodingAgent("coding-01", agent_type=AgentType.CODING, config=config)

# WRONG: agent_type mismatch -- agent is CODING but type says REVIEW
coding_agent = CodingAgent("coding-01", agent_type=AgentType.REVIEW, config=config)
```

The valid `AgentType` values are:
- `AgentType.CODING` = `"coding"`
- `AgentType.REVIEW` = `"review"`
- `AgentType.TEST_DATA` = `"test_data"`
- `AgentType.TEST` = `"test"`
- `AgentType.DEVOPS` = `"devops"`
- `AgentType.DEPLOYING` = `"deploying"`
- `AgentType.MONITOR` = `"monitor"`
- `AgentType.PIPELINE_GENERATOR` = `"pipeline_generator"`

### Step 4: Check Coordinator State

```bash
# Check how many agents the coordinator knows about
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep "agent_registered" | tail -10
# The total_agents field shows the running count

# Check if coordinator itself started
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep "coordinator_started"
```

If `coordinator_started` is missing, the `ConductorAI.initialize()` method may have failed. Check for:
```bash
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -E "conductor_initializing|conductor_initialized"
```

### Step 5: Check Agent State in StateManager

If using Redis-backed StateManager:
```bash
# List all persisted agent states
redis-cli KEYS "conductor:agent:*"

# Check a specific agent's state
redis-cli GET "conductor:agent:coding-01" | python3 -m json.tool
```

If the agent key does not exist, the agent was never successfully registered (registration calls `_sync_agent_state()` which persists to Redis).

### Step 6: Check LLM Configuration for Agent Dependencies

Agents need a valid LLM provider. Check the configuration:

```bash
# Check LLM provider config
echo "Provider: $CONDUCTOR_LLM__PROVIDER"
echo "Model: $CONDUCTOR_LLM__MODEL"
echo "API Key set: $([ -n \"$CONDUCTOR_LLM__API_KEY\" ] && echo 'yes' || echo 'NO')"
```

If `provider` is `"openai"` but the `openai` package is not installed:
```
LLMProviderError: The 'openai' package is required for OpenAIProvider. Install it with: pip install conductorai[openai]
```

If `provider` is `"anthropic"` but the `anthropic` package is not installed:
```
LLMProviderError: The 'anthropic' package is required for AnthropicProvider. Install it with: pip install conductorai[anthropic]
```

### Step 7: Check Prometheus Metrics

```promql
# Active agents by type -- should match expected count
conductorai_active_agents

# If an agent_type label is missing entirely, that agent type was never registered

# Check if tasks are being dispatched but failing due to no agent
rate(conductorai_errors_total{error_code="NO_AVAILABLE_AGENT"}[5m])
```

---

## Resolution Steps

### Issue: Agent Start Fails Due to Missing LLM Dependency

```bash
# Install the required provider SDK
pip install conductorai[openai]     # For OpenAI provider
pip install conductorai[anthropic]  # For Anthropic provider

# Or install both:
pip install conductorai[openai,anthropic]

# Restart the application
kubectl rollout restart deployment/conductorai -n conductorai
```

### Issue: Wrong AgentType in Agent Constructor

Fix the agent initialization code to use the correct `AgentType`:

```python
# In your application setup:
from conductor.core.enums import AgentType
from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent

# Each agent class must be paired with its correct AgentType
coding_agent = CodingAgent(
    agent_id="coding-01",
    agent_type=AgentType.CODING,  # Must be CODING for CodingAgent
    config=config,
)
review_agent = ReviewAgent(
    agent_id="review-01",
    agent_type=AgentType.REVIEW,  # Must be REVIEW for ReviewAgent
    config=config,
)
```

### Issue: Duplicate Agent ID

If you see `AGENT_ALREADY_REGISTERED`, you are trying to register two agents with the same `agent_id`:

```python
# WRONG: Both agents have the same ID
agent1 = CodingAgent("coding-01", agent_type=AgentType.CODING, config=config)
agent2 = CodingAgent("coding-01", agent_type=AgentType.CODING, config=config)  # Will fail

# CORRECT: Unique IDs for each instance
agent1 = CodingAgent("coding-01", agent_type=AgentType.CODING, config=config)
agent2 = CodingAgent("coding-02", agent_type=AgentType.CODING, config=config)
```

### Issue: ConductorAI Not Initialized Before Agent Registration

Agents can only be registered after `ConductorAI.initialize()` (or entering the async context manager). Registration before initialization raises `RuntimeError`:

```python
# WRONG: register before initialize
conductor = ConductorAI(config)
await conductor.register_agent(agent)  # RuntimeError: ConductorAI has not been initialized

# CORRECT: initialize first
conductor = ConductorAI(config)
await conductor.initialize()
await conductor.register_agent(agent)

# OR: use async context manager
async with ConductorAI(config) as conductor:
    await conductor.register_agent(agent)
```

### Issue: Missing Agent Type in Workflow Definition

If the WorkflowDefinition includes tasks assigned to an agent type that was never registered:

1. **Register the missing agent type** before running the workflow
2. **Or remove the task** from the WorkflowDefinition if that agent type is not needed

```python
# Verify all required agent types are registered before running workflow
for task in workflow_definition.tasks:
    agents = coordinator.get_agents_by_type(task.assigned_to)
    if not agents:
        print(f"WARNING: No agent registered for type {task.assigned_to}")
```

### Issue: Agent _on_start() Hook Fails

If a custom agent overrides `_on_start()` and that method raises an exception, the agent's `start()` call fails and registration is aborted:

```bash
# Look for errors in the _on_start hook
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -A5 "agent_starting"
```

Fix the custom `_on_start()` implementation in the agent subclass, or make it more resilient:

```python
class MyAgent(BaseAgent):
    async def _on_start(self) -> None:
        try:
            # Custom initialization that might fail
            await self._setup_external_connection()
        except Exception as e:
            self._logger.warning("agent_on_start_non_critical_failure", error=str(e))
            # Don't re-raise if this is non-critical
```

### Post-Resolution Verification

1. **Verify all expected agents are registered:**
   ```bash
   kubectl logs -l app=conductorai -n conductorai --tail=100 | \
     grep "agent_registered"
   ```

   Expected output should show all agent types your workflow needs:
   ```
   event="agent_registered" agent_id="coding-01" agent_type="coding" total_agents=1
   event="agent_registered" agent_id="review-01" agent_type="review" total_agents=2
   event="agent_registered" agent_id="test-01" agent_type="test" total_agents=3
   event="agent_registered" agent_id="devops-01" agent_type="devops" total_agents=4
   event="agent_registered" agent_id="monitor-01" agent_type="monitor" total_agents=5
   ```

2. **Verify Prometheus metrics:**
   ```promql
   # Should show all expected agent types
   conductorai_active_agents
   ```

3. **Run a test workflow** to confirm all phases execute successfully.

---

## Prevention

### Pre-Deployment Checklist

- [ ] All required agent types for the workflow are instantiated and registered
- [ ] Each agent has a unique `agent_id`
- [ ] Each agent's `agent_type` matches its class (CodingAgent uses `AgentType.CODING`, etc.)
- [ ] LLM provider SDK is installed (`pip install conductorai[openai]` or `conductorai[anthropic]`)
- [ ] LLM API key is configured via `CONDUCTOR_LLM__API_KEY` or `conductor.yaml`
- [ ] `ConductorAI.initialize()` is called before `register_agent()`
- [ ] Agent `_on_start()` hooks are resilient to transient failures

### Monitoring

```yaml
groups:
  - name: conductorai-agents
    rules:
      - alert: ConductorAIMissingAgentType
        expr: |
          absent(conductorai_active_agents{agent_type="coding"})
          or absent(conductorai_active_agents{agent_type="review"})
          or absent(conductorai_active_agents{agent_type="test"})
          or absent(conductorai_active_agents{agent_type="devops"})
          or absent(conductorai_active_agents{agent_type="monitor"})
        for: 5m
        labels:
          severity: high
        annotations:
          summary: "Expected agent type not registered"
          description: "One or more required agent types are missing from the coordinator registry."

      - alert: ConductorAINoAvailableAgent
        expr: rate(conductorai_errors_total{error_code="NO_AVAILABLE_AGENT"}[5m]) > 0
        for: 2m
        labels:
          severity: high
        annotations:
          summary: "No available agent for task dispatch"
          description: "Tasks are failing because no agent of the required type is available."

      - alert: ConductorAIAgentCountDrop
        expr: |
          sum(conductorai_active_agents) < 3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Low agent count"
          description: "Only {{ $value }} agents are active. Expected at least 5 for full workflow support."
```

### Configuration Validation

Add a startup validation step to your application that checks all required agent types are registered before accepting workflow requests:

```python
REQUIRED_AGENT_TYPES = [
    AgentType.CODING,
    AgentType.REVIEW,
    AgentType.TEST,
    AgentType.DEVOPS,
    AgentType.MONITOR,
]

async def validate_agent_coverage(coordinator: AgentCoordinator) -> bool:
    for agent_type in REQUIRED_AGENT_TYPES:
        agents = coordinator.get_agents_by_type(agent_type)
        if not agents:
            logger.error("missing_agent_type", agent_type=agent_type.value)
            return False
    return True
```

---

## Escalation

| Level | Condition | Action |
|---|---|---|
| **L1 - On-Call** | Single agent type missing, other workflows succeeding | Check registration logs, verify config, restart application |
| **L2 - Platform** | Multiple agent types missing, LLM SDK installation issue | Check container image, verify pip dependencies, rebuild container |
| **L3 - Engineering** | Agent `_on_start()` hook crashing, agent validation logic failing, systematic registration errors | Investigate agent subclass implementation, review `BaseAgent.start()` and `AgentCoordinator.register_agent()` code |
