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

from conductor.infrastructure.artifact_store import (
    Artifact,
    ArtifactStore,
    InMemoryArtifactStore,
)

__all__ = [
    "Artifact",
    "ArtifactStore",
    "InMemoryArtifactStore",
]
