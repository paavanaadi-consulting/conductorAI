"""
conductor.agents - Specialized AI Agent Layer
===============================================

This package contains the agent framework and all specialized agent
implementations. The agent layer sits between the orchestration layer
(which controls agents) and the integration layer (which agents use).

Architecture:
    ┌─────────────── ORCHESTRATION LAYER ─────────────────┐
    │  Coordinator, WorkflowEngine, MessageBus             │
    └─────────────────────┬───────────────────────────────┘
                          │ dispatches tasks
                          ▼
    ┌─────────────── AGENT LAYER ─────────────────────────┐
    │                                                      │
    │  BaseAgent (abstract)                                │
    │    ├── development/                                   │
    │    │   ├── CodingAgent     (code generation)         │
    │    │   ├── ReviewAgent     (code review)             │
    │    │   ├── TestDataAgent   (test data generation)    │
    │    │   └── TestAgent       (test execution)          │
    │    ├── devops/                                        │
    │    │   ├── DevOpsAgent     (CI/CD configuration)     │
    │    │   └── DeployingAgent  (deployment)              │
    │    └── monitoring/                                    │
    │        └── MonitorAgent    (monitoring & feedback)    │
    │                                                      │
    └──────────────────────────────────────────────────────┘
                          │ uses
                          ▼
    ┌─────────────── INTEGRATION LAYER ───────────────────┐
    │  LLM Providers, Cloud, CI/CD, Notifications          │
    └──────────────────────────────────────────────────────┘

Usage:
    from conductor.agents.base import BaseAgent
    from conductor.agents.development.coding_agent import CodingAgent
"""

from conductor.agents.base import BaseAgent
from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.development.test_data_agent import TestDataAgent
from conductor.agents.devops.deploying_agent import DeployingAgent
from conductor.agents.devops.devops_agent import DevOpsAgent
from conductor.agents.monitoring.monitor_agent import MonitorAgent

__all__ = [
    "BaseAgent",
    "CodingAgent",
    "DeployingAgent",
    "DevOpsAgent",
    "MonitorAgent",
    "ReviewAgent",
    "TestAgent",
    "TestDataAgent",
]
