"""
Tests for conductor.infrastructure.health
===========================================
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from conductor.infrastructure.health import (
    ComponentHealth,
    HealthCheckResult,
    HealthChecker,
    HealthStatus,
)


class TestHealthCheckResult:
    """Tests for HealthCheckResult model."""

    def test_healthy_result(self):
        result = HealthCheckResult(
            component="redis",
            status=ComponentHealth.HEALTHY,
            latency_ms=1.5,
        )
        assert result.component == "redis"
        assert result.status == ComponentHealth.HEALTHY
        assert result.latency_ms == 1.5

    def test_unhealthy_result_with_message(self):
        result = HealthCheckResult(
            component="redis",
            status=ComponentHealth.UNHEALTHY,
            message="Connection refused",
        )
        assert result.status == ComponentHealth.UNHEALTHY
        assert result.message == "Connection refused"

    def test_serialization(self):
        result = HealthCheckResult(
            component="llm",
            status=ComponentHealth.HEALTHY,
            details={"provider": "openai"},
        )
        data = result.model_dump()
        assert data["component"] == "llm"
        assert data["details"]["provider"] == "openai"


class TestHealthStatus:
    """Tests for HealthStatus model."""

    def test_overall_healthy(self):
        status = HealthStatus(
            status=ComponentHealth.HEALTHY,
            version="0.1.0",
            environment="dev",
        )
        assert status.status == ComponentHealth.HEALTHY
        assert status.version == "0.1.0"

    def test_serialization(self):
        status = HealthStatus(
            status=ComponentHealth.UNHEALTHY,
            version="0.1.0",
            environment="prod",
            checks=[
                HealthCheckResult(
                    component="redis",
                    status=ComponentHealth.UNHEALTHY,
                    message="down",
                ),
            ],
        )
        data = status.model_dump()
        assert data["status"] == "unhealthy"
        assert len(data["checks"]) == 1


class TestHealthChecker:
    """Tests for HealthChecker."""

    async def test_all_healthy_no_components(self):
        checker = HealthChecker(version="0.1.0", environment="dev")
        status = await checker.check_all()
        assert status.status == ComponentHealth.HEALTHY
        assert len(status.checks) == 3  # state_manager, message_bus, llm

    async def test_state_manager_healthy(self):
        mock_sm = AsyncMock()
        mock_sm.get_agent_state = AsyncMock(return_value=None)
        checker = HealthChecker(state_manager=mock_sm)
        result = await checker.check_state_manager()
        assert result.status == ComponentHealth.HEALTHY
        assert result.latency_ms is not None

    async def test_state_manager_unhealthy(self):
        mock_sm = AsyncMock()
        mock_sm.get_agent_state = AsyncMock(side_effect=ConnectionError("refused"))
        checker = HealthChecker(state_manager=mock_sm)
        result = await checker.check_state_manager()
        assert result.status == ComponentHealth.UNHEALTHY
        assert "refused" in result.message

    async def test_llm_provider_healthy(self):
        mock_llm = MagicMock()
        mock_llm.provider_name = "openai"
        checker = HealthChecker(llm_provider=mock_llm)
        result = await checker.check_llm()
        assert result.status == ComponentHealth.HEALTHY
        assert result.details["provider"] == "openai"

    async def test_llm_provider_none_is_healthy(self):
        checker = HealthChecker()
        result = await checker.check_llm()
        assert result.status == ComponentHealth.HEALTHY
        assert "mock" in result.message.lower() or "not configured" in result.message.lower()

    async def test_aggregation_one_unhealthy(self):
        mock_sm = AsyncMock()
        mock_sm.get_agent_state = AsyncMock(side_effect=RuntimeError("down"))
        checker = HealthChecker(state_manager=mock_sm)
        status = await checker.check_all()
        assert status.status == ComponentHealth.UNHEALTHY

    async def test_check_all_includes_version_and_env(self):
        checker = HealthChecker(version="1.2.3", environment="prod")
        status = await checker.check_all()
        assert status.version == "1.2.3"
        assert status.environment == "prod"

    async def test_check_all_has_timestamp(self):
        checker = HealthChecker()
        status = await checker.check_all()
        assert status.timestamp is not None
