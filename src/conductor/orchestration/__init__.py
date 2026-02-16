"""
conductor.orchestration - Orchestration Layer
===============================================

This package contains the orchestration components that control and coordinate
the multi-agent system. It sits above the agent layer and controls agent
lifecycle, communication, and workflow execution.

Components (built across Days 3-5):
    - MessageBus:      Agent-to-agent communication (pub/sub + request-response)
    - StateManager:    Persistent state storage for agents and workflows
    - ErrorHandler:    Retry logic, circuit breakers, dead letter queue
    - PolicyEngine:    Rule evaluation and enforcement
    - AgentCoordinator: Agent lifecycle and task dispatch management
    - WorkflowEngine:  Multi-phase workflow execution with feedback loops
"""

from conductor.orchestration.message_bus import InMemoryMessageBus, MessageBus
from conductor.orchestration.state_manager import InMemoryStateManager, StateManager

__all__ = [
    "MessageBus",
    "InMemoryMessageBus",
    "StateManager",
    "InMemoryStateManager",
]
