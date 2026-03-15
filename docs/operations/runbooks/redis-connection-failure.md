# Runbook: Redis Connection Failure

**Severity:** Critical
**Components Affected:** StateManager, MessageBus, WorkflowEngine
**Last Updated:** 2026-03-14

---

## Alert / Symptoms

### How This Is Detected

- Health check endpoint returns `unhealthy` for `state_manager` or `message_bus` component:
  ```json
  {
    "status": "unhealthy",
    "checks": [
      {"component": "state_manager", "status": "unhealthy", "message": "Connection refused"}
    ]
  }
  ```
- Prometheus alert `ConductorAIRedisHealthCheckFailure` fires
- Structlog entries with Redis connection errors:
  ```
  event="task_dispatch_failed" error="Connection refused" component="agent_coordinator"
  event="workflow_failed" error="StateError: Failed to save workflow state" component="workflow_engine"
  ```

### Observable Symptoms

1. **Workflow timeouts**: Workflows hang at `IN_PROGRESS` because `StateManager.save_workflow_state()` and `StateManager.save_agent_state()` calls fail
2. **State save failures**: `StateError` exceptions with `error_code="STATE_WRITE_FAILED"` in logs
3. **Message bus failures**: `MessageBusError` exceptions with `error_code="PUBLISH_FAILED"` when agents attempt to publish to channels (`conductor:agent:{agent_id}`, `conductor:errors`)
4. **Task results lost**: `StateManager.save_task_result()` fails silently or raises, causing `TaskResult` objects to be lost
5. **Agent state desync**: Coordinator's in-memory `_agents` registry diverges from persisted state in Redis

---

## Impact

| Impact Area | Description |
|---|---|
| **Workflow Execution** | All workflows using Redis-backed `StateManager` will fail. `WorkflowEngine.run_workflow()` sets status to `FAILED` and records error in `error_log`. |
| **Agent Communication** | If using Redis-backed `MessageBus`, pub/sub channels (`conductor:agent:*`, `conductor:workflow:*`, `conductor:broadcast`) stop delivering messages. |
| **State Persistence** | Agent states, workflow states, and task results cannot be saved or retrieved. Keys prefixed with `conductor:` (configurable via `RedisConfig.key_prefix`) are inaccessible. |
| **Data Loss Risk** | In-flight task results from agents that completed work but could not persist results. |

---

## Diagnosis Steps

### Step 1: Verify Redis Connectivity

```bash
# Test basic Redis connectivity from the ConductorAI pod/host
redis-cli -u redis://localhost:6379/0 ping
# Expected: PONG

# If using password authentication (RedisConfig.password):
redis-cli -u redis://localhost:6379/0 -a "${CONDUCTOR_REDIS_PASSWORD}" ping

# If using TLS (RedisConfig.ssl=true):
redis-cli --tls -u rediss://localhost:6379/0 ping
```

### Step 2: Check Redis Server Status

```bash
# Check Redis process
kubectl get pods -l app=redis -n conductorai
kubectl logs -l app=redis -n conductorai --tail=50

# If running locally:
systemctl status redis
# or
docker ps | grep redis

# Check Redis INFO for connection stats
redis-cli INFO server | grep -E "uptime|connected_clients|blocked_clients"
redis-cli INFO memory | grep -E "used_memory_human|maxmemory"
redis-cli INFO clients | grep connected_clients
```

### Step 3: Check Connection Pool Exhaustion

The `RedisConfig.max_connections` defaults to `10`. If all connections are in use, new operations will block or fail.

```bash
# Check current client connections
redis-cli CLIENT LIST | wc -l

# Check if max connections are hit
redis-cli CONFIG GET maxclients
redis-cli INFO clients | grep -E "connected_clients|blocked_clients|rejected_connections"
```

Look for `rejected_connections > 0` which indicates the pool has been exhausted.

### Step 4: Check Sentinel / Cluster Status (if applicable)

If `RedisConfig.sentinel_mode=true`:
```bash
# Check Sentinel master resolution
redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
# Expected: Returns IP and port of current master

# Check Sentinel status
redis-cli -p 26379 SENTINEL masters
redis-cli -p 26379 SENTINEL replicas mymaster
```

If `RedisConfig.cluster_mode=true`:
```bash
# Check cluster health
redis-cli --cluster check <cluster_node>:6379
redis-cli CLUSTER INFO | grep cluster_state
# Expected: cluster_state:ok

# Check for failed nodes
redis-cli CLUSTER NODES | grep fail
```

### Step 5: Check ConductorAI Application Logs

```bash
# Search for Redis-related errors in structlog output
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -E "StateError|MessageBusError|Connection refused|PUBLISH_FAILED|STATE_WRITE_FAILED"

# Check health check logs
kubectl logs -l app=conductorai -n conductorai --tail=100 | \
  grep "health_check_completed"
```

### Step 6: Check Prometheus Metrics

```promql
# Check if state_manager health checks are failing
# (Custom metric if exposed via health check endpoint scraping)

# Check error rate by error code for state-related errors
rate(conductorai_errors_total{error_code=~"STATE_.*|MESSAGE_BUS_.*"}[5m])

# Check workflow failure rate (may spike during Redis outage)
rate(conductorai_workflows_total{status="failure"}[5m])

# Check if tasks are still being dispatched
rate(conductorai_tasks_total[5m])
```

