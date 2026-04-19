# ConductorAI Performance Tuning Guide

**Last Updated:** 2026-03-14
**Audience:** SRE, Backend Engineers, Infrastructure Team
**Prerequisite:** Read `load-testing-guide.md` for baseline measurement methodology

---

## 1. Redis Tuning

Redis serves as both the MessageBus (pub/sub) and StateManager (state persistence) backend for ConductorAI. Redis performance directly impacts workflow throughput and task latency.

### 1.1 Connection Pooling

ConductorAI uses `RedisConfig.max_connections` to control the connection pool size. The default of 10 is suitable for development but too low for production.

```python
from conductor.core.config import RedisConfig, ConductorConfig

# Development (default)
dev_redis = RedisConfig(
    max_connections=10,  # Default: sufficient for dev/testing
)

# Production -- single instance
prod_redis = RedisConfig(
    url="rediss://redis.internal:6380/0",
    max_connections=50,    # 50 connections for moderate workloads
    socket_timeout=5.0,    # 5 second timeout
    ssl=True,
)

# Production -- heavy workload
heavy_redis = RedisConfig(
    url="rediss://redis.internal:6380/0",
    max_connections=100,   # 100 connections for high throughput
    socket_timeout=3.0,    # Tighter timeout for faster failure detection
    ssl=True,
)
```

**Sizing Guide:**

| Concurrent Workflows | Recommended `max_connections` | Justification |
|---------------------|------------------------------|---------------|
| 1-5 | 10 (default) | Minimal pool sufficient |
| 5-20 | 25-50 | Each workflow uses ~2-3 connections (state reads/writes + pub/sub) |
| 20-50 | 50-100 | Avoid connection wait times under load |
| 50-100 | 100-200 | Ensure pool never blocks; monitor with `redis_connected_clients` |

**Monitoring Connection Pool Health:**

```bash
# Check current connections
redis-cli --tls -h redis.internal -p 6380 INFO clients
# connected_clients:45
# blocked_clients:0      <-- Should always be 0
# maxclients:10000

# Check connection pool utilization
redis-cli --tls -h redis.internal -p 6380 INFO stats
# total_connections_received:1234
# rejected_connections:0   <-- Non-zero means pool exhaustion
```

### 1.2 Pipelining

Redis pipelining batches multiple commands into a single network round-trip. ConductorAI's StateManager can benefit from pipelining when saving multiple states in a single workflow phase.

```python
"""Example: Redis pipelining for batch state operations."""
import redis.asyncio as aioredis

async def batch_save_task_results(
    redis_client: aioredis.Redis,
    results: dict[str, dict],
    key_prefix: str = "conductor:",
) -> None:
    """Save multiple task results in a single pipeline.

    Without pipelining: N round-trips (one per SET commands)
    With pipelining: 1 round-trip for N commands

    For a workflow with 4 tasks, this reduces latency from ~20ms to ~5ms.
    """
    async with redis_client.pipeline(transaction=False) as pipe:
        for task_id, result_json in results.items():
            key = f"{key_prefix}task_result:{task_id}"
            pipe.set(key, result_json)
            pipe.expire(key, 90 * 24 * 3600)  # 90-day TTL
        await pipe.execute()


async def batch_read_workflow_state(
    redis_client: aioredis.Redis,
    workflow_id: str,
    task_ids: list[str],
    key_prefix: str = "conductor:",
) -> dict:
    """Read workflow state and all task results in a single pipeline."""
    async with redis_client.pipeline(transaction=False) as pipe:
        # Queue workflow state read
        pipe.get(f"{key_prefix}workflow:{workflow_id}")
        # Queue all task result reads
        for task_id in task_ids:
            pipe.get(f"{key_prefix}task_result:{task_id}")
        results = await pipe.execute()

    return {
        "workflow_state": results[0],
        "task_results": {
            task_id: results[i + 1]
            for i, task_id in enumerate(task_ids)
        },
    }
```

### 1.3 Key Expiry and Memory Management

Proper key expiry prevents Redis memory from growing unbounded.

```ini
# redis.conf -- Memory management
maxmemory 2gb
maxmemory-policy allkeys-lru

# Lazy freeing (non-blocking key deletion)
lazyfree-lazy-eviction yes
lazyfree-lazy-expire yes
lazyfree-lazy-server-del yes
```

**ConductorAI Key Expiry Strategy:**

