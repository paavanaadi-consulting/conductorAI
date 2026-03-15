"""
conductor.infrastructure.tracing - Distributed Tracing
=======================================================

Provides a TracingProvider that wraps OpenTelemetry for distributed tracing
of ConductorAI workflows, tasks, and LLM calls. Falls back to a no-op
implementation when opentelemetry packages are not installed.

Usage:
    from conductor.infrastructure.tracing import TracingProvider

    tracer = TracingProvider(service_name="conductorai")
    with tracer.start_workflow_span("wf-123", "deploy-pipeline") as span:
        with tracer.start_task_span("task-456", "CodingAgent", parent=span):
            ...  # agent work happens here
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator, Optional

import structlog

logger = structlog.get_logger()

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


class _NoOpSpan:
    """Minimal span-like object for when OpenTelemetry is not available."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass

    def end(self) -> None:
        pass


class TracingProvider:
    """OpenTelemetry tracing for ConductorAI.

    If opentelemetry-api and opentelemetry-sdk are installed, creates real
    traces. Otherwise, all methods return no-op spans.

    Args:
        service_name: The service name to report in traces.
        exporter: Optional span exporter. If None, no exporter is configured
            (useful for testing; production users add their own exporter).
    """

    def __init__(
        self,
        service_name: str = "conductorai",
        exporter: Any = None,
    ) -> None:
        self._enabled = _OTEL_AVAILABLE
        self._service_name = service_name

        if self._enabled:
            resource = Resource.create({"service.name": service_name})
            self._provider = TracerProvider(resource=resource)
            if exporter is not None:
                self._provider.add_span_processor(
                    SimpleSpanProcessor(exporter)
                )
            trace.set_tracer_provider(self._provider)
            self._tracer = trace.get_tracer(service_name)
        else:
            self._provider = None
            self._tracer = None

    @property
    def enabled(self) -> bool:
        """Whether real OpenTelemetry tracing is active."""
        return self._enabled

    @contextmanager
    def start_workflow_span(
        self,
        workflow_id: str,
        workflow_name: str,
        parent: Any = None,
    ) -> Generator[Any, None, None]:
        """Start a span for a workflow execution."""
        if not self._enabled:
            yield _NoOpSpan()
            return

        ctx = trace.set_span_in_context(parent) if parent else None
        with self._tracer.start_as_current_span(
            f"workflow:{workflow_name}",
            context=ctx,
            attributes={
                "conductor.workflow.id": workflow_id,
                "conductor.workflow.name": workflow_name,
            },
        ) as span:
            yield span

    @contextmanager
    def start_task_span(
        self,
        task_id: str,
        agent_type: str,
        parent: Any = None,
    ) -> Generator[Any, None, None]:
        """Start a span for a task execution within a workflow."""
        if not self._enabled:
            yield _NoOpSpan()
            return

        ctx = trace.set_span_in_context(parent) if parent else None
        with self._tracer.start_as_current_span(
            f"task:{agent_type}",
            context=ctx,
            attributes={
                "conductor.task.id": task_id,
                "conductor.agent.type": agent_type,
            },
        ) as span:
            yield span

    @contextmanager
    def start_llm_span(
        self,
        provider: str,
        model: str,
        parent: Any = None,
    ) -> Generator[Any, None, None]:
        """Start a span for an LLM API call."""
        if not self._enabled:
            yield _NoOpSpan()
            return

        ctx = trace.set_span_in_context(parent) if parent else None
        with self._tracer.start_as_current_span(
            f"llm:{provider}",
            context=ctx,
            attributes={
                "conductor.llm.provider": provider,
                "conductor.llm.model": model,
            },
        ) as span:
            yield span

    def shutdown(self) -> None:
        """Flush and shut down the tracer provider."""
        if self._enabled and self._provider is not None:
            self._provider.shutdown()


class NoOpTracingProvider(TracingProvider):
    """A tracing provider that never creates real spans.

    Use this when you want to explicitly disable tracing regardless
    of whether OpenTelemetry is installed.
    """

    def __init__(self) -> None:
        self._enabled = False
        self._service_name = ""
        self._provider = None
        self._tracer = None
