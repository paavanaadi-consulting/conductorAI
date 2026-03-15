"""
conductor.infrastructure.metrics - Prometheus Metrics
=====================================================

Provides a MetricsCollector that wraps prometheus_client counters, histograms,
and gauges for observability of ConductorAI workflows, tasks, agents, and LLM
calls. Falls back to a no-op implementation when prometheus_client is not
installed (optional dependency).

Usage:
    from conductor.infrastructure.metrics import MetricsCollector

    metrics = MetricsCollector()          # real metrics if prometheus_client installed
    metrics.record_workflow_completed("success")
    metrics.record_task_completed("CodingAgent", "success", 12.5)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator

import structlog

logger = structlog.get_logger()

try:
    from prometheus_client import Counter, Gauge, Histogram

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


class MetricsCollector:
    """Prometheus metrics for ConductorAI.

    If prometheus_client is installed, creates real Prometheus metrics.
    Otherwise, all methods are silent no-ops.

    Metrics exposed:
        conductorai_workflows_total         Counter(status)
        conductorai_tasks_total             Counter(agent_type, status)
        conductorai_task_duration_seconds   Histogram(agent_type)
        conductorai_active_agents           Gauge(agent_type)
        conductorai_errors_total            Counter(error_code)
        conductorai_llm_requests_total      Counter(provider, model)
        conductorai_llm_tokens_total        Counter(provider, token_type)
    """

    def __init__(self, prefix: str = "conductorai") -> None:
        self._enabled = _PROMETHEUS_AVAILABLE
        self._prefix = prefix

        if self._enabled:
            self._workflows_total = Counter(
                f"{prefix}_workflows_total",
                "Total workflows executed",
                ["status"],
            )
            self._tasks_total = Counter(
                f"{prefix}_tasks_total",
                "Total tasks executed",
                ["agent_type", "status"],
            )
            self._task_duration = Histogram(
                f"{prefix}_task_duration_seconds",
                "Task execution duration in seconds",
                ["agent_type"],
                buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
            )
            self._active_agents = Gauge(
                f"{prefix}_active_agents",
                "Number of currently active agents",
                ["agent_type"],
            )
            self._errors_total = Counter(
                f"{prefix}_errors_total",
                "Total errors by error code",
                ["error_code"],
            )
            self._llm_requests_total = Counter(
                f"{prefix}_llm_requests_total",
                "Total LLM API requests",
                ["provider", "model"],
            )
            self._llm_tokens_total = Counter(
                f"{prefix}_llm_tokens_total",
                "Total LLM tokens consumed",
                ["provider", "token_type"],
            )

    @property
    def enabled(self) -> bool:
        """Whether real Prometheus metrics are being collected."""
        return self._enabled

    # -- Workflow metrics -------------------------------------------------------

    def record_workflow_completed(self, status: str) -> None:
        """Record a completed workflow. Status: 'success', 'failure', 'timeout'."""
        if self._enabled:
            self._workflows_total.labels(status=status).inc()

    # -- Task metrics -----------------------------------------------------------

    def record_task_completed(
        self, agent_type: str, status: str, duration_seconds: float
    ) -> None:
        """Record a completed task with its duration."""
        if self._enabled:
            self._tasks_total.labels(agent_type=agent_type, status=status).inc()
            self._task_duration.labels(agent_type=agent_type).observe(duration_seconds)

    @contextmanager
    def track_task(self, agent_type: str) -> Generator[None, None, None]:
        """Context manager that tracks task duration and active agent count."""
        if self._enabled:
            self._active_agents.labels(agent_type=agent_type).inc()
        start = time.monotonic()
        status = "success"
        try:
            yield
        except Exception:
            status = "failure"
            raise
        finally:
            duration = time.monotonic() - start
            if self._enabled:
                self._active_agents.labels(agent_type=agent_type).dec()
                self._tasks_total.labels(agent_type=agent_type, status=status).inc()
                self._task_duration.labels(agent_type=agent_type).observe(duration)

    # -- Agent metrics ----------------------------------------------------------

    def set_active_agents(self, agent_type: str, count: int) -> None:
        """Set the current number of active agents of a given type."""
        if self._enabled:
            self._active_agents.labels(agent_type=agent_type).set(count)

    # -- Error metrics ----------------------------------------------------------

    def record_error(self, error_code: str) -> None:
        """Record an error occurrence by error code."""
        if self._enabled:
            self._errors_total.labels(error_code=error_code).inc()

    # -- LLM metrics ------------------------------------------------------------

    def record_llm_request(self, provider: str, model: str) -> None:
        """Record an LLM API request."""
        if self._enabled:
            self._llm_requests_total.labels(provider=provider, model=model).inc()

    def record_llm_tokens(
        self, provider: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        """Record LLM token usage."""
        if self._enabled:
            self._llm_tokens_total.labels(
                provider=provider, token_type="prompt"
            ).inc(prompt_tokens)
            self._llm_tokens_total.labels(
                provider=provider, token_type="completion"
            ).inc(completion_tokens)


class NoOpMetricsCollector(MetricsCollector):
    """A metrics collector that never records anything.

    Use this when you want to explicitly disable metrics regardless
    of whether prometheus_client is installed.
    """

    def __init__(self) -> None:
        self._enabled = False
        self._prefix = ""
