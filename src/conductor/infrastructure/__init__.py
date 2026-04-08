"""
conductor.infrastructure - Data & Infrastructure Layer
========================================================

This package provides the data persistence and infrastructure components
that the agent and orchestration layers rely on. It implements the repository
pattern for storing and retrieving artifacts produced during workflows.

Architecture:
    ┌─────────────── ORCHESTRATION LAYER ─────────────────┐
    │  WorkflowEngine, Coordinator, MessageBus             │
    └─────────────────────┬───────────────────────────────┘
                          │
    ┌─────────────── AGENT LAYER ─────────────────────────┐
    │  CodingAgent, ReviewAgent, TestAgent, DevOpsAgent... │
    └─────────────────────┬───────────────────────────────┘
                          │ stores artifacts
                          ▼
    ┌─────────────── INFRASTRUCTURE LAYER ────────────────┐
    │                                                      │
    │  ArtifactStore (ABC)                                │
    │    └── InMemoryArtifactStore                        │
    │                                                      │
    │  Artifact (model)                                    │
    │    - code, configs, test data, deployment manifests   │
    │                                                      │
    └──────────────────────────────────────────────────────┘

Components:
    - Artifact:               Pydantic model for workflow artifacts
    - ArtifactStore (ABC):    Abstract interface for artifact persistence
    - InMemoryArtifactStore:  In-memory implementation for development/testing

Usage:
    from conductor.infrastructure import InMemoryArtifactStore, Artifact
"""

from src.conductor.infrastructure.artifact_store import (
    Artifact,
    ArtifactStore,
    InMemoryArtifactStore,
)
from src.conductor.infrastructure.health import (
    ComponentHealth,
    HealthCheckResult,
    HealthChecker,
    HealthStatus,
)
from src.conductor.infrastructure.metrics import (
    MetricsCollector,
    NoOpMetricsCollector,
)
from src.conductor.infrastructure.secrets import (
    AWSSecretsProvider,
    EnvSecretsProvider,
    SecretsProvider,
    VaultSecretsProvider,
)
from src.conductor.infrastructure.tracing import (
    NoOpTracingProvider,
    TracingProvider,
)

__all__ = [
    # Artifacts
    "Artifact",
    "ArtifactStore",
    "InMemoryArtifactStore",
    # Health
    "ComponentHealth",
    "HealthCheckResult",
    "HealthChecker",
    "HealthStatus",
    # Metrics
    "MetricsCollector",
    "NoOpMetricsCollector",
    # Secrets
    "SecretsProvider",
    "EnvSecretsProvider",
    "VaultSecretsProvider",
    "AWSSecretsProvider",
    # Tracing
    "TracingProvider",
    "NoOpTracingProvider",
]
