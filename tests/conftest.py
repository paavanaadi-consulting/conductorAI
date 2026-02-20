"""
Shared Test Fixtures for ConductorAI
=======================================

This module provides reusable pytest fixtures used across the entire
test suite. Fixtures are organized by layer:

    1. Configuration fixtures
    2. Infrastructure fixtures (ArtifactStore)
    3. Orchestration fixtures (MessageBus, StateManager, PolicyEngine, etc.)
    4. Integration fixtures (LLM providers)
    5. Agent fixtures (all 7 agent types)
    6. Facade fixtures (ConductorAI)
"""

from __future__ import annotations

import pytest

from conductor.agents.development.coding_agent import CodingAgent
from conductor.agents.development.review_agent import ReviewAgent
from conductor.agents.development.test_agent import TestAgent
from conductor.agents.development.test_data_agent import TestDataAgent
from conductor.agents.devops.deploying_agent import DeployingAgent
from conductor.agents.devops.devops_agent import DevOpsAgent
from conductor.agents.monitoring.monitor_agent import MonitorAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.infrastructure.artifact_store import InMemoryArtifactStore
from conductor.integrations.llm.mock import MockLLMProvider
from conductor.orchestration.error_handler import ErrorHandler
from conductor.orchestration.message_bus import InMemoryMessageBus
from conductor.orchestration.policy_engine import PolicyEngine
from conductor.orchestration.state_manager import InMemoryStateManager


# =============================================================================
# Configuration
# =============================================================================

@pytest.fixture
def config():
    """ConductorAI configuration with defaults."""
    return ConductorConfig()


# =============================================================================
# Infrastructure
# =============================================================================

@pytest.fixture
def artifact_store():
    """Fresh InMemoryArtifactStore."""
    return InMemoryArtifactStore()


# =============================================================================
# Orchestration
# =============================================================================

@pytest.fixture
def message_bus():
    """Fresh InMemoryMessageBus."""
    return InMemoryMessageBus()


@pytest.fixture
def state_manager():
    """Fresh InMemoryStateManager."""
    return InMemoryStateManager()


@pytest.fixture
def policy_engine():
    """Fresh PolicyEngine with no policies registered."""
    return PolicyEngine()


@pytest.fixture
def error_handler(message_bus, state_manager):
    """ErrorHandler wired to the message bus and state manager."""
    return ErrorHandler(
        message_bus=message_bus,
        state_manager=state_manager,
    )


# =============================================================================
# LLM Provider
# =============================================================================

@pytest.fixture
def mock_llm_provider():
    """Fresh MockLLMProvider with no queued responses."""
    return MockLLMProvider()


# =============================================================================
# Agents
# =============================================================================

@pytest.fixture
def coding_agent(config, mock_llm_provider):
    """CodingAgent with mock LLM provider."""
    return CodingAgent("coding-01", config, llm_provider=mock_llm_provider)


@pytest.fixture
def review_agent(config, mock_llm_provider):
    """ReviewAgent with mock LLM provider."""
    return ReviewAgent("review-01", config, llm_provider=mock_llm_provider)


@pytest.fixture
def test_data_agent(config, mock_llm_provider):
    """TestDataAgent with mock LLM provider."""
    return TestDataAgent("testdata-01", config, llm_provider=mock_llm_provider)


@pytest.fixture
def test_agent(config, mock_llm_provider):
    """TestAgent with mock LLM provider."""
    return TestAgent("test-01", config, llm_provider=mock_llm_provider)


@pytest.fixture
def devops_agent(config, mock_llm_provider):
    """DevOpsAgent with mock LLM provider."""
    return DevOpsAgent("devops-01", config, llm_provider=mock_llm_provider)


@pytest.fixture
def deploying_agent(config, mock_llm_provider):
    """DeployingAgent with mock LLM provider."""
    return DeployingAgent("deploying-01", config, llm_provider=mock_llm_provider)


@pytest.fixture
def monitor_agent(config, mock_llm_provider):
    """MonitorAgent with mock LLM provider."""
    return MonitorAgent("monitor-01", config, llm_provider=mock_llm_provider)


# =============================================================================
# Task Definitions
# =============================================================================

@pytest.fixture
def coding_task():
    """A basic coding task definition."""
    return TaskDefinition(
        name="Generate Code",
        assigned_to=AgentType.CODING,
        input_data={
            "specification": "Create a hello world function",
            "language": "python",
        },
    )


@pytest.fixture
def review_task():
    """A basic review task definition."""
    return TaskDefinition(
        name="Review Code",
        assigned_to=AgentType.REVIEW,
        input_data={
            "code": "def hello(): return 'Hello, World!'",
            "review_criteria": ["style", "correctness"],
        },
    )


@pytest.fixture
def simple_workflow():
    """A single-phase DEVELOPMENT workflow with one coding task."""
    return WorkflowDefinition(
        name="Simple Test Workflow",
        phases=[WorkflowPhase.DEVELOPMENT],
        tasks=[
            TaskDefinition(
                name="Generate Code",
                assigned_to=AgentType.CODING,
                input_data={
                    "specification": "Hello world function",
                    "language": "python",
                },
            ),
        ],
    )
