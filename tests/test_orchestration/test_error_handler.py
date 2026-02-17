"""
Tests for conductor.orchestration.error_handler
=================================================

These tests verify the ErrorHandler, RetryPolicy, and CircuitBreaker
implementations — the three resilience components of ConductorAI.

What's Being Tested:
    - RetryPolicy:     Exponential backoff calculation, retryable error checks
    - CircuitBreaker:  State transitions (CLOSED→OPEN→HALF_OPEN→CLOSED),
                       failure/success tracking, recovery timeout
    - ErrorHandler:    Decision logic (RETRY/ESCALATE/DEAD_LETTER),
                       circuit breaker integration, DLQ management
    - ErrorAction:     Enum values and string comparison

All tests are async (pytest-asyncio with asyncio_mode=auto).
Uses InMemoryMessageBus and InMemoryStateManager for isolation.

Architecture Context:
    The Error Handler intercepts agent failures and decides:

    Exception → [ErrorHandler] → RETRY (transient, backoff & retry)
                               → ESCALATE (non-retryable, notify coordinator)
                               → DEAD_LETTER (exhausted retries, park for later)
"""

import asyncio
import time

import pytest

from conductor.core.enums import MessageType, Priority
from conductor.core.exceptions import AgentError, ConductorError, MessageBusError
from conductor.core.messages import AgentMessage
from conductor.orchestration.error_handler import (
    CircuitBreaker,
    CircuitBreakerState,
    ErrorAction,
    ErrorHandler,
    RetryPolicy,
)
from conductor.orchestration.message_bus import InMemoryMessageBus
from conductor.orchestration.state_manager import InMemoryStateManager


# =============================================================================
# Test: ErrorAction Enum
# =============================================================================
class TestErrorAction:
    """Tests for the ErrorAction enum values."""

    def test_error_action_values(self) -> None:
        """ErrorAction should have the four expected values."""
        assert ErrorAction.RETRY == "retry"
        assert ErrorAction.ESCALATE == "escalate"
        assert ErrorAction.DEAD_LETTER == "dead_letter"
        assert ErrorAction.SKIP == "skip"


# =============================================================================
# Test: CircuitBreakerState Enum
# =============================================================================
class TestCircuitBreakerState:
    """Tests for the CircuitBreakerState enum values."""

    def test_circuit_breaker_state_values(self) -> None:
        """CircuitBreakerState should have three states."""
        assert CircuitBreakerState.CLOSED == "closed"
        assert CircuitBreakerState.OPEN == "open"
        assert CircuitBreakerState.HALF_OPEN == "half_open"


