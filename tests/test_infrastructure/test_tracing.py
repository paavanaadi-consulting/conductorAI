"""
Tests for conductor.infrastructure.tracing
============================================
"""

from __future__ import annotations

import pytest

from conductor.infrastructure.tracing import (
    NoOpTracingProvider,
    TracingProvider,
    _NoOpSpan,
)


class TestNoOpSpan:
    """Tests for _NoOpSpan placeholder."""

    def test_set_attribute(self):
        span = _NoOpSpan()
        span.set_attribute("key", "value")  # should not raise

    def test_record_exception(self):
        span = _NoOpSpan()
        span.record_exception(ValueError("test"))

    def test_end(self):
        span = _NoOpSpan()
        span.end()


class TestTracingProvider:
    """Tests for TracingProvider."""

    def test_enabled_depends_on_otel(self):
        tracer = TracingProvider()
        assert isinstance(tracer.enabled, bool)

    def test_workflow_span_context_manager(self):
        tracer = TracingProvider()
        with tracer.start_workflow_span("wf-1", "test-workflow") as span:
            assert span is not None

    def test_task_span_context_manager(self):
        tracer = TracingProvider()
        with tracer.start_task_span("task-1", "CodingAgent") as span:
            assert span is not None

    def test_llm_span_context_manager(self):
        tracer = TracingProvider()
        with tracer.start_llm_span("openai", "gpt-4") as span:
            assert span is not None

    def test_shutdown_no_error(self):
        tracer = TracingProvider()
        tracer.shutdown()


class TestNoOpTracingProvider:
    """Tests for NoOpTracingProvider."""

    def test_noop_disabled(self):
        tracer = NoOpTracingProvider()
        assert tracer.enabled is False

    def test_noop_workflow_span(self):
        tracer = NoOpTracingProvider()
        with tracer.start_workflow_span("wf-1", "test") as span:
            assert isinstance(span, _NoOpSpan)

    def test_noop_task_span(self):
        tracer = NoOpTracingProvider()
        with tracer.start_task_span("t-1", "Agent") as span:
            assert isinstance(span, _NoOpSpan)

    def test_noop_llm_span(self):
        tracer = NoOpTracingProvider()
        with tracer.start_llm_span("mock", "m") as span:
            assert isinstance(span, _NoOpSpan)

    def test_noop_shutdown(self):
        tracer = NoOpTracingProvider()
        tracer.shutdown()
