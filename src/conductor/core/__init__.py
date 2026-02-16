"""
conductor.core - Foundation Layer
=================================

This module contains the foundational building blocks that every other module
in ConductorAI depends on. It provides:

    - config:      Configuration management (ConductorConfig, RedisConfig, LLMConfig)
    - enums:       Type-safe enumerations (AgentType, WorkflowPhase, TaskStatus, etc.)
    - models:      Core Pydantic data models (TaskDefinition, TaskResult, AgentIdentity)
    - exceptions:  Custom exception hierarchy for structured error handling
    - messages:    Agent communication message types (built in Day 2)
    - state:       Agent and workflow state models (built in Day 2)

Design Principle:
    Everything in `core` is a plain data structure or configuration — no business
    logic, no I/O, no side effects. This makes core types safe to import anywhere
    without risking circular dependencies.

Dependency Rule:
    core/ depends on NOTHING else in the conductor package.
    Every other package (agents/, orchestration/, infrastructure/, integrations/)
    depends on core/.
"""

# =============================================================================
# Re-exports for convenient importing
# =============================================================================
# Instead of:  from conductor.core.config import ConductorConfig
# Users can:   from conductor.core import ConductorConfig
# =============================================================================
from conductor.core.config import ConductorConfig, LLMConfig, RedisConfig
from conductor.core.enums import (
    AgentStatus,
    AgentType,
    MessageType,
    Priority,
    TaskStatus,
    WorkflowPhase,
)
from conductor.core.exceptions import (
    AgentError,
    ConductorError,
    ConfigurationError,
    MessageBusError,
    PolicyViolationError,
    StateError,
    WorkflowError,
)
from conductor.core.models import (
    AgentIdentity,
    TaskDefinition,
    TaskResult,
    WorkflowDefinition,
)

# =============================================================================
# Public API
# =============================================================================
# __all__ explicitly declares what `from conductor.core import *` exports.
# This is good practice for library modules to prevent namespace pollution.
# =============================================================================
__all__ = [
    # Config
    "ConductorConfig",
    "RedisConfig",
    "LLMConfig",
    # Enums
    "AgentType",
    "AgentStatus",
    "WorkflowPhase",
    "MessageType",
    "Priority",
    "TaskStatus",
    # Models
    "AgentIdentity",
    "TaskDefinition",
    "TaskResult",
    "WorkflowDefinition",
    # Exceptions
    "ConductorError",
    "AgentError",
    "WorkflowError",
    "ConfigurationError",
    "MessageBusError",
    "StateError",
    "PolicyViolationError",
]