# =============================================================================
# Test: RetryPolicy
# =============================================================================
class TestRetryPolicy:
    """Tests for the RetryPolicy Pydantic model.

    RetryPolicy configures exponential backoff delays and which errors
    are worth retrying. All delay calculations include a small random
    jitter, so tests use approximate bounds rather than exact values.
    """

    def test_defaults(self) -> None:
        """RetryPolicy should have sensible defaults for LLM-based agents."""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.initial_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.backoff_multiplier == 2.0
        assert "LLM_TIMEOUT" in policy.retryable_errors
        assert "LLM_RATE_LIMIT" in policy.retryable_errors
        assert "TRANSIENT_ERROR" in policy.retryable_errors

    def test_calculate_delay_attempt_zero(self) -> None:
        """First retry (attempt=0) should use ~initial_delay.

        delay = initial_delay * (multiplier^0) + jitter = 1.0 + small_jitter
        """
        policy = RetryPolicy(initial_delay=1.0, backoff_multiplier=2.0)
        delay = policy.calculate_delay(attempt=0)

        # Base delay = 1.0 * 2^0 = 1.0, plus up to 10% jitter
        assert 1.0 <= delay <= 1.2, (
            f"Attempt 0 delay should be ~1.0s (got {delay:.3f}s)"
        )

    def test_calculate_delay_exponential_growth(self) -> None:
        """Delay should roughly double with each attempt (exponential backoff).

        attempt 0: 1.0 * 2^0 = ~1.0s
        attempt 1: 1.0 * 2^1 = ~2.0s
        attempt 2: 1.0 * 2^2 = ~4.0s
        """
        policy = RetryPolicy(initial_delay=1.0, backoff_multiplier=2.0)

        delay_0 = policy.calculate_delay(0)
        delay_1 = policy.calculate_delay(1)
        delay_2 = policy.calculate_delay(2)

        # Each delay should be roughly double the previous (within jitter)
        assert delay_1 > delay_0, "Delay should increase with each attempt"
        assert delay_2 > delay_1, "Delay should increase with each attempt"
        # delay_2 should be roughly 4x delay_0 (2^2)
        assert delay_2 < 5.0, "Attempt 2 should be under 5s (4.0 + jitter)"

    def test_calculate_delay_capped_at_max(self) -> None:
        """Delay should never exceed max_delay, even for high attempt numbers.

        Without the cap, attempt 20 would be: 1 * 2^20 = 1,048,576 seconds.
        The max_delay cap prevents this.
        """
        policy = RetryPolicy(initial_delay=1.0, max_delay=10.0)
        delay = policy.calculate_delay(attempt=20)

        assert delay <= 10.0, (
            f"Delay should be capped at max_delay=10.0 (got {delay:.3f}s)"
        )

    def test_calculate_delay_custom_multiplier(self) -> None:
        """Custom backoff_multiplier should change the growth rate."""
        policy = RetryPolicy(initial_delay=1.0, backoff_multiplier=3.0)
        delay = policy.calculate_delay(attempt=2)

        # 1.0 * 3^2 = 9.0, plus up to 10% jitter → ~9.0-9.9
        assert delay >= 9.0
        assert delay <= 10.0

    def test_is_retryable_default_errors(self) -> None:
        """Default retryable errors should include common LLM/transient codes."""
        policy = RetryPolicy()
        assert policy.is_retryable("LLM_TIMEOUT") is True
        assert policy.is_retryable("LLM_RATE_LIMIT") is True
        assert policy.is_retryable("TRANSIENT_ERROR") is True

    def test_is_retryable_non_retryable_errors(self) -> None:
        """Errors NOT in the retryable list should return False."""
        policy = RetryPolicy()
        assert policy.is_retryable("INVALID_INPUT") is False
        assert policy.is_retryable("POLICY_VIOLATION") is False
        assert policy.is_retryable("CONFIG_ERROR") is False
        assert policy.is_retryable("UNKNOWN_ERROR") is False

    def test_custom_retryable_errors(self) -> None:
        """Custom retryable_errors list should override defaults."""
        policy = RetryPolicy(retryable_errors=["MY_CUSTOM_ERROR"])
        assert policy.is_retryable("MY_CUSTOM_ERROR") is True
        assert policy.is_retryable("LLM_TIMEOUT") is False  # No longer in list

    def test_validation_max_retries_bounds(self) -> None:
        """max_retries should be validated within bounds."""
        # Valid values
        RetryPolicy(max_retries=0)
        RetryPolicy(max_retries=20)

        # Invalid: negative
        with pytest.raises(Exception):
            RetryPolicy(max_retries=-1)