| Key Pattern | TTL | Rationale |
|------------|-----|-----------|
| `conductor:workflow:{id}` | 90 days | Long-term audit trail |
| `conductor:task_result:{id}` | 90 days | Paired with workflow state |
| `conductor:agent:{id}` | 7 days | Transient; agents re-register on startup |
| `conductor:dlq:{id}` | 30 days | Dead-letter entries need review |
| `conductor:artifact:{id}` | 180 days | Generated code/configs |
| `conductor:channel:*` | No TTL | Pub/sub channels are ephemeral |

```python
"""Automated key expiry enforcement."""
import redis.asyncio as aioredis

KEY_TTLS = {
    "conductor:workflow:": 90 * 86400,
    "conductor:task_result:": 90 * 86400,
    "conductor:agent:": 7 * 86400,
    "conductor:dlq:": 30 * 86400,
    "conductor:artifact:": 180 * 86400,
}

async def enforce_ttls(redis_client: aioredis.Redis) -> dict:
    """Scan all conductor: keys and set TTLs where missing."""
    stats = {"checked": 0, "updated": 0}

    async for key in redis_client.scan_iter("conductor:*", count=100):
        stats["checked"] += 1
        ttl = await redis_client.ttl(key)

        if ttl == -1:  # No expiry set
            key_str = key.decode() if isinstance(key, bytes) else key
            for prefix, target_ttl in KEY_TTLS.items():
                if key_str.startswith(prefix):
                    await redis_client.expire(key, target_ttl)
                    stats["updated"] += 1
                    break

    return stats
```

### 1.4 Redis Configuration Tuning

```ini
# redis.conf -- Performance tuning for ConductorAI workloads

# --- Network ---
tcp-backlog 511
tcp-keepalive 300
timeout 0

# --- Memory ---
maxmemory 4gb
maxmemory-policy allkeys-lru
maxmemory-samples 10

# --- Persistence (balanced for ConductorAI) ---
# RDB for periodic snapshots
save 60 100
save 300 10

# AOF for durability
appendonly yes
appendfsync everysec

# --- Performance ---
# Disable slow operations
slowlog-log-slower-than 10000    # Log commands > 10ms
slowlog-max-len 128

# IO threads for Redis 6+ (read/write parallelism)
io-threads 4
io-threads-do-reads yes

# Lazy freeing
lazyfree-lazy-eviction yes
lazyfree-lazy-expire yes
lazyfree-lazy-server-del yes
replica-lazy-flush yes

# --- Client output buffers ---
# Pub/sub clients (MessageBus) need larger buffers
client-output-buffer-limit pubsub 256mb 128mb 60
client-output-buffer-limit normal 0 0 0
```

---

## 2. Asyncio Optimization

ConductorAI is built entirely on Python `asyncio`. Optimizing the event loop and task management directly impacts throughput.

### 2.1 Event Loop Configuration

```python
"""Asyncio event loop optimization for ConductorAI."""
import asyncio
import sys

def configure_event_loop():
    """Configure the asyncio event loop for optimal ConductorAI performance."""

    # Use uvloop if available (2-4x faster than default loop)
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        print("Using uvloop event loop (recommended)")
    except ImportError:
        print("uvloop not available; using default asyncio loop")
        print("Install with: pip install uvloop")

    # Enable debug mode in development to catch slow callbacks
    if sys.flags.dev_mode:
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.slow_callback_duration = 0.1  # Warn on callbacks > 100ms


# Call at application startup, before creating ConductorAI
configure_event_loop()
```

**Install uvloop:**

```bash
pip install uvloop
```

**Benchmark difference:**

| Event Loop | Workflow/sec (mock LLM) | Task Dispatch Latency (p50) |
|-----------|------------------------|---------------------------|
| Default asyncio | ~15 | ~8ms |
| uvloop | ~40 | ~3ms |

### 2.2 Task Concurrency Control

ConductorAI's WorkflowEngine executes tasks sequentially within a phase. For independent tasks within the same phase, concurrent execution improves throughput.

