"""
conductor.agents.development - Development Phase Agents
=========================================================

This package contains the agents that operate during the DEVELOPMENT phase
of the ConductorAI workflow pipeline.

Development Phase Flow:
    ┌─────────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────┐
    │ CodingAgent │ ──→ │ ReviewAgent │ ──→ │ TestDataAgent│ ──→ │TestAgent │
    │ (generates) │     │ (reviews)   │     │ (fixtures)   │     │ (tests)  │
    └─────────────┘     └─────────────┘     └──────────────┘     └──────────┘

Agents:
    - CodingAgent:   Generates source code from specifications using LLM.
    - ReviewAgent:   Reviews generated code for quality, bugs, best practices.
    - TestDataAgent: Generates test data and fixtures (Day 7).
    - TestAgent:     Creates and runs test suites (Day 7).

Usage:
    from conductor.agents.development import CodingAgent, ReviewAgent
"""

from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.development.test_data_agent import TestDataAgent

__all__ = [
    "CodingAgent",
    "ReviewAgent",
    "TestAgent",
    "TestDataAgent",
]
