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

from conductor.orchestration.agent_coordinator import AgentCoordinator
from conductor.orchestration.error_handler import (
    CircuitBreaker,
    CircuitBreakerState,
    ErrorAction,
    ErrorHandler,
    RetryPolicy,
)
from conductor.orchestration.message_bus import InMemoryMessageBus, MessageBus
from conductor.orchestration.policy_engine import (
    AgentAvailabilityPolicy,
    MaxConcurrentTasksPolicy,
    PhaseGatePolicy,
    Policy,
    PolicyEngine,
    PolicyResult,
    TaskTimeoutPolicy,
)
from conductor.orchestration.state_manager import InMemoryStateManager, StateManager
from conductor.orchestration.workflow_engine import WorkflowEngine

__all__ = [
    # Day 3: Message Bus
    "MessageBus",
    "InMemoryMessageBus",
    # Day 3: State Manager
    "StateManager",
    "InMemoryStateManager",
    # Day 4: Error Handler
    "ErrorAction",
    "ErrorHandler",
    "RetryPolicy",
    "CircuitBreaker",
    "CircuitBreakerState",
    # Day 4: Policy Engine
    "Policy",
    "PolicyEngine",
    "PolicyResult",
    "MaxConcurrentTasksPolicy",
    "TaskTimeoutPolicy",
    "PhaseGatePolicy",
    "AgentAvailabilityPolicy",
    # Day 5: Agent Coordinator
    "AgentCoordinator",
    # Day 5: Workflow Engine
    "WorkflowEngine",
]
