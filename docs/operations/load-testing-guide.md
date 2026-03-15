# ConductorAI Load Testing Guide

**Last Updated:** 2026-03-14
**Purpose:** Establish performance baselines, identify bottlenecks, and validate scaling capacity
**Tools:** Locust, k6, Prometheus, Grafana

---

## 1. Test Scenarios

### 1.1 Concurrent Workflow Execution

**Objective:** Determine how many concurrent workflows ConductorAI can handle before degradation.

| Scenario | Concurrent Workflows | Agents per Workflow | LLM Calls per Workflow | Duration |
|----------|---------------------|--------------------|-----------------------|----------|
| S1: Baseline | 1 | 4 (CODING, REVIEW, TEST, DEVOPS) | 4 | 5 min |
| S2: Light Load | 5 | 4 | 20 | 10 min |
| S3: Moderate Load | 20 | 4 | 80 | 15 min |
| S4: Heavy Load | 50 | 4 | 200 | 20 min |
| S5: Stress Test | 100 | 4 | 400 | 30 min |
| S6: Soak Test | 10 (sustained) | 4 | continuous | 4 hours |

**Metrics to Capture:**

- Workflow completion time (p50, p90, p99)
- Task execution duration per agent type (`conductorai_task_duration_seconds`)
- Active agent count (`conductorai_active_agents`)
- Error rate (`conductorai_errors_total`)
- Redis connection pool utilization
- Memory and CPU usage

### 1.2 Agent Throughput

**Objective:** Measure individual agent task processing capacity.

| Agent Type | Tasks/Minute Target | Input Size | Expected Duration |
|-----------|-------------------|------------|------------------|
| CodingAgent | 10 | 2KB spec | 5-30s per task |
| ReviewAgent | 15 | 5KB code | 3-20s per task |
| TestAgent | 10 | 5KB code | 5-30s per task |
| TestDataAgent | 20 | 1KB spec | 2-10s per task |
| DevOpsAgent | 15 | 2KB config | 3-15s per task |
| DeployingAgent | 5 | 3KB manifest | 10-60s per task |
| MonitorAgent | 20 | 1KB metrics | 2-10s per task |

### 1.3 LLM Latency Under Load

**Objective:** Measure LLM provider response times as concurrent request volume increases.

| Scenario | Concurrent LLM Calls | Provider | Model | Expected Latency |
|----------|---------------------|----------|-------|-----------------|
| L1: Single | 1 | OpenAI | gpt-4 | 2-10s |
| L2: Light | 5 | OpenAI | gpt-4 | 3-15s |
| L3: Moderate | 10 | OpenAI | gpt-4 | 5-30s |
| L4: Rate Limit | 20 | OpenAI | gpt-4 | 10s+ (429 errors) |
| L5: Provider Failover | 10 | OpenAI -> Anthropic | gpt-4 -> claude | Failover < 5s |

### 1.4 Redis Pressure Test

**Objective:** Measure Redis performance under ConductorAI workload patterns.

| Scenario | Operation Mix | Throughput Target | Latency Target |
|----------|-------------|------------------|----------------|
| R1: State reads | 80% GET, 20% SET | 10,000 ops/sec | p99 < 5ms |
| R2: State writes | 20% GET, 80% SET | 5,000 ops/sec | p99 < 10ms |
| R3: Pub/Sub | 100% PUBLISH/SUBSCRIBE | 1,000 msg/sec | p99 < 10ms |
| R4: Mixed (realistic) | 40% GET, 30% SET, 30% PUB/SUB | 5,000 ops/sec | p99 < 10ms |

---

## 2. Load Testing Tools

### 2.1 Locust (Python-Native, Recommended for ConductorAI)

Locust is ideal because ConductorAI is Python async and Locust supports custom Python test logic.

**Installation:**

```bash
pip install locust
```

### 2.2 k6 (For HTTP Endpoint Testing)

k6 is best for load testing the HealthChecker HTTP endpoint and any REST API layer built on top of ConductorAI.

**Installation:**

```bash
# macOS
brew install k6

# Linux
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D68
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

---

## 3. Baseline Metrics from Prometheus

### 3.1 Key Metrics to Collect

Before load testing, establish baselines from ConductorAI's `MetricsCollector`:

```promql
# Workflow throughput (rate over 5 minutes)
rate(conductorai_workflows_total[5m])

