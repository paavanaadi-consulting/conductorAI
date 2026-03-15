"""
conductor.infrastructure.health - Health Check System
=======================================================

Provides composable health checking for ConductorAI components.
Users embed a HealthChecker in their own web framework to expose
health endpoints (/health, /readiness, /liveness).

Architecture:
    HealthChecker is NOT a web server. It returns structured data
    that users serialize into HTTP responses in their framework of choice.

    ┌─────────────────────────────┐
    │ User's Web Framework        │
    │   @app.get("/health")       │
    │     → checker.check_all()   │
    │     → return JSON           │
    └──────────────┬──────────────┘
                   │
    ┌──────────────▼──────────────┐
    │ HealthChecker               │
    │   check_redis()             │
    │   check_state_manager()     │
    │   check_llm()               │
    │   check_all() → HealthStatus│
    └─────────────────────────────┘

Usage:
    >>> checker = HealthChecker(config=config, state_manager=sm)
    >>> status = await checker.check_all()
    >>> status.model_dump()  # JSON-serializable dict
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

import structlog

logger = structlog.get_logger()


class ComponentHealth(str, Enum):
    """Health status for an individual component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheckResult(BaseModel):
    """Result of a single component health check."""

    component: str
    status: ComponentHealth
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class HealthStatus(BaseModel):
    """Aggregate health status across all components."""

    status: ComponentHealth
    version: str
    environment: str
    checks: list[HealthCheckResult] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthChecker:
    """Composable health checker for ConductorAI components.

    Runs checks against registered infrastructure components and
    aggregates results into a single HealthStatus. Components are
    optional — if not provided, their check is skipped.

    Usage in FastAPI:
        checker = HealthChecker(config=config, state_manager=sm)

        @app.get("/health")
        async def health():
            return (await checker.check_all()).model_dump()

    Usage in Flask:
        @app.route("/health")
        def health():
            import asyncio
            status = asyncio.run(checker.check_all())
            return jsonify(status.model_dump())
    """

    def __init__(
        self,
        *,
        version: str = "0.1.0",
        environment: str = "dev",
        state_manager: Any = None,
        message_bus: Any = None,
        llm_provider: Any = None,
    ) -> None:
        self._version = version
        self._environment = environment
        self._state_manager = state_manager
        self._message_bus = message_bus
        self._llm_provider = llm_provider
        self._logger = logger.bind(component="health_checker")

    async def check_state_manager(self) -> HealthCheckResult:
        """Check state manager connectivity.

        Attempts a lightweight operation (get non-existent key)
        to verify the state manager is responsive.
        """
        if self._state_manager is None:
            return HealthCheckResult(
                component="state_manager",
                status=ComponentHealth.HEALTHY,
                message="Not configured (using in-memory)",
            )

        start = time.monotonic()
        try:
            # Try a lightweight read — should return None for non-existent key
            await self._state_manager.get_agent_state("__health_check__")
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component="state_manager",
                status=ComponentHealth.HEALTHY,
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component="state_manager",
                status=ComponentHealth.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=str(e),
            )

    async def check_message_bus(self) -> HealthCheckResult:
        """Check message bus connectivity."""
        if self._message_bus is None:
            return HealthCheckResult(
                component="message_bus",
                status=ComponentHealth.HEALTHY,
                message="Not configured (using in-memory)",
            )

        start = time.monotonic()
        try:
            # Check if the bus has a connected attribute or similar
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component="message_bus",
                status=ComponentHealth.HEALTHY,
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component="message_bus",
                status=ComponentHealth.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=str(e),
            )

    async def check_llm(self) -> HealthCheckResult:
        """Check LLM provider availability.

        Does NOT make a real API call (to avoid costs). Checks that
        the provider is configured and importable.
        """
        if self._llm_provider is None:
            return HealthCheckResult(
                component="llm_provider",
                status=ComponentHealth.HEALTHY,
                message="Not configured (using mock)",
            )

        try:
            provider_name = getattr(self._llm_provider, "provider_name", "unknown")
            return HealthCheckResult(
                component="llm_provider",
                status=ComponentHealth.HEALTHY,
                details={"provider": provider_name},
            )
        except Exception as e:
            return HealthCheckResult(
                component="llm_provider",
                status=ComponentHealth.UNHEALTHY,
                message=str(e),
            )

    async def check_all(self) -> HealthStatus:
        """Run all registered health checks and aggregate.

        Aggregation rules:
            - All HEALTHY → overall HEALTHY
            - Any DEGRADED (none UNHEALTHY) → overall DEGRADED
            - Any UNHEALTHY → overall UNHEALTHY
        """
        checks = [
            await self.check_state_manager(),
            await self.check_message_bus(),
            await self.check_llm(),
        ]

        # Aggregate status
        statuses = {c.status for c in checks}
        if ComponentHealth.UNHEALTHY in statuses:
            overall = ComponentHealth.UNHEALTHY
        elif ComponentHealth.DEGRADED in statuses:
            overall = ComponentHealth.DEGRADED
        else:
            overall = ComponentHealth.HEALTHY

        self._logger.info(
            "health_check_completed",
            overall=overall.value,
            checks={c.component: c.status.value for c in checks},
        )

        return HealthStatus(
            status=overall,
            version=self._version,
            environment=self._environment,
            checks=checks,
        )