---

## Resolution Steps

### Option A: Restart Redis (If Redis Is Down)

```bash
# Kubernetes
kubectl rollout restart statefulset/redis -n conductorai
kubectl wait --for=condition=ready pod -l app=redis -n conductorai --timeout=120s

# Docker
docker restart conductorai-redis

# Systemd
sudo systemctl restart redis
```

After restart, verify:
```bash
redis-cli ping
# PONG

# Verify ConductorAI keys are intact (if persistent storage configured)
redis-cli KEYS "conductor:*" | head -20
```

### Option B: Failover to InMemoryStateManager (Temporary Degraded Mode)

If Redis cannot be restored quickly, switch to in-memory mode to unblock workflows. This loses persistence across restarts but allows the system to continue operating.

**Via environment variables:**
```bash
# Set enable_persistence=false to use InMemoryStateManager
export CONDUCTOR_ENABLE_PERSISTENCE=false

# Restart the ConductorAI application
kubectl rollout restart deployment/conductorai -n conductorai
```

**Via conductor.yaml:**
```yaml
enable_persistence: false
```

**Important:** In-memory mode means:
- State is lost if the process restarts
- Multi-instance deployments will have inconsistent state
- This is a temporary measure only

### Option C: Fix Connection Pool Issues

If the issue is pool exhaustion rather than Redis being down:

**Increase max connections in configuration:**
```yaml
redis:
  max_connections: 20  # Default is 10, max allowed is 100
  socket_timeout: 10.0  # Default is 5.0, increase if operations are slow
```

**Or via environment variables:**
```bash
export CONDUCTOR_REDIS__MAX_CONNECTIONS=20
export CONDUCTOR_REDIS__SOCKET_TIMEOUT=10.0
```

### Option D: Fix Sentinel Failover Issues

If Sentinel failed to elect a new master:
```bash
# Force failover to a replica
redis-cli -p 26379 SENTINEL failover mymaster

# Verify new master
redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
```

Update `RedisConfig.sentinel_nodes` if Sentinel topology changed:
```yaml
redis:
  sentinel_mode: true
  sentinel_master: "mymaster"
  sentinel_nodes:
    - "sentinel-0:26379"
    - "sentinel-1:26379"
    - "sentinel-2:26379"
```

### Post-Recovery Verification

After Redis is restored:

1. **Verify health endpoint:**
   ```bash
   curl -s http://conductorai:8080/health | python3 -m json.tool
   # All components should show "healthy"
   ```

2. **Verify state manager connectivity:**
   ```bash
   # Check that agent states are being persisted
   redis-cli KEYS "conductor:agent:*"

   # Check workflow states
   redis-cli KEYS "conductor:workflow:*"
   ```

3. **Verify message bus:**
   ```bash
   # Check pub/sub channels are active
   redis-cli PUBSUB CHANNELS "conductor:*"
   ```

4. **Run a test workflow** to confirm end-to-end operation.

5. **If you were in InMemoryStateManager failover mode**, switch back:
   ```bash
   export CONDUCTOR_ENABLE_PERSISTENCE=true
   kubectl rollout restart deployment/conductorai -n conductorai
   ```

---

## Prevention

### Monitoring

Set up the following Prometheus alerts:

```yaml
groups:
  - name: conductorai-redis
    rules:
      - alert: ConductorAIRedisHealthCheckFailure
        expr: conductorai_redis_health_check_success == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "ConductorAI Redis health check failing"
          description: "Redis health check has been failing for 1 minute. StateManager and MessageBus are impacted."

      - alert: ConductorAIHighStateErrors
        expr: rate(conductorai_errors_total{error_code=~"STATE_.*"}[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Elevated state management errors"
          description: "State-related errors are occurring at {{ $value }}/s. Possible Redis connectivity issue."

      - alert: ConductorAIRedisConnectionPoolExhausted
        expr: redis_connected_clients >= 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis connection pool near capacity"
```

### Configuration Best Practices

1. **Set appropriate `socket_timeout`**: Default `5.0` seconds. Increase to `10.0` in high-latency environments.
2. **Size `max_connections` for your workload**: Each concurrent workflow dispatch can consume a connection. Rule of thumb: `max_connections >= max_concurrent_workflows * 2`.
3. **Enable Sentinel or Cluster mode** in production for high availability.
4. **Configure Redis persistence** (RDB or AOF) to survive Redis restarts without data loss.

### Capacity Planning

- Monitor `redis_connected_clients` vs `RedisConfig.max_connections`
- Monitor `redis_used_memory` vs `redis_maxmemory`
- Set Redis `maxmemory-policy` to `allkeys-lru` to prevent OOM kills

---

## Escalation

| Level | Condition | Action |
|---|---|---|
| **L1 - On-Call** | Health check shows `unhealthy` for `state_manager` | Attempt Redis restart, verify connectivity |
| **L2 - Platform** | Redis restart fails or data corruption detected | Engage DBA/platform team, consider failover to InMemoryStateManager |
| **L3 - Engineering** | Persistent connection pool exhaustion or application-level bugs | Engage ConductorAI development team for connection handling review |
