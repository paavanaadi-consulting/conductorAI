"""
Tests for conductor.orchestration.policy_engine
=================================================

These tests verify the Policy Engine — the rule enforcement layer of ConductorAI.
The Policy Engine evaluates registered policies before actions are taken.

What's Being Tested:
    - PolicyResult:               Data model correctness
    - Policy ABC:                 Interface contract
    - MaxConcurrentTasksPolicy:   Concurrency limit enforcement
    - TaskTimeoutPolicy:          Timeout bounds validation
    - PhaseGatePolicy:            Phase transition quality gates
    - AgentAvailabilityPolicy:    Agent status-based availability
    - PolicyEngine:               Registration, evaluation, enforcement, check

All tests are async (pytest-asyncio with asyncio_mode=auto).

Architecture Context:
    The Policy Engine is the gatekeeper:

    Coordinator → [PolicyEngine.enforce(ctx)] → allowed? → Agent
                                               → denied?  → PolicyViolationError
"""

import pytest

from conductor.core.enums import AgentStatus, AgentType, TaskStatus, WorkflowPhase
from conductor.core.exceptions import PolicyViolationError
from conductor.core.models import TaskDefinition
from conductor.core.state import AgentState, WorkflowState
from conductor.orchestration.policy_engine import (
    AgentAvailabilityPolicy,
    MaxConcurrentTasksPolicy,
    PhaseGatePolicy,
    Policy,
    PolicyEngine,
    PolicyResult,
    TaskTimeoutPolicy,
)


# =============================================================================
# Helper: Create test entities
# =============================================================================

def _make_agent_state(
    agent_id: str = "coding-01",
    status: AgentStatus = AgentStatus.IDLE,
) -> AgentState:
    """Create an AgentState for testing."""
    return AgentState(
        agent_id=agent_id,
        agent_type=AgentType.CODING,
        status=status,
    )


def _make_workflow_state(
    completed: int = 0,
    failed: int = 0,
) -> WorkflowState:
    """Create a WorkflowState with embedded task results for testing.

    Uses model_copy to set task_results that produce the right
    completed_task_count and failed_task_count.
    """
    from conductor.core.models import TaskResult

    task_results = {}
    for i in range(completed):
        task_results[f"completed-{i}"] = TaskResult(
            task_id=f"completed-{i}",
            agent_id="agent",
            status=TaskStatus.COMPLETED,
        )
    for i in range(failed):
        task_results[f"failed-{i}"] = TaskResult(
            task_id=f"failed-{i}",
            agent_id="agent",
            status=TaskStatus.FAILED,
        )

    return WorkflowState(
        workflow_id="wf-01",
        current_phase=WorkflowPhase.DEVELOPMENT,
        status=TaskStatus.IN_PROGRESS,
        task_results=task_results,
    )


# =============================================================================
# Test: PolicyResult Model
# =============================================================================
class TestPolicyResult:
    """Tests for the PolicyResult Pydantic model."""

    def test_allowed_result(self) -> None:
        """PolicyResult should support allowed=True with a reason."""
        result = PolicyResult(
            allowed=True,
            policy_name="TestPolicy",
            reason="All checks passed",
        )
        assert result.allowed is True
        assert result.policy_name == "TestPolicy"
        assert result.reason == "All checks passed"

    def test_denied_result_with_metadata(self) -> None:
        """PolicyResult should support metadata dict for programmatic use."""
        result = PolicyResult(
            allowed=False,
            policy_name="MaxConcurrentTasksPolicy",
            reason="5 of 5 slots used",
            metadata={"running_count": 5, "max_tasks": 5},
        )
        assert result.allowed is False
        assert result.metadata["running_count"] == 5
        assert result.metadata["max_tasks"] == 5

    def test_defaults(self) -> None:
        """PolicyResult should have empty defaults for reason and metadata."""
        result = PolicyResult(allowed=True, policy_name="Test")
        assert result.reason == ""
        assert result.metadata == {}