```python
"""Concurrent task execution within a workflow phase."""
import asyncio
from conductor.core.models import TaskDefinition, TaskResult
from conductor.orchestration.agent_coordinator import AgentCoordinator

async def execute_phase_tasks_concurrent(
    coordinator: AgentCoordinator,
    tasks: list[TaskDefinition],
    max_concurrency: int = 5,
) -> list[TaskResult]:
    """Execute tasks concurrently with bounded concurrency.

    Uses asyncio.Semaphore to limit concurrent agent executions,
    preventing Redis connection pool exhaustion and LLM rate limiting.

    Args:
        coordinator: AgentCoordinator for task dispatch.
        tasks: Tasks to execute.
        max_concurrency: Maximum simultaneous task executions.

    Returns:
        List of TaskResults in input order.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def dispatch_with_limit(task: TaskDefinition) -> TaskResult:
        async with semaphore:
            return await coordinator.dispatch_task(task)

    # Execute all tasks concurrently (bounded by semaphore)
    results = await asyncio.gather(
        *[dispatch_with_limit(task) for task in tasks],
        return_exceptions=True,
    )

    # Convert exceptions to failed TaskResults
    processed = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed.append(TaskResult(
                task_id=tasks[i].task_id,
                agent_id="coordinator",
                status="failed",
                error_message=str(result),
            ))
        else:
            processed.append(result)

    return processed
```

**Concurrency Sizing Guide:**

| Resource Constraint | Recommended `max_concurrency` | Rationale |
|-------------------|------------------------------|-----------|
| Redis pool = 10 | 3-5 | Leave headroom for state saves |
| Redis pool = 50 | 10-20 | Each task needs ~2 connections |
| LLM rate limit = 60 RPM | 5-10 | Avoid 429 rate limit errors |
| LLM rate limit = 600 RPM | 20-50 | Higher tier allows more concurrency |

### 2.3 Avoiding Event Loop Blocking

Common blocking operations in ConductorAI and how to avoid them:

```python
"""Patterns to avoid event loop blocking."""
import asyncio
from functools import partial
from concurrent.futures import ThreadPoolExecutor

# Create a thread pool for CPU-bound work
_executor = ThreadPoolExecutor(max_workers=4)


# BAD: Synchronous file I/O blocks the event loop
def bad_save_artifact(path: str, content: str):
    with open(path, 'w') as f:
        f.write(content)  # Blocks event loop!


# GOOD: Use asyncio's run_in_executor for file I/O
async def good_save_artifact(path: str, content: str):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor,
        partial(_write_file, path, content),
    )

def _write_file(path: str, content: str):
    with open(path, 'w') as f:
        f.write(content)


# BAD: CPU-bound work in async context
async def bad_process_output(data: str) -> str:
    import json
    result = json.loads(data)  # Fine for small data
    # But this blocks for large payloads:
    processed = heavy_computation(result)  # Blocks event loop!
    return processed


# GOOD: Offload CPU-bound work
async def good_process_output(data: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        partial(_process_output_sync, data),
    )

def _process_output_sync(data: str) -> str:
    import json
    result = json.loads(data)
    return heavy_computation(result)


# GOOD: Use asyncio.wait_for to prevent indefinite hangs
async def safe_llm_call(provider, messages, timeout=60):
    """Call LLM with explicit timeout to prevent event loop starvation."""
    try:
        return await asyncio.wait_for(
            provider.generate(messages),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"LLM call timed out after {timeout}s")
```

### 2.4 Structured Concurrency with TaskGroups (Python 3.11+)

```python
"""Using TaskGroups for structured concurrency in workflow phases."""
import asyncio
from conductor.core.models import TaskDefinition, TaskResult

async def execute_phase_with_taskgroup(
    coordinator,
    tasks: list[TaskDefinition],
) -> list[TaskResult]:
    """Execute tasks using Python 3.11+ TaskGroup for structured concurrency.

    Benefits over asyncio.gather:
    - Automatic cancellation of remaining tasks if one fails
    - Clear exception propagation
    - No orphaned tasks
    """
    results: dict[str, TaskResult] = {}

    async with asyncio.TaskGroup() as tg:
        for task in tasks:
            async def dispatch(t=task):
                result = await coordinator.dispatch_task(t)
                results[t.task_id] = result

            tg.create_task(dispatch())

    return [results[task.task_id] for task in tasks]
```

---

## 3. LLM Batching and Caching Strategies

### 3.1 Request Batching

When multiple agents need LLM calls simultaneously, batch them to reduce API overhead.

