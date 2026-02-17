"""
conductor.agents.devops - DevOps Phase Agents
================================================

This package contains the agents that operate during the DEVOPS phase
of the ConductorAI workflow pipeline.

DevOps Phase Flow:
    ┌─────────────┐     ┌────────────────┐
    │ DevOpsAgent │ ──→ │ DeployingAgent │
    │ (CI/CD)     │     │ (deployment)   │
    └─────────────┘     └────────────────┘

Agents:
    - DevOpsAgent:     Generates CI/CD configurations (GitHub Actions, Docker, etc.).
    - DeployingAgent:  Generates deployment configurations (Kubernetes, Terraform, etc.).

Usage:
    from conductor.agents.devops import DevOpsAgent, DeployingAgent
"""

from conductor.agents.devops.deploying_agent import DeployingAgent
from conductor.agents.devops.devops_agent import DevOpsAgent

__all__ = [
    "DeployingAgent",
    "DevOpsAgent",
]