# =============================================================================
# Test: MaxConcurrentTasksPolicy
# =============================================================================
class TestMaxConcurrentTasksPolicy:
    """Tests for the concurrency limit policy."""

    async def test_under_limit_allows(self) -> None:
        """When running agents < max, should allow."""
        policy = MaxConcurrentTasksPolicy(max_tasks=3)

        result = await policy.evaluate({
            "agent_states": [
                _make_agent_state("a", AgentStatus.RUNNING),
                _make_agent_state("b", AgentStatus.IDLE),
                _make_agent_state("c", AgentStatus.COMPLETED),
            ],
        })

        assert result.allowed is True, (
            "1 running agent out of 3 max should be allowed"
        )

    async def test_at_limit_denies(self) -> None:
        """When running agents >= max, should deny."""
        policy = MaxConcurrentTasksPolicy(max_tasks=2)

        result = await policy.evaluate({
            "agent_states": [
                _make_agent_state("a", AgentStatus.RUNNING),
                _make_agent_state("b", AgentStatus.RUNNING),
                _make_agent_state("c", AgentStatus.IDLE),
            ],
        })

        assert result.allowed is False, (
            "2 running agents at limit of 2 should be denied"
        )
        assert "2" in result.reason
        assert result.metadata["running_count"] == 2

    async def test_no_running_agents_allows(self) -> None:
        """When no agents are running, should allow."""
        policy = MaxConcurrentTasksPolicy(max_tasks=5)

        result = await policy.evaluate({
            "agent_states": [
                _make_agent_state("a", AgentStatus.IDLE),
                _make_agent_state("b", AgentStatus.COMPLETED),
            ],
        })

        assert result.allowed is True

    async def test_missing_context_fails_open(self) -> None:
        """Missing agent_states should fail-open (allow with skip note)."""
        policy = MaxConcurrentTasksPolicy(max_tasks=3)

        result = await policy.evaluate({})  # No agent_states key

        assert result.allowed is True
        assert result.metadata.get("skipped") is True

    def test_name_and_description(self) -> None:
        """Policy should have name and description properties."""
        policy = MaxConcurrentTasksPolicy(max_tasks=5)
        assert policy.name == "MaxConcurrentTasksPolicy"
        assert "5" in policy.description


# =============================================================================
# Test: TaskTimeoutPolicy
# =============================================================================
class TestTaskTimeoutPolicy:
    """Tests for the task timeout bounds policy."""

    async def test_valid_timeout_allows(self) -> None:
        """A timeout within bounds (0 < t < 3600) should be allowed."""
        policy = TaskTimeoutPolicy()

        task = TaskDefinition(
            name="test task",
            agent_type=AgentType.CODING,
            timeout_seconds=120,
        )
        result = await policy.evaluate({"task": task})

        assert result.allowed is True

    async def test_default_timeout_allows(self) -> None:
        """The default timeout_seconds from TaskDefinition should pass."""
        policy = TaskTimeoutPolicy()

        task = TaskDefinition(
            name="test task",
            agent_type=AgentType.CODING,
        )
        result = await policy.evaluate({"task": task})

        assert result.allowed is True

    async def test_missing_context_fails_open(self) -> None:
        """Missing task in context should fail-open."""
        policy = TaskTimeoutPolicy()

        result = await policy.evaluate({})

        assert result.allowed is True
        assert result.metadata.get("skipped") is True

    def test_name_and_description(self) -> None:
        """Policy should have name and description."""
        policy = TaskTimeoutPolicy(default_timeout=300.0)
        assert policy.name == "TaskTimeoutPolicy"
        assert "300" in policy.description


# =============================================================================
# Test: PhaseGatePolicy
# =============================================================================
class TestPhaseGatePolicy:
    """Tests for the phase transition quality gate policy."""

    async def test_above_threshold_allows(self) -> None:
        """Success rate above threshold should allow phase transition.

        8 completed + 2 failed = 80% success >= 80% required → allowed
        """
        policy = PhaseGatePolicy(required_success_rate=0.8)

        wf = _make_workflow_state(completed=8, failed=2)
        result = await policy.evaluate({"workflow_state": wf})

        assert result.allowed is True, (
            "80% success rate should meet 80% threshold"
        )

    async def test_below_threshold_denies(self) -> None:
        """Success rate below threshold should deny phase transition.

        6 completed + 4 failed = 60% success < 80% required → denied
        """
        policy = PhaseGatePolicy(required_success_rate=0.8)

        wf = _make_workflow_state(completed=6, failed=4)
        result = await policy.evaluate({"workflow_state": wf})

        assert result.allowed is False, (
            "60% success rate should be below 80% threshold"
        )

    async def test_no_completed_tasks_denies(self) -> None:
        """Zero completed tasks should deny (can't assess quality).

        Even with zero failures, if nothing has completed, the gate blocks.
        """
        policy = PhaseGatePolicy()

        wf = _make_workflow_state(completed=0, failed=0)
        result = await policy.evaluate({"workflow_state": wf})

        assert result.allowed is False, (
            "Zero completed tasks should block phase transition"
        )

    async def test_all_tasks_completed_allows(self) -> None:
        """100% success rate should always allow."""
        policy = PhaseGatePolicy(required_success_rate=1.0)

        wf = _make_workflow_state(completed=5, failed=0)
        result = await policy.evaluate({"workflow_state": wf})

        assert result.allowed is True

    async def test_missing_context_fails_open(self) -> None:
        """Missing workflow_state should fail-open."""
        policy = PhaseGatePolicy()

        result = await policy.evaluate({})

        assert result.allowed is True
        assert result.metadata.get("skipped") is True

    def test_name_and_description(self) -> None:
        """Policy should have name and description."""
        policy = PhaseGatePolicy(required_success_rate=0.8)
        assert policy.name == "PhaseGatePolicy"
        assert "80%" in policy.description