```python
"""LLM request batching for ConductorAI agents."""
import asyncio
from dataclasses import dataclass
from typing import Any

@dataclass
class LLMBatchRequest:
    """A single LLM request in a batch."""
    request_id: str
    messages: list[dict]
    future: asyncio.Future

class LLMBatcher:
    """Batches LLM requests and sends them together.

    Instead of each agent making individual API calls, requests are
    collected over a short window and sent as concurrent batches.

    This reduces:
    - Connection overhead (fewer TCP handshakes)
    - Rate limit impact (controlled burst size)
    - Overall latency (parallel execution)
    """

    def __init__(
        self,
        provider,
        batch_size: int = 5,
        batch_window_ms: int = 100,
        max_concurrent: int = 10,
    ):
        self._provider = provider
        self._batch_size = batch_size
        self._batch_window_ms = batch_window_ms
        self._max_concurrent = max_concurrent
        self._pending: list[LLMBatchRequest] = []
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._flush_task: asyncio.Task | None = None

    async def generate(self, messages: list[dict]) -> dict:
        """Submit a generation request to the batcher.

        Returns when the LLM response is available.
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        request = LLMBatchRequest(
            request_id=f"req-{id(future)}",
            messages=messages,
            future=future,
        )
        self._pending.append(request)

        # Schedule flush if batch is full or start timer
        if len(self._pending) >= self._batch_size:
            await self._flush()
        elif self._flush_task is None:
            self._flush_task = asyncio.create_task(self._delayed_flush())

        return await future

    async def _delayed_flush(self):
        """Flush after batch window expires."""
        await asyncio.sleep(self._batch_window_ms / 1000)
        await self._flush()

    async def _flush(self):
        """Send all pending requests concurrently."""
        if not self._pending:
            return

        batch = self._pending.copy()
        self._pending.clear()
        self._flush_task = None

        async def process_request(req: LLMBatchRequest):
            async with self._semaphore:
                try:
                    result = await self._provider.generate(req.messages)
                    req.future.set_result(result)
                except Exception as e:
                    req.future.set_exception(e)

        await asyncio.gather(*[process_request(r) for r in batch])
```

### 3.2 Response Caching

Cache LLM responses for identical prompts to reduce API costs and latency.

```python
"""LLM response caching for ConductorAI."""
import hashlib
import json
import time
from typing import Any, Optional

class LLMCache:
    """In-memory LLM response cache with TTL.

    Caches are keyed by a hash of the message content + model parameters.
    Useful when the same prompt is sent repeatedly (e.g., during retries
    or when multiple workflows have identical tasks).

    For production, replace the dict with Redis using the same key prefix:
        conductor:llm_cache:{hash}
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 1000):
        self._cache: dict[str, dict[str, Any]] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    def _make_key(self, messages: list[dict], model: str, temperature: float) -> str:
        """Create a deterministic cache key from request parameters."""
        content = json.dumps({
            "messages": messages,
            "model": model,
            "temperature": temperature,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, messages: list[dict], model: str, temperature: float) -> Optional[dict]:
        """Look up a cached response."""
        key = self._make_key(messages, model, temperature)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        if time.monotonic() - entry["timestamp"] > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry["response"]

    def put(self, messages: list[dict], model: str, temperature: float, response: dict) -> None:
        """Store a response in the cache."""
        # Evict oldest entries if at capacity
        if len(self._cache) >= self._max_entries:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]

        key = self._make_key(messages, model, temperature)
        self._cache[key] = {
            "response": response,
            "timestamp": time.monotonic(),
        }

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def stats(self) -> dict:
        """Cache statistics for monitoring."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 3),
            "entries": len(self._cache),
            "max_entries": self._max_entries,
        }
```

**Redis-Backed Cache for Production:**

```python
"""Redis-backed LLM cache for production deployments."""
import hashlib
import json
import redis.asyncio as aioredis
from typing import Optional

class RedisLLMCache:
    """Production LLM cache backed by Redis.

    Uses the same Redis instance as ConductorAI's StateManager,
    with the key prefix: conductor:llm_cache:
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        ttl_seconds: int = 3600,
        key_prefix: str = "conductor:llm_cache:",
    ):
        self._redis = redis_client
        self._ttl = ttl_seconds
        self._prefix = key_prefix

    def _make_key(self, messages: list[dict], model: str, temperature: float) -> str:
        content = json.dumps({"messages": messages, "model": model, "temperature": temperature}, sort_keys=True)
        return f"{self._prefix}{hashlib.sha256(content.encode()).hexdigest()}"

    async def get(self, messages: list[dict], model: str, temperature: float) -> Optional[dict]:
        key = self._make_key(messages, model, temperature)
        cached = await self._redis.get(key)
        if cached:
            return json.loads(cached)
        return None

    async def put(self, messages: list[dict], model: str, temperature: float, response: dict) -> None:
        key = self._make_key(messages, model, temperature)
        await self._redis.setex(key, self._ttl, json.dumps(response))
```