# =============================================================================
# Test: CircuitBreaker
# =============================================================================
class TestCircuitBreaker:
    """Tests for the CircuitBreaker per-agent health tracking.

    The circuit breaker tracks consecutive failures and opens/closes
    based on thresholds. Key states: CLOSED (normal), OPEN (blocked),
    HALF_OPEN (testing recovery).
    """

    def test_initial_state_is_closed(self) -> None:
        """Circuit breaker should start in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_can_execute_when_closed(self) -> None:
        """CLOSED breaker should always allow execution."""
        cb = CircuitBreaker()
        assert await cb.can_execute() is True

    async def test_opens_after_failure_threshold(self) -> None:
        """Breaker should transition CLOSED → OPEN after failure_threshold failures.

        Scenario:
            1. Record 5 failures (default threshold)
            2. State should transition to OPEN
            3. can_execute() should return False
        """
        cb = CircuitBreaker(failure_threshold=3)

        # 3 consecutive failures should trip the breaker
        await cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED  # Not yet

        await cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED  # Not yet

        await cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN  # Tripped!

        # Should block execution
        assert await cb.can_execute() is False

    async def test_success_resets_failure_count(self) -> None:
        """A success in CLOSED state should reset the failure counter.

        This means failures must be CONSECUTIVE to trip the breaker.
        A single success in between resets the counter.
        """
        cb = CircuitBreaker(failure_threshold=3)

        # 2 failures, then a success, then 2 more failures
        await cb.record_failure()
        await cb.record_failure()
        await cb.record_success()  # Resets counter to 0

        await cb.record_failure()
        await cb.record_failure()

        # Should still be CLOSED (only 2 consecutive failures, not 3)
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_open_to_half_open_after_recovery_timeout(self) -> None:
        """OPEN breaker should transition to HALF_OPEN after recovery_timeout.

        Scenario:
            1. Trip the breaker (3 failures)
            2. Breaker is OPEN, blocks execution
            3. Simulate recovery_timeout by manipulating _last_failure_time
            4. can_execute() should return True and state should be HALF_OPEN
        """
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)

        # Trip the breaker
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Simulate recovery_timeout elapsed by backdating the failure time.
        # We set _last_failure_time to 2 seconds ago (> 1.0s recovery_timeout).
        cb._last_failure_time = time.monotonic() - 2.0

        # Now can_execute should transition to HALF_OPEN and return True
        assert await cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    async def test_half_open_to_closed_after_success_threshold(self) -> None:
        """HALF_OPEN breaker should close after enough successes.

        Scenario:
            1. Trip the breaker → OPEN
            2. Wait for recovery → HALF_OPEN
            3. Record success_threshold successes → CLOSED
        """
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.01,
            success_threshold=2,
        )

        # Trip the breaker
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.02)
        await cb.can_execute()  # Triggers OPEN → HALF_OPEN
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # First success in HALF_OPEN
        await cb.record_success()
        assert cb.state == CircuitBreakerState.HALF_OPEN  # Not yet

        # Second success reaches threshold → CLOSED
        await cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_half_open_failure_reopens(self) -> None:
        """A failure in HALF_OPEN state should immediately reopen the circuit.

        This is the aggressive recovery check: if the first test request
        fails, we go right back to OPEN (agent hasn't recovered yet).
        """
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.01,
            success_threshold=2,
        )

        # Trip the breaker → OPEN
        await cb.record_failure()
        await cb.record_failure()

        # Wait for recovery → HALF_OPEN
        await asyncio.sleep(0.02)
        await cb.can_execute()
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Failure in HALF_OPEN → immediately back to OPEN
        await cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    async def test_open_blocks_execution(self) -> None:
        """OPEN breaker should return False from can_execute().

        This prevents the coordinator from sending tasks to an unhealthy agent.
        """
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)

        # Trip the breaker
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Should block (recovery_timeout hasn't elapsed)
        assert await cb.can_execute() is False


# =============================================================================
# Test: ErrorHandler
# =============================================================================
class TestErrorHandler:
    """Tests for the ErrorHandler decision logic.

    Each test creates fresh bus + state manager instances for isolation.
    """

    async def _create_handler(
        self, retry_policy: RetryPolicy | None = None
    ) -> tuple[ErrorHandler, InMemoryMessageBus, InMemoryStateManager]:
        """Create a connected ErrorHandler with fresh dependencies."""
        bus = InMemoryMessageBus()
        sm = InMemoryStateManager()
        await bus.connect()
        await sm.connect()
        handler = ErrorHandler(bus, sm, default_retry_policy=retry_policy)
        return handler, bus, sm

    # -------------------------------------------------------------------------
    # Test: RETRY action (transient, retryable errors)
    # -------------------------------------------------------------------------

    async def test_retryable_error_returns_retry(self) -> None:
        """A retryable error on first attempt should return RETRY.

        Scenario:
            1. Create an AgentError with error_code="LLM_TIMEOUT"
            2. Call handle_error with attempt=0
            3. Should return ErrorAction.RETRY
        """
        handler, bus, sm = await self._create_handler()

        error = AgentError(
            message="LLM timed out",
            agent_id="coding-01",
            error_code="LLM_TIMEOUT",
        )
        context = {"agent_id": "coding-01", "task_id": "task-1", "attempt": 0}

        action = await handler.handle_error(error, context)

        assert action == ErrorAction.RETRY, (
            "Retryable error on first attempt should return RETRY"
        )

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: ESCALATE action (non-retryable errors)
    # -------------------------------------------------------------------------

    async def test_non_retryable_error_returns_escalate(self) -> None:
        """A non-retryable error should return ESCALATE.

        Errors like INVALID_INPUT or CONFIG_ERROR are permanent failures
        that won't resolve by retrying. These need human attention.
        """
        handler, bus, sm = await self._create_handler()

        # Track escalation messages published to the bus
        escalated: list[AgentMessage] = []

        async def on_error(msg: AgentMessage) -> None:
            escalated.append(msg)

        await bus.subscribe("conductor:errors", on_error)

        error = AgentError(
            message="Invalid task configuration",
            agent_id="coding-01",
            error_code="INVALID_INPUT",
        )
        context = {"agent_id": "coding-01", "task_id": "task-1", "attempt": 0}

        action = await handler.handle_error(error, context)

        assert action == ErrorAction.ESCALATE, (
            "Non-retryable error should return ESCALATE"
        )
        # Verify escalation message was published
        assert len(escalated) == 1, (
            "An ERROR message should be published to conductor:errors"
        )
        assert escalated[0].message_type == MessageType.ERROR
        assert escalated[0].sender_id == "error_handler"

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: DEAD_LETTER action (max retries exhausted)
    # -------------------------------------------------------------------------

    async def test_max_retries_exhausted_returns_dead_letter(self) -> None:
        """Exceeding max_retries should return DEAD_LETTER.

        Even if the error is retryable, once we've tried max_retries times,
        we stop and send it to the dead letter queue.
        """
        handler, bus, sm = await self._create_handler(
            retry_policy=RetryPolicy(max_retries=3)
        )

        error = AgentError(
            message="LLM timed out (again)",
            agent_id="coding-01",
            error_code="LLM_TIMEOUT",
        )
        # attempt=3 means we've already tried 3 times (0,1,2 were retries)
        context = {"agent_id": "coding-01", "task_id": "task-1", "attempt": 3}

        action = await handler.handle_error(error, context)

        assert action == ErrorAction.DEAD_LETTER, (
            "Should DEAD_LETTER when max retries exhausted"
        )
        # Verify it was added to the DLQ
        assert handler.dead_letter_count == 1
        dlq = handler.get_dead_letter_queue()
        assert dlq[0]["error_code"] == "LLM_TIMEOUT"
        assert dlq[0]["task_id"] == "task-1"

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: DEAD_LETTER when circuit breaker is open
    # -------------------------------------------------------------------------

    async def test_circuit_breaker_open_returns_dead_letter(self) -> None:
        """When the agent's circuit breaker is open, should return DEAD_LETTER.

        An open circuit breaker means the agent is unhealthy. Don't even
        attempt a retry — send directly to DLQ.
        """
        handler, bus, sm = await self._create_handler()

        # Manually trip the circuit breaker for this agent
        breaker = handler.get_circuit_breaker("coding-01")
        for _ in range(5):  # Default threshold is 5
            await breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

        # Now any error for this agent should go to DLQ
        error = AgentError(
            message="LLM timed out",
            agent_id="coding-01",
            error_code="LLM_TIMEOUT",
        )
        context = {"agent_id": "coding-01", "task_id": "task-1", "attempt": 0}

        action = await handler.handle_error(error, context)

        assert action == ErrorAction.DEAD_LETTER, (
            "Open circuit breaker should send error to DEAD_LETTER"
        )
        assert handler.dead_letter_count == 1

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: Circuit breaker failure tracking through handle_error
    # -------------------------------------------------------------------------

    async def test_handle_error_records_circuit_breaker_failure(self) -> None:
        """handle_error should record a failure in the agent's circuit breaker.

        Each call to handle_error with a retryable error should increment
        the circuit breaker's failure count, eventually tripping it.
        """
        handler, bus, sm = await self._create_handler(
            retry_policy=RetryPolicy(max_retries=10)  # High limit so we don't hit it
        )

        error = AgentError(
            message="Timeout",
            agent_id="coding-01",
            error_code="LLM_TIMEOUT",
        )

        # Call handle_error 5 times (default circuit breaker threshold)
        for i in range(5):
            await handler.handle_error(
                error, {"agent_id": "coding-01", "task_id": f"task-{i}", "attempt": i}
            )

        # The circuit breaker should now be OPEN
        breaker = handler.get_circuit_breaker("coding-01")
        assert breaker.state == CircuitBreakerState.OPEN

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: retry_task delay
    # -------------------------------------------------------------------------

    async def test_retry_task_waits_and_returns_true(self) -> None:
        """retry_task should sleep for the calculated delay and return True.

        We use a very short initial_delay to keep the test fast.
        """
        handler, bus, sm = await self._create_handler(
            retry_policy=RetryPolicy(initial_delay=0.01)
        )

        start = time.monotonic()
        result = await handler.retry_task("task-1", "coding-01", attempt=0)
        elapsed = time.monotonic() - start

        assert result is True, "retry_task should return True on success"
        assert elapsed >= 0.01, "retry_task should sleep for at least initial_delay"

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: Dead Letter Queue management
    # -------------------------------------------------------------------------

    async def test_dead_letter_queue_accumulates(self) -> None:
        """Multiple dead-lettered errors should accumulate in the DLQ."""
        handler, bus, sm = await self._create_handler(
            retry_policy=RetryPolicy(max_retries=0)  # No retries → immediate DLQ
        )

        for i in range(3):
            error = AgentError(
                message=f"Error {i}",
                agent_id="coding-01",
                error_code="LLM_TIMEOUT",
            )
            await handler.handle_error(
                error, {"agent_id": "coding-01", "task_id": f"task-{i}", "attempt": 0}
            )

        assert handler.dead_letter_count == 3, (
            "DLQ should have 3 entries after 3 dead-lettered errors"
        )

        dlq = handler.get_dead_letter_queue()
        assert len(dlq) == 3
        # Verify DLQ entries have the right fields
        for entry in dlq:
            assert "error_type" in entry
            assert "error_code" in entry
            assert "error_message" in entry
            assert "context" in entry
            assert "timestamp" in entry

        await bus.disconnect()
        await sm.disconnect()

    async def test_get_dead_letter_queue_returns_copy(self) -> None:
        """get_dead_letter_queue should return a copy, not the internal list."""
        handler, bus, sm = await self._create_handler()

        dlq = handler.get_dead_letter_queue()
        dlq.append({"fake": "entry"})  # Modify the copy

        # Internal DLQ should be unaffected
        assert handler.dead_letter_count == 0

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: Generic exceptions (not ConductorError)
    # -------------------------------------------------------------------------

    async def test_generic_exception_gets_unknown_error_code(self) -> None:
        """Non-ConductorError exceptions should get UNKNOWN_ERROR code.

        Since UNKNOWN_ERROR is not in the retryable list, it should ESCALATE.
        """
        handler, bus, sm = await self._create_handler()

        error = RuntimeError("Something unexpected")
        context = {"agent_id": "coding-01", "task_id": "task-1", "attempt": 0}

        action = await handler.handle_error(error, context)

        assert action == ErrorAction.ESCALATE, (
            "Unknown error codes should be escalated (not retryable)"
        )

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: Per-agent circuit breaker isolation
    # -------------------------------------------------------------------------

    async def test_per_agent_circuit_breaker_isolation(self) -> None:
        """Each agent should have its own independent circuit breaker.

        Tripping one agent's breaker should not affect other agents.
        """
        handler, bus, sm = await self._create_handler()

        # Trip coding-01's breaker
        breaker_a = handler.get_circuit_breaker("coding-01")
        for _ in range(5):
            await breaker_a.record_failure()
        assert breaker_a.state == CircuitBreakerState.OPEN

        # review-01's breaker should still be CLOSED
        breaker_b = handler.get_circuit_breaker("review-01")
        assert breaker_b.state == CircuitBreakerState.CLOSED

        await bus.disconnect()
        await sm.disconnect()

    # -------------------------------------------------------------------------
    # Test: Escalation message bus publish failure is non-fatal
    # -------------------------------------------------------------------------

    async def test_escalation_survives_bus_failure(self) -> None:
        """escalate_error should not raise even if the bus publish fails.

        The error handler should be robust: if the message bus is down,
        we log the failure but don't crash.
        """
        handler, bus, sm = await self._create_handler()

        # Disconnect the bus to simulate a failure
        await bus.disconnect()

        error = AgentError(
            message="Bad config",
            agent_id="coding-01",
            error_code="INVALID_INPUT",
        )
        context = {"agent_id": "coding-01", "task_id": "task-1"}

        # Should not raise even though bus is disconnected
        await handler.escalate_error(error, context)

    # -------------------------------------------------------------------------
    # Test: ErrorHandler with missing context keys
    # -------------------------------------------------------------------------

    async def test_handle_error_with_minimal_context(self) -> None:
        """handle_error should work even with an empty context dict.

        Missing keys should use defaults (agent_id="unknown", attempt=0).
        """
        handler, bus, sm = await self._create_handler()

        error = AgentError(
            message="Something failed",
            agent_id="coding-01",
            error_code="LLM_TIMEOUT",
        )

        # Empty context — should still work with defaults
        action = await handler.handle_error(error, {})

        assert action == ErrorAction.RETRY, (
            "Retryable error with default attempt=0 should RETRY"
        )

        await bus.disconnect()
        await sm.disconnect()
