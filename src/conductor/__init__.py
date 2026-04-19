"""
ConductorAI - Multi-Agent AI Framework
=======================================

ConductorAI is a production-grade framework for orchestrating specialized AI agents
through a multi-phase software development lifecycle:

    Development Phase  →  DevOps Phase  →  Monitoring & Feedback Phase
    (Code → Review       (Build → Deploy)   (Monitor → Feedback Loop)
     → Test)

Architecture Layers (top to bottom):
    1. Orchestration Layer  - Workflow Engine, Coordinator, Message Bus, State Manager
    2. Agent Layer          - Specialized AI Agents (Coding, Review, Test, DevOps, Monitor)
    3. Infrastructure Layer - Storage, Repositories, Observability
    4. Integration Layer    - LLM Providers, Cloud, CI/CD, Notifications

Quick Start:
    >>> from conductor import ConductorAI
    >>> async with ConductorAI() as ai:
    ...     result = await ai.run_workflow(my_plan)

For full documentation, see: docs/getting-started.md
"""

# =============================================================================
# Package Version
# =============================================================================
# Single source of truth for the package version.
# This is referenced by pyproject.toml and can be imported as:
#   from conductor import __version__
# =============================================================================
__version__ = "0.1.0"

# =============================================================================
# Package-Level Exports
# =============================================================================
# The ConductorAI facade is the main entry point for users.
# For specific components, import from submodules directly:
#   from conductor.core.config import ConductorConfig
#   from conductor.core.enums import AgentType
#   from conductor.core.models import TaskDefinition
# =============================================================================
from conductor.facade import ConductorAI

__all__ = ["ConductorAI", "__version__"]