### 3.3 Model Selection Optimization

```python
"""Use cheaper/faster models for simpler tasks."""

AGENT_MODEL_MAP = {
    # Simple tasks: use faster, cheaper model
    "test_data": {"model": "gpt-3.5-turbo", "max_tokens": 2048},
    "monitor":   {"model": "gpt-3.5-turbo", "max_tokens": 1024},

    # Complex tasks: use more capable model
    "coding":    {"model": "gpt-4", "max_tokens": 4096},
    "review":    {"model": "gpt-4", "max_tokens": 4096},
    "test":      {"model": "gpt-4", "max_tokens": 4096},

    # Infrastructure tasks: moderate model
    "devops":    {"model": "gpt-4", "max_tokens": 2048},
    "deploying": {"model": "gpt-3.5-turbo", "max_tokens": 2048},
}
```

---

## 4. Memory Profiling

### 4.1 Using tracemalloc

```python
"""Memory profiling for ConductorAI with tracemalloc."""
import tracemalloc
import asyncio
import linecache
from conductor.facade import ConductorAI
from conductor.core.config import ConductorConfig

def display_top_allocations(snapshot, key_type='lineno', limit=20):
    """Display top memory allocations from a tracemalloc snapshot."""
    snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
        tracemalloc.Filter(False, "<unknown>"),
    ))
    top_stats = snapshot.statistics(key_type)

    print(f"\nTop {limit} memory allocations:")
    print("=" * 80)
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        print(f"#{index}: {frame.filename}:{frame.lineno}: "
              f"{stat.size / 1024:.1f} KiB ({stat.count} blocks)")
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            print(f"    {line}")

    total = sum(stat.size for stat in top_stats)
    print(f"\nTotal allocated: {total / 1024 / 1024:.1f} MiB")
    print(f"Total allocation blocks: {sum(stat.count for stat in top_stats)}")


async def profile_workflow_memory():
    """Profile memory usage during workflow execution."""
    tracemalloc.start(25)  # 25 frames deep

    # Take baseline snapshot
    snapshot_before = tracemalloc.take_snapshot()

    # Run ConductorAI workflow
    config = ConductorConfig(environment="dev")
    async with ConductorAI(config) as conductor:
        # Register agents and run workflows...
        pass

    # Take post-workflow snapshot
    snapshot_after = tracemalloc.take_snapshot()

    # Compare snapshots to find memory growth
    print("\n--- Memory Growth During Workflow ---")
    top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')

    print(f"\nTop 20 memory growth locations:")
    for stat in top_stats[:20]:
        print(f"  {stat}")

    # Show absolute top allocations
    display_top_allocations(snapshot_after)

    tracemalloc.stop()


# Run the profiler
asyncio.run(profile_workflow_memory())
```

### 4.2 Continuous Memory Monitoring

```python
"""Periodic memory monitoring for production ConductorAI."""
import asyncio
import os
import tracemalloc
import structlog

logger = structlog.get_logger()

class MemoryMonitor:
    """Monitors ConductorAI memory usage and logs warnings."""

    def __init__(
        self,
        warning_threshold_mb: float = 256.0,
        critical_threshold_mb: float = 512.0,
        check_interval_seconds: int = 60,
    ):
        self._warning_mb = warning_threshold_mb
        self._critical_mb = critical_threshold_mb
        self._interval = check_interval_seconds
        self._baseline_mb: float = 0.0

    async def start(self):
        """Start the memory monitoring background task."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            self._baseline_mb = process.memory_info().rss / 1024 / 1024
        except ImportError:
            logger.warning("psutil not installed; memory monitoring limited")
            self._baseline_mb = 0

        asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self):
        """Periodically check memory usage."""
        while True:
            await asyncio.sleep(self._interval)
            try:
                import psutil
                process = psutil.Process(os.getpid())
                rss_mb = process.memory_info().rss / 1024 / 1024
                growth_mb = rss_mb - self._baseline_mb

                if rss_mb > self._critical_mb:
                    logger.critical(
                        "memory_critical",
                        rss_mb=round(rss_mb, 1),
                        growth_mb=round(growth_mb, 1),
                        threshold_mb=self._critical_mb,
                    )
                elif rss_mb > self._warning_mb:
                    logger.warning(
                        "memory_warning",
                        rss_mb=round(rss_mb, 1),
                        growth_mb=round(growth_mb, 1),
                        threshold_mb=self._warning_mb,
                    )
                else:
                    logger.debug(
                        "memory_ok",
                        rss_mb=round(rss_mb, 1),
                    )
            except Exception as e:
                logger.error("memory_monitor_error", error=str(e))
```