# =============================================================================
# Test: AgentAvailabilityPolicy
# =============================================================================
class TestAgentAvailabilityPolicy:
    """Tests for the agent availability check policy."""

    async def test_idle_agent_is_available(self) -> None:
        """IDLE agents should be available for task assignment."""
        policy = AgentAvailabilityPolicy()

        result = await policy.evaluate({
            "agent_state": _make_agent_state("coding-01", AgentStatus.IDLE),
        })

        assert result.allowed is True

    async def test_completed_agent_is_available(self) -> None:
        """COMPLETED agents should be available (finished last task)."""
        policy = AgentAvailabilityPolicy()

        result = await policy.evaluate({
            "agent_state": _make_agent_state("coding-01", AgentStatus.COMPLETED),
        })

        assert result.allowed is True

    async def test_running_agent_is_unavailable(self) -> None:
        """RUNNING agents should NOT be available (already busy)."""
        policy = AgentAvailabilityPolicy()

        result = await policy.evaluate({
            "agent_state": _make_agent_state("coding-01", AgentStatus.RUNNING),
        })

        assert result.allowed is False
        assert "RUNNING" in result.reason

    async def test_failed_agent_is_unavailable(self) -> None:
        """FAILED agents should NOT be available (needs recovery)."""
        policy = AgentAvailabilityPolicy()

        result = await policy.evaluate({
            "agent_state": _make_agent_state("coding-01", AgentStatus.FAILED),
        })

        assert result.allowed is False
        assert "FAILED" in result.reason

    async def test_missing_context_fails_open(self) -> None:
        """Missing agent_state should fail-open."""
        policy = AgentAvailabilityPolicy()

        result = await policy.evaluate({})

        assert result.allowed is True
        assert result.metadata.get("skipped") is True

    def test_name_and_description(self) -> None:
        """Policy should have name and description."""
        policy = AgentAvailabilityPolicy()
        assert policy.name == "AgentAvailabilityPolicy"
        assert len(policy.description) > 0


