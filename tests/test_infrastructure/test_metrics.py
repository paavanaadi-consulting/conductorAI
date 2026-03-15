"""
Tests for conductor.infrastructure.metrics
============================================
"""

from __future__ import annotations

import pytest

from conductor.infrastructure.metrics import MetricsCollector, NoOpMetricsCollector


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_enabled_depends_on_prometheus(self):
        collector = MetricsCollector()
        # We can't guarantee prometheus_client is installed, so just check it's a bool
        assert isinstance(collector.enabled, bool)

    def test_record_workflow_no_error(self):
        collector = MetricsCollector()
        collector.record_workflow_completed("success")
        collector.record_workflow_completed("failure")

    def test_record_task_no_error(self):
        collector = MetricsCollector()
        collector.record_task_completed("CodingAgent", "success", 1.5)

    def test_record_error_no_error(self):
        collector = MetricsCollector()
        collector.record_error("WORKFLOW_FAILED")

    def test_record_llm_request_no_error(self):
        collector = MetricsCollector()
        collector.record_llm_request("openai", "gpt-4")

    def test_record_llm_tokens_no_error(self):
        collector = MetricsCollector()
        collector.record_llm_tokens("openai", 100, 50)

    def test_set_active_agents_no_error(self):
        collector = MetricsCollector()
        collector.set_active_agents("CodingAgent", 3)

    def test_track_task_context_manager(self):
        collector = MetricsCollector()
        with collector.track_task("CodingAgent"):
            pass  # simulated work


class TestNoOpMetricsCollector:
    """Tests for NoOpMetricsCollector."""

    def test_noop_disabled(self):
        collector = NoOpMetricsCollector()
        assert collector.enabled is False

    def test_noop_methods_safe(self):
        collector = NoOpMetricsCollector()
        collector.record_workflow_completed("success")
        collector.record_task_completed("CodingAgent", "success", 1.0)
        collector.record_error("ERR")
        collector.record_llm_request("mock", "model")
        collector.record_llm_tokens("mock", 10, 5)
        collector.set_active_agents("CodingAgent", 0)

    def test_noop_track_task(self):
        collector = NoOpMetricsCollector()
        with collector.track_task("CodingAgent"):
            pass