### 4.3 Common Memory Issues in ConductorAI

| Issue | Symptom | Root Cause | Fix |
|-------|---------|-----------|-----|
| WorkflowState accumulation | RSS grows linearly with workflows | `task_results` dict retains all results in memory | Persist to Redis, clear from in-memory after save |
| MessageBus subscriber leak | RSS grows with time | Unsubscribed handlers still referenced | Ensure `unsubscribe()` called on agent stop |
| LLM response buffering | Spikes during large outputs | Full response held in memory | Stream responses, process incrementally |
| TaskResult serialization | Spike during `model_dump_json()` | Pydantic creates copies during serialization | Use `model_dump()` with exclude for large fields |
| Dead-letter queue growth | Gradual increase | Failed tasks accumulate without cleanup | Enforce TTL on DLQ entries, periodic purge |

---

## 5. Agent Pool Sizing Recommendations

### 5.1 Sizing Formula

```
Agents per type = ceil(
    (target_workflows_per_minute * tasks_per_workflow_for_type * avg_task_duration_seconds)
    / 60
)
```

**Example:**

| Parameter | Value |
|-----------|-------|
| Target workflows/min | 10 |
| CodingAgent tasks per workflow | 1 |
| CodingAgent avg task duration | 15s |
| Agents needed | ceil(10 * 1 * 15 / 60) = 3 |

### 5.2 Recommended Pool Sizes by Workload

| Agent Type | Light (5 wf/min) | Moderate (20 wf/min) | Heavy (50 wf/min) | Avg Duration |
|-----------|------------------|---------------------|--------------------|-------------|
| CodingAgent | 2 | 5 | 13 | 15s |
| ReviewAgent | 2 | 4 | 10 | 10s |
| TestDataAgent | 1 | 2 | 5 | 5s |
| TestAgent | 2 | 5 | 13 | 15s |
| DevOpsAgent | 1 | 3 | 7 | 8s |
| DeployingAgent | 1 | 2 | 5 | 10s |
| MonitorAgent | 1 | 2 | 5 | 5s |
| **Total agents** | **10** | **23** | **58** | -- |

### 5.3 Agent Registration Configuration

```python
"""Production agent pool configuration."""
from conductor.facade import ConductorAI
from conductor.core.config import ConductorConfig, LLMConfig
from conductor.core.enums import AgentType
from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.development.test_data_agent import TestDataAgent
from conductor.agents.devops.devops_agent import DevOpsAgent
from conductor.agents.devops.deploying_agent import DeployingAgent
from conductor.agents.monitoring.monitor_agent import MonitorAgent

AGENT_POOL_CONFIG = {
    # (AgentClass, AgentType, pool_size)
    "coding":    (CodingAgent,    AgentType.CODING,    5),
    "review":    (ReviewAgent,    AgentType.REVIEW,    4),
    "test_data": (TestDataAgent,  AgentType.TEST_DATA, 2),
    "test":      (TestAgent,      AgentType.TEST,      5),
    "devops":    (DevOpsAgent,    AgentType.DEVOPS,    3),
    "deploying": (DeployingAgent, AgentType.DEPLOYING, 2),
    "monitor":   (MonitorAgent,   AgentType.MONITOR,   2),
}


async def register_agent_pool(conductor: ConductorAI, config: ConductorConfig):
    """Register the full agent pool according to sizing configuration."""
    for name, (agent_cls, agent_type, pool_size) in AGENT_POOL_CONFIG.items():
        for i in range(pool_size):
            agent = agent_cls(
                agent_id=f"{name}-{i:02d}",
                agent_type=agent_type,
                config=config,
                metrics_collector=conductor.metrics,
            )
            await conductor.register_agent(agent)

    total = sum(size for _, _, size in AGENT_POOL_CONFIG.values())
    print(f"Registered {total} agents across {len(AGENT_POOL_CONFIG)} types")
```