# =============================================================================
# Test: PolicyEngine
# =============================================================================
class TestPolicyEngine:
    """Tests for the central PolicyEngine orchestrator."""

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def test_starts_with_no_policies(self) -> None:
        """Fresh engine should have zero policies."""
        engine = PolicyEngine()
        assert engine.policy_count == 0
        assert engine.policies == []

    def test_register_policy(self) -> None:
        """register_policy should add a policy to the registry."""
        engine = PolicyEngine()
        engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=5))

        assert engine.policy_count == 1
        assert engine.policies[0].name == "MaxConcurrentTasksPolicy"

    def test_register_multiple_policies(self) -> None:
        """Multiple policies should be stored in registration order."""
        engine = PolicyEngine()
        engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=5))
        engine.register_policy(AgentAvailabilityPolicy())

        assert engine.policy_count == 2
        assert engine.policies[0].name == "MaxConcurrentTasksPolicy"
        assert engine.policies[1].name == "AgentAvailabilityPolicy"

    def test_unregister_policy(self) -> None:
        """unregister_policy should remove the policy by name."""
        engine = PolicyEngine()
        engine.register_policy(MaxConcurrentTasksPolicy())
        engine.register_policy(AgentAvailabilityPolicy())

        removed = engine.unregister_policy("MaxConcurrentTasksPolicy")

        assert removed is True
        assert engine.policy_count == 1
        assert engine.policies[0].name == "AgentAvailabilityPolicy"

    def test_unregister_nonexistent_returns_false(self) -> None:
        """Unregistering a name that doesn't exist should return False."""
        engine = PolicyEngine()

        removed = engine.unregister_policy("NonexistentPolicy")

        assert removed is False

    def test_policies_returns_copy(self) -> None:
        """engine.policies should return a copy, not the internal list."""
        engine = PolicyEngine()
        engine.register_policy(MaxConcurrentTasksPolicy())

        policies = engine.policies
        policies.append(AgentAvailabilityPolicy())  # type: ignore

        assert engine.policy_count == 1, (
            "Modifying the returned list should not affect the engine"
        )

    # -------------------------------------------------------------------------
    # evaluate_all
    # -------------------------------------------------------------------------

    async def test_evaluate_all_empty_engine(self) -> None:
        """evaluate_all with no policies should return empty list."""
        engine = PolicyEngine()

        results = await engine.evaluate_all({"anything": "goes"})

        assert results == []

    async def test_evaluate_all_all_pass(self) -> None:
        """evaluate_all should return results from all policies (all passing)."""
        engine = PolicyEngine()
        engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=5))
        engine.register_policy(AgentAvailabilityPolicy())

        context = {
            "agent_states": [_make_agent_state("a", AgentStatus.IDLE)],
            "agent_state": _make_agent_state("a", AgentStatus.IDLE),
        }

        results = await engine.evaluate_all(context)

        assert len(results) == 2
        assert all(r.allowed for r in results)

    async def test_evaluate_all_some_fail(self) -> None:
        """evaluate_all should return results from all policies (some failing)."""
        engine = PolicyEngine()
        engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=1))
        engine.register_policy(AgentAvailabilityPolicy())

        context = {
            "agent_states": [_make_agent_state("a", AgentStatus.RUNNING)],
            "agent_state": _make_agent_state("a", AgentStatus.RUNNING),
        }

        results = await engine.evaluate_all(context)

        assert len(results) == 2
        # MaxConcurrentTasks: 1 running >= 1 max → denied
        assert results[0].allowed is False
        # AgentAvailability: RUNNING → denied
        assert results[1].allowed is False

    # -------------------------------------------------------------------------
    # enforce
    # -------------------------------------------------------------------------

    async def test_enforce_all_pass_no_exception(self) -> None:
        """enforce should not raise when all policies pass."""
        engine = PolicyEngine()
        engine.register_policy(AgentAvailabilityPolicy())

        context = {
            "agent_state": _make_agent_state("a", AgentStatus.IDLE),
        }

        # Should not raise
        await engine.enforce(context)

    async def test_enforce_raises_on_violation(self) -> None:
        """enforce should raise PolicyViolationError on the first violation."""
        engine = PolicyEngine()
        engine.register_policy(AgentAvailabilityPolicy())

        context = {
            "agent_state": _make_agent_state("a", AgentStatus.FAILED),
        }

        with pytest.raises(PolicyViolationError) as exc_info:
            await engine.enforce(context)

        assert exc_info.value.policy_name == "AgentAvailabilityPolicy"
        assert "FAILED" in str(exc_info.value)

    async def test_enforce_empty_engine(self) -> None:
        """enforce with no policies should not raise (vacuously true)."""
        engine = PolicyEngine()

        # Should not raise
        await engine.enforce({})

    # -------------------------------------------------------------------------
    # check
    # -------------------------------------------------------------------------

    async def test_check_all_pass_returns_true(self) -> None:
        """check should return True when all policies pass."""
        engine = PolicyEngine()
        engine.register_policy(AgentAvailabilityPolicy())

        context = {
            "agent_state": _make_agent_state("a", AgentStatus.IDLE),
        }

        assert await engine.check(context) is True

    async def test_check_any_fail_returns_false(self) -> None:
        """check should return False when any policy fails."""
        engine = PolicyEngine()
        engine.register_policy(AgentAvailabilityPolicy())

        context = {
            "agent_state": _make_agent_state("a", AgentStatus.RUNNING),
        }

        assert await engine.check(context) is False

    async def test_check_empty_engine_returns_true(self) -> None:
        """check with no policies should return True (vacuously true)."""
        engine = PolicyEngine()
        assert await engine.check({}) is True

    # -------------------------------------------------------------------------
    # Error handling during evaluation
    # -------------------------------------------------------------------------

    async def test_policy_evaluation_error_is_caught(self) -> None:
        """If a policy's evaluate() raises, the engine should catch it.

        A buggy policy should not crash the entire evaluation. Instead,
        the engine records a denied result with the error message.
        """
        from typing import Any

        class BuggyPolicy(Policy):
            @property
            def name(self) -> str:
                return "BuggyPolicy"

            @property
            def description(self) -> str:
                return "Always crashes"

            async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
                raise RuntimeError("Bug in policy code!")

        engine = PolicyEngine()
        engine.register_policy(BuggyPolicy())

        results = await engine.evaluate_all({})

        # The error should be caught and recorded as a denied result
        assert len(results) == 1
        assert results[0].allowed is False
        assert "Bug in policy code" in results[0].reason
        assert results[0].policy_name == "BuggyPolicy"