# Workflow success rate
sum(rate(conductorai_workflows_total{status="success"}[5m]))
/
sum(rate(conductorai_workflows_total[5m]))

# Task duration by agent type (p50, p90, p99)
histogram_quantile(0.50, rate(conductorai_task_duration_seconds_bucket[5m]))
histogram_quantile(0.90, rate(conductorai_task_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(conductorai_task_duration_seconds_bucket[5m]))

# Active agents
conductorai_active_agents

# Error rate
rate(conductorai_errors_total[5m])

# LLM request rate by provider
rate(conductorai_llm_requests_total[5m])

# LLM token consumption rate
rate(conductorai_llm_tokens_total[5m])
```

### 3.2 Grafana Dashboard Configuration

```json
{
  "dashboard": {
    "title": "ConductorAI Load Test Dashboard",
    "panels": [
      {
        "title": "Workflow Throughput",
        "type": "timeseries",
        "targets": [
          {"expr": "rate(conductorai_workflows_total[1m])", "legendFormat": "{{status}}"}
        ]
      },
      {
        "title": "Task Duration (p99) by Agent Type",
        "type": "timeseries",
        "targets": [
          {"expr": "histogram_quantile(0.99, rate(conductorai_task_duration_seconds_bucket[1m]))", "legendFormat": "{{agent_type}}"}
        ]
      },
      {
        "title": "Active Agents",
        "type": "gauge",
        "targets": [
          {"expr": "conductorai_active_agents", "legendFormat": "{{agent_type}}"}
        ]
      },
      {
        "title": "Error Rate",
        "type": "timeseries",
        "targets": [
          {"expr": "rate(conductorai_errors_total[1m])", "legendFormat": "{{error_code}}"}
        ]
      },
      {
        "title": "LLM Requests/sec",
        "type": "timeseries",
        "targets": [
          {"expr": "rate(conductorai_llm_requests_total[1m])", "legendFormat": "{{provider}}/{{model}}"}
        ]
      },
      {
        "title": "Redis Connection Pool",
        "type": "gauge",
        "targets": [
          {"expr": "redis_connected_clients", "legendFormat": "connections"}
        ]
      }
    ]
  }
}
```

### 3.3 Baseline Recording

Before each load test, record the baseline metrics:

```bash
#!/bin/bash
# record-baseline.sh -- Capture baseline metrics before load test
PROM_URL="${PROMETHEUS_URL:-http://prometheus:9090}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

for metric in \
  "conductorai_workflows_total" \
  "conductorai_tasks_total" \
  "conductorai_task_duration_seconds_bucket" \
  "conductorai_active_agents" \
  "conductorai_errors_total" \
  "conductorai_llm_requests_total" \
  "conductorai_llm_tokens_total"; do
  curl -s "${PROM_URL}/api/v1/query?query=${metric}" \
    > "baseline-${metric}-${TIMESTAMP}.json"
done

echo "Baseline recorded at ${TIMESTAMP}"
```

---

## 4. Bottleneck Identification Checklist

After each load test, systematically check for bottlenecks:

### 4.1 Application Layer

- [ ] **Event loop saturation**: asyncio event loop blocked > 100ms?
  - Check: `asyncio.get_event_loop().slow_callback_duration`
  - Symptom: All task durations increase uniformly
- [ ] **Agent pool exhaustion**: All agents of a type are busy?
  - Check: `conductorai_active_agents{agent_type="coding"}` equals registered agent count
  - Symptom: Tasks queue up, workflow duration increases
- [ ] **Memory leak**: RSS growing over time during soak test?
  - Check: Process RSS via `psutil` or container metrics
  - Symptom: OOM kills during extended runs
- [ ] **GIL contention**: CPU-bound work blocking event loop?
  - Check: `py-spy` profiling during load test
  - Symptom: Uneven task distribution, high p99 latency

### 4.2 Redis Layer

- [ ] **Connection pool exhaustion**: Pool at `max_connections` (default: 10)?
  - Check: `redis_connected_clients` vs `RedisConfig.max_connections`
  - Fix: Increase `max_connections` in `RedisConfig`
- [ ] **Redis CPU saturation**: Redis instance at 100% CPU?
  - Check: `redis_cpu_user` + `redis_cpu_sys`
  - Fix: Enable Redis Cluster for sharding
- [ ] **Key eviction**: `evicted_keys` counter increasing?
  - Check: `redis_evicted_keys_total`
  - Fix: Increase Redis `maxmemory` or review key TTL policies
- [ ] **Slow commands**: Commands taking > 10ms?
  - Check: Redis `SLOWLOG GET 10`
  - Fix: Optimize key patterns, use pipelining

### 4.3 LLM Provider Layer

- [ ] **Rate limiting**: HTTP 429 errors from LLM providers?
  - Check: `conductorai_errors_total{error_code="RATE_LIMITED"}`
  - Fix: Implement request queuing, reduce concurrency, upgrade API tier
- [ ] **Timeout errors**: LLM requests timing out?
  - Check: `conductorai_errors_total{error_code="LLM_TIMEOUT"}`
  - Fix: Increase timeout, implement retry with backoff (ErrorHandler)
- [ ] **Token budget exhaustion**: Hitting monthly token limits?
  - Check: `conductorai_llm_tokens_total` cumulative
  - Fix: Implement token budgeting, use smaller models for simpler tasks

### 4.4 Infrastructure Layer

- [ ] **CPU throttling**: Container CPU limits being hit?
  - Check: `container_cpu_cfs_throttled_seconds_total`
  - Fix: Increase CPU limits or optimize code
- [ ] **Memory pressure**: Container approaching memory limits?
  - Check: `container_memory_working_set_bytes` vs limits
  - Fix: Increase limits, profile memory usage, fix leaks
- [ ] **Network saturation**: High network I/O between app and Redis?
  - Check: `container_network_transmit_bytes_total`
  - Fix: Optimize payload sizes, use Redis pipelining

---

## 5. Sample Locust Script for Workflow Execution

### 5.1 Full Load Test Script

```python
"""
ConductorAI Load Test with Locust
===================================

This script simulates concurrent workflow executions against ConductorAI.
Since ConductorAI is an async Python framework (not an HTTP server),
we use Locust's custom User class to drive the async API directly.

Usage:
    # Start Locust web UI
    locust -f load_test_conductor.py --host=localhost

    # Headless mode (CI/CD)
    locust -f load_test_conductor.py \
        --host=localhost \
        --headless \
        --users 20 \
        --spawn-rate 2 \
        --run-time 10m \
        --csv=results/load-test

Requirements:
    pip install locust conductor-ai
"""

import asyncio
import time
import uuid
from typing import Any

from locust import User, task, between, events
from locust.runners import MasterRunner

from conductor.facade import ConductorAI
from conductor.core.config import ConductorConfig, LLMConfig, RedisConfig
from conductor.core.enums import AgentType, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.devops.devops_agent import DevOpsAgent


# ---------------------------------------------------------------------------
# Shared ConductorAI instance (initialized once per worker)
# ---------------------------------------------------------------------------
_conductor: ConductorAI | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Get or create an event loop for the worker process."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


async def _initialize_conductor() -> ConductorAI:
    """Initialize a shared ConductorAI instance with mock LLM."""
    config = ConductorConfig(
        environment="dev",
        log_level="WARNING",  # Reduce log noise during load test
        llm=LLMConfig(provider="mock"),  # Use mock provider for load testing
        redis=RedisConfig(
            url="redis://localhost:6379/0",
            max_connections=50,  # Higher pool for load test
        ),
        max_agent_retries=1,
        workflow_timeout_seconds=120,
    )

    conductor = ConductorAI(config)
    await conductor.initialize()

    # Register agents (shared across all simulated users)
    for i in range(5):  # 5 instances of each agent type
        await conductor.register_agent(
            CodingAgent(f"coding-{i:02d}", AgentType.CODING, config)
        )
        await conductor.register_agent(
            ReviewAgent(f"review-{i:02d}", AgentType.REVIEW, config)
        )
        await conductor.register_agent(
            TestAgent(f"test-{i:02d}", AgentType.TEST, config)
        )
        await conductor.register_agent(
            DevOpsAgent(f"devops-{i:02d}", AgentType.DEVOPS, config)
        )

    return conductor


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize ConductorAI when the test starts."""
    global _conductor
    if not isinstance(environment.runner, MasterRunner):
        loop = _get_event_loop()
        _conductor = loop.run_until_complete(_initialize_conductor())
        print(f"ConductorAI initialized: {_conductor}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Shutdown ConductorAI when the test stops."""
    global _conductor
    if _conductor is not None:
        loop = _get_event_loop()
        loop.run_until_complete(_conductor.shutdown())
        print("ConductorAI shut down")


# ---------------------------------------------------------------------------
# Workflow Definition Generators
# ---------------------------------------------------------------------------

def create_simple_workflow() -> WorkflowDefinition:
    """Create a simple 2-task workflow (code + review)."""
    workflow_id = f"loadtest-simple-{uuid.uuid4().hex[:8]}"
    return WorkflowDefinition(
        workflow_id=workflow_id,
        name=f"Load Test Simple Workflow",
        phases=[WorkflowPhase.DEVELOPMENT],
        tasks=[
            TaskDefinition(
                name="Generate Code",
                assigned_to=AgentType.CODING,
                input_data={
                    "specification": "Create a Python function that calculates fibonacci numbers.",
                    "language": "python",
                },
            ),
            TaskDefinition(
                name="Review Code",
                assigned_to=AgentType.REVIEW,
                input_data={
                    "code": "def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)",
                    "review_criteria": ["correctness", "performance"],
                },
            ),
        ],
    )


def create_full_workflow() -> WorkflowDefinition:
    """Create a full 3-phase workflow (dev + devops + monitoring)."""
    workflow_id = f"loadtest-full-{uuid.uuid4().hex[:8]}"
    return WorkflowDefinition(
        workflow_id=workflow_id,
        name="Load Test Full Workflow",
        phases=[WorkflowPhase.DEVELOPMENT, WorkflowPhase.DEVOPS],
        tasks=[
            TaskDefinition(
                name="Generate Code",
                assigned_to=AgentType.CODING,
                input_data={
                    "specification": "Build a REST API with FastAPI for user management.",
                    "language": "python",
                },
            ),
            TaskDefinition(
                name="Review Code",
                assigned_to=AgentType.REVIEW,
                input_data={
                    "code": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/users')\ndef get_users(): return []",
                    "review_criteria": ["security", "performance", "style"],
                },
            ),
            TaskDefinition(
                name="Generate Tests",
                assigned_to=AgentType.TEST,
                input_data={
                    "code": "from fastapi import FastAPI\napp = FastAPI()",
                    "test_framework": "pytest",
                },
            ),
            TaskDefinition(
                name="Create CI/CD Pipeline",
                assigned_to=AgentType.DEVOPS,
                input_data={
                    "project_name": "user-service",
                    "deployment_target": "kubernetes",
                },
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Locust User Class
# ---------------------------------------------------------------------------

class ConductorUser(User):
    """Simulates a ConductorAI user running workflows."""

    # Wait 1-3 seconds between tasks
    wait_time = between(1, 3)

    @task(3)
    def run_simple_workflow(self):
        """Run a simple 2-task workflow (most common operation)."""
        loop = _get_event_loop()
        definition = create_simple_workflow()

        start_time = time.monotonic()
        try:
            state = loop.run_until_complete(
                _conductor.run_workflow(definition)
            )
            duration_ms = (time.monotonic() - start_time) * 1000

            # Report success to Locust
            events.request.fire(
                request_type="WORKFLOW",
                name="simple_workflow",
                response_time=duration_ms,
                response_length=len(str(state.task_results)),
                exception=None,
                context={},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            events.request.fire(
                request_type="WORKFLOW",
                name="simple_workflow",
                response_time=duration_ms,
                response_length=0,
                exception=e,
                context={},
            )

    @task(1)
    def run_full_workflow(self):
        """Run a full multi-phase workflow (less frequent)."""
        loop = _get_event_loop()
        definition = create_full_workflow()

        start_time = time.monotonic()
        try:
            state = loop.run_until_complete(
                _conductor.run_workflow(definition)
            )
            duration_ms = (time.monotonic() - start_time) * 1000

            events.request.fire(
                request_type="WORKFLOW",
                name="full_workflow",
                response_time=duration_ms,
                response_length=len(str(state.task_results)),
                exception=None,
                context={},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            events.request.fire(
                request_type="WORKFLOW",
                name="full_workflow",
                response_time=duration_ms,
                response_length=0,
                exception=e,
                context={},
            )

    @task(5)
    def dispatch_single_task(self):
        """Dispatch a single task (most frequent operation)."""
        loop = _get_event_loop()
        task_def = TaskDefinition(
            name="Single Task",
            assigned_to=AgentType.CODING,
            input_data={
                "specification": "Write a hello world function.",
                "language": "python",
            },
        )

        start_time = time.monotonic()
        try:
            result = loop.run_until_complete(
                _conductor.dispatch_task(task_def)
            )
            duration_ms = (time.monotonic() - start_time) * 1000

            events.request.fire(
                request_type="TASK",
                name="single_task_dispatch",
                response_time=duration_ms,
                response_length=len(str(result.output_data)),
                exception=None,
                context={},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            events.request.fire(
                request_type="TASK",
                name="single_task_dispatch",
                response_time=duration_ms,
                response_length=0,
                exception=e,
                context={},
            )
```

### 5.2 k6 Script for HealthChecker Endpoint

```javascript
// k6-health-endpoint.js
// Load test the HealthChecker HTTP endpoint
// Usage: k6 run --vus 50 --duration 5m k6-health-endpoint.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const healthCheckDuration = new Trend('health_check_duration');
const healthCheckFailRate = new Rate('health_check_failures');

export const options = {
  stages: [
    { duration: '1m', target: 10 },   // Ramp up
    { duration: '3m', target: 50 },   // Sustained load
    { duration: '1m', target: 100 },  // Peak load
    { duration: '1m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(99)<500'],        // 99% of requests under 500ms
    health_check_failures: ['rate<0.01'],    // Less than 1% failures
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

export default function () {
  // Health check endpoint
  const healthRes = http.get(`${BASE_URL}/health`);
  healthCheckDuration.add(healthRes.timings.duration);

  const healthCheck = check(healthRes, {
    'health status is 200': (r) => r.status === 200,
    'health response has status field': (r) => JSON.parse(r.body).status !== undefined,
    'health status is healthy': (r) => JSON.parse(r.body).status === 'healthy',
    'response time < 200ms': (r) => r.timings.duration < 200,
  });

  if (!healthCheck) {
    healthCheckFailRate.add(1);
  } else {
    healthCheckFailRate.add(0);
  }

  sleep(0.5);
}
```

### 5.3 Running Load Tests

```bash
# Locust -- Web UI mode
locust -f load_test_conductor.py --host=localhost

# Locust -- Headless CI/CD mode
locust -f load_test_conductor.py \
    --host=localhost \
    --headless \
    --users 20 \
    --spawn-rate 2 \
    --run-time 10m \
    --csv=results/load-test \
    --html=results/load-test-report.html

# k6 -- Health endpoint
k6 run \
    --out json=results/k6-health.json \
    --env BASE_URL=http://localhost:8080 \
    k6-health-endpoint.js

# View k6 results
k6 run --summary-trend-stats="avg,min,med,max,p(90),p(95),p(99)" k6-health-endpoint.js
```

---

## 6. Results Analysis

### 6.1 Performance Report Template

```markdown
# Load Test Report: [Date]

## Test Configuration
- **Tool:** Locust / k6
- **Duration:** [X minutes]
- **Virtual Users:** [X ramped to Y]
- **ConductorAI Config:** [environment, agent count, Redis config]
- **LLM Provider:** Mock / OpenAI / Anthropic

## Results Summary

| Metric | Baseline | Under Load | Delta |
|--------|----------|-----------|-------|
| Workflow throughput (req/s) | | | |
| Workflow p50 latency | | | |
| Workflow p99 latency | | | |
| Task dispatch p50 | | | |
| Task dispatch p99 | | | |
| Error rate | | | |
| Redis ops/sec | | | |
| Memory usage (peak) | | | |
| CPU usage (peak) | | | |

## Bottlenecks Identified
1. [Bottleneck and evidence]
2. [Bottleneck and evidence]

## Recommendations
1. [Recommendation]
2. [Recommendation]
```

### 6.2 Acceptance Criteria

| Metric | Minimum Acceptable | Target | Stretch |
|--------|-------------------|--------|---------|
| Workflow throughput | 5 workflows/min | 20 workflows/min | 50 workflows/min |
| Task p99 latency | < 60s | < 30s | < 10s |
| Error rate | < 5% | < 1% | < 0.1% |
| Health endpoint p99 | < 500ms | < 100ms | < 50ms |
| Redis p99 latency | < 50ms | < 10ms | < 5ms |