### 5.4 Dynamic Scaling

```python
"""Dynamic agent pool scaling based on queue depth."""
import asyncio
import structlog

logger = structlog.get_logger()

class AgentPoolScaler:
    """Automatically scales agent pools based on workload.

    Monitors the ratio of active agents to total agents per type.
    When utilization exceeds a threshold, registers additional agents.
    When utilization drops, unregisters excess agents (down to minimum).
    """

    def __init__(
        self,
        conductor: ConductorAI,
        config: ConductorConfig,
        min_agents_per_type: int = 1,
        max_agents_per_type: int = 20,
        scale_up_threshold: float = 0.8,    # 80% utilization
        scale_down_threshold: float = 0.3,  # 30% utilization
        check_interval: int = 30,
    ):
        self._conductor = conductor
        self._config = config
        self._min = min_agents_per_type
        self._max = max_agents_per_type
        self._up_threshold = scale_up_threshold
        self._down_threshold = scale_down_threshold
        self._interval = check_interval

    async def start(self):
        """Start the auto-scaling background task."""
        asyncio.create_task(self._scaling_loop())

    async def _scaling_loop(self):
        """Periodically evaluate and adjust agent pool sizes."""
        while True:
            await asyncio.sleep(self._interval)
            try:
                coordinator = self._conductor.coordinator
                # Evaluate each agent type
                for agent_type in AgentType:
                    agents = [
                        a for a in coordinator._agents.values()
                        if a.agent_type == agent_type
                    ]
                    if not agents:
                        continue

                    total = len(agents)
                    active = sum(
                        1 for a in agents
                        if a.status.value == "running"
                    )
                    utilization = active / total if total > 0 else 0

                    if utilization > self._up_threshold and total < self._max:
                        logger.info(
                            "scaling_up",
                            agent_type=agent_type.value,
                            current=total,
                            utilization=round(utilization, 2),
                        )
                        # Scale up logic: register new agent

                    elif utilization < self._down_threshold and total > self._min:
                        logger.info(
                            "scaling_down",
                            agent_type=agent_type.value,
                            current=total,
                            utilization=round(utilization, 2),
                        )
                        # Scale down logic: unregister idle agent

            except Exception as e:
                logger.error("scaling_error", error=str(e))
```

---

## 6. Performance Tuning Checklist

Use this checklist before each production deployment:

| # | Category | Item | Default | Recommended (Prod) | Status |
|---|----------|------|---------|-------------------|--------|
| 1 | Redis | `max_connections` | 10 | 50-100 | |
| 2 | Redis | `socket_timeout` | 5.0s | 3.0s | |
| 3 | Redis | TLS enabled | False | True | |
| 4 | Redis | `maxmemory` | unset | 4GB+ | |
| 5 | Redis | `io-threads` | 1 | 4 | |
| 6 | Redis | Key TTLs set | No | Yes (per Section 1.3) | |
| 7 | Asyncio | uvloop installed | No | Yes | |
| 8 | Asyncio | Event loop debug (prod) | Off | Off | |
| 9 | LLM | Response caching | None | TTL cache (1h) | |
| 10 | LLM | Concurrent request limit | Unlimited | Semaphore (10-20) | |
| 11 | LLM | Model selection per agent | gpt-4 (all) | Tiered (see 3.3) | |
| 12 | Agents | Pool size per type | 1 | See Section 5.2 | |
| 13 | Agents | Metrics enabled | Optional | Yes (`MetricsCollector`) | |
| 14 | Config | `max_agent_retries` | 3 | 2-3 | |
| 15 | Config | `workflow_timeout_seconds` | 300 | 120-300 | |
| 16 | Config | `log_level` | INFO | WARNING (high traffic) | |
| 17 | Memory | Memory monitoring | None | `MemoryMonitor` (Section 4.2) | |
| 18 | Memory | tracemalloc (prod) | Off | Off (overhead) | |
| 19 | Container | CPU limit | None | 500m-2000m | |
| 20 | Container | Memory limit | None | 512Mi-2Gi | |
