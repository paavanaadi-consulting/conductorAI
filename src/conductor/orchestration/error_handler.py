"""
conductor.orchestration.error_handler - Resilient Error Handling Infrastructure
=================================================================================

This module implements the Error Handler -- the resilience backbone of ConductorAI.
When agents fail (LLM timeouts, rate limits, bugs), the Error Handler decides what
to do: retry with exponential backoff, escalate to a human/coordinator, or park
the failure in a dead letter queue for later inspection.

Architecture Context:
    The Error Handler sits in the orchestration layer between agents and the
    Workflow Engine. It intercepts errors before they propagate up and applies
    a multi-layered resilience strategy:

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                        ORCHESTRATION LAYER                              │
    │                                                                         │
    │  ┌──────────────┐    error    ┌────────────────┐    escalate           │
    │  │    Agent      │ ─────────> │  Error Handler  │ ──────────>  Message │
    │  │  (failed)     │            │                  │              Bus     │
    │  └──────────────┘            │  1. Check CB     │                      │
    │         ^                     │  2. Check Retry  │    state             │
    │         │ retry               │  3. Escalate?    │ ──────────>  State  │
    │         └─────────────────── │  4. Dead Letter? │              Manager │
    │                               └────────────────┘                      │
    │                                       │                                │
    │                                       v                                │
    │                              ┌─────────────────┐                      │
    │                              │  Dead Letter     │                      │
    │                              │  Queue (DLQ)     │                      │
    │                              └─────────────────┘                      │
    └─────────────────────────────────────────────────────────────────────────┘

Error Handling Flow:
    When an agent raises an exception, the Error Handler executes this
    decision tree:

    Exception raised by Agent
            │
            v
    ┌─ CircuitBreaker OPEN? ──────────────> YES ──> DEAD_LETTER
    │       │                                       (agent is unhealthy,
    │       NO                                       stop sending work)
    │       │
    │       v
    ├─ Is error retryable?
    │   (check error_code against RetryPolicy.retryable_errors)
    │       │                 │
    │      YES               NO
    │       │                 │
    │       v                 v
    │  Attempt < max?     ESCALATE
    │       │     │       (notify coordinator
    │      YES    NO       for human attention)
    │       │     │
    │       v     v
    │    RETRY   DEAD_LETTER
    │   (sleep   (max retries
    │  with       exhausted,
    │  backoff)   park error)
    │
    └──────────────────────────────────────────────────────────────────

Three Resilience Patterns:
    1. **RetryPolicy** (Exponential Backoff with Jitter):
       Transient errors (LLM timeouts, rate limits) often resolve if you
       wait and try again. The retry policy calculates increasing delays
       with random jitter to avoid thundering herd problems.

    2. **CircuitBreaker** (Per-Agent Health Tracking):
       If an agent keeps failing, stop sending it work. The circuit breaker
       tracks consecutive failures per agent and "opens" the circuit when
       the failure threshold is reached. After a recovery timeout, it
       transitions to HALF_OPEN and allows a few test requests through.
       If they succeed, the circuit closes again.

       Circuit Breaker State Machine:
           CLOSED ──(failure_threshold reached)──> OPEN
           OPEN ──(recovery_timeout elapsed)──> HALF_OPEN
           HALF_OPEN ──(success_threshold reached)──> CLOSED
           HALF_OPEN ──(any failure)──> OPEN

    3. **Dead Letter Queue** (DLQ):
       Errors that cannot be retried or have exhausted all retries are
       stored in the DLQ. This prevents data loss and allows operators
       to inspect, debug, and manually reprocess failed tasks later.

Design Decisions:
    - RetryPolicy is a Pydantic BaseModel so it can be serialized, loaded
      from config files, and validated automatically.
    - CircuitBreaker uses time.monotonic() instead of datetime to avoid
      issues with clock adjustments (NTP jumps, DST transitions).
    - The DLQ is an in-memory list for now. In production, this would be
      backed by a Redis list or a dedicated message queue (RabbitMQ DLQ).
    - ErrorHandler uses composition (has-a MessageBus, has-a StateManager)
      rather than inheritance, following the same pattern as other
      orchestration components.

Usage:
    >>> from conductor.orchestration.error_handler import ErrorHandler, RetryPolicy
    >>> handler = ErrorHandler(
    ...     message_bus=bus,
    ...     state_manager=state_mgr,
    ...     default_retry_policy=RetryPolicy(max_retries=5),
    ... )
    >>> action = await handler.handle_error(error, context={"agent_id": "coding-01"})
    >>> # action is ErrorAction.RETRY, ErrorAction.ESCALATE, or ErrorAction.DEAD_LETTER
"""

from __future__ import annotations

import asyncio
import random
import time
import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

from conductor.core.enums import MessageType, Priority
from conductor.core.exceptions import AgentError, ConductorError
from conductor.core.messages import AgentMessage, ErrorPayload
from conductor.orchestration.message_bus import MessageBus
from conductor.orchestration.state_manager import StateManager


# =============================================================================
# Logger Setup
# =============================================================================
# structlog provides structured, key-value logging that integrates with
# JSON log aggregators (ELK, Datadog, etc.). The module-level logger is
# shared by all classes in this file; each class binds additional context
# (e.g., component="error_handler") to their own logger instances.
# =============================================================================
logger = structlog.get_logger()


# =============================================================================
# ErrorAction Enumeration
# =============================================================================
# Represents the decision output of the ErrorHandler. After analyzing an error,
# the handler returns one of these actions telling the caller what to do next.
#
# This enum decouples the ERROR ANALYSIS logic (in ErrorHandler) from the
# ACTION EXECUTION logic (in WorkflowEngine/Coordinator). The handler decides;
# the caller executes. This separation makes both components independently
# testable.
#
# Decision mapping:
#   RETRY       → Transient error, retry with backoff (agent may recover)
#   ESCALATE    → Non-retryable error, needs human/coordinator attention
#   DEAD_LETTER → Max retries exhausted or circuit open, park for later
#   SKIP        → Error is non-critical, skip and continue workflow
# =============================================================================
class ErrorAction(str, Enum):
    """Actions the ErrorHandler can recommend after analyzing an error.

    The WorkflowEngine or Coordinator reads this action and executes the
    appropriate response. This keeps the ErrorHandler focused on ANALYSIS
    (what should we do?) and lets the caller handle EXECUTION (do it).

    Usage:
        >>> action = await error_handler.handle_error(error, context)
        >>> if action == ErrorAction.RETRY:
        ...     await retry_the_task()
        >>> elif action == ErrorAction.ESCALATE:
        ...     await notify_human()
    """

    RETRY = "retry"               # Retry the failed operation with backoff
    ESCALATE = "escalate"         # Escalate to coordinator/human for attention
    DEAD_LETTER = "dead_letter"   # Park in dead letter queue (unrecoverable)
    SKIP = "skip"                 # Skip and continue (non-critical failure)


# =============================================================================
# CircuitBreakerState Enumeration
# =============================================================================
# The three states of a circuit breaker, modeled after an electrical circuit:
#
#   CLOSED    = Circuit is complete, current flows = requests go through
#   OPEN      = Circuit is broken, no current    = requests are blocked
#   HALF_OPEN = Testing if circuit can be closed  = limited test requests
#
# This naming convention comes from Michael Nygard's "Release It!" and is
# the industry standard for the circuit breaker pattern.
# =============================================================================
class CircuitBreakerState(str, Enum):
    """States of the circuit breaker pattern.

    State Machine:
        CLOSED ──(failures >= threshold)──> OPEN
        OPEN ──(recovery_timeout elapsed)──> HALF_OPEN
        HALF_OPEN ──(successes >= threshold)──> CLOSED
        HALF_OPEN ──(any failure)──> OPEN

    Analogy:
        Think of an electrical circuit breaker in your home. When everything
        is fine (CLOSED), electricity flows normally. When there's a problem
        (too many failures), the breaker trips (OPEN) and cuts the circuit.
        After some time, you can test (HALF_OPEN) by flipping the breaker
        partially. If the test succeeds, the circuit closes again.
    """

    CLOSED = "closed"         # Normal operation: requests flow through
    OPEN = "open"             # Tripped: all requests are blocked
    HALF_OPEN = "half_open"   # Recovery testing: limited requests allowed


# =============================================================================
# RetryPolicy (Pydantic BaseModel)
# =============================================================================
# Configures HOW retries are performed: how many times, how long to wait,
# and which errors are worth retrying.
#
# The retry delay uses exponential backoff with jitter:
#
#   delay = min(initial_delay * (backoff_multiplier ^ attempt) + jitter, max_delay)
#
# This is the industry-standard approach (used by AWS SDK, Google Cloud,
# Stripe, etc.) because:
#   1. Exponential growth gives the failing service time to recover
#   2. Jitter prevents "thundering herd" (all retries hitting at the same time)
#   3. max_delay caps the wait to avoid absurdly long waits on high attempt counts
#
# Example delay progression (default settings):
#   Attempt 0: ~1.0s   (1.0 * 2^0 = 1.0, plus jitter)
#   Attempt 1: ~2.0s   (1.0 * 2^1 = 2.0, plus jitter)
#   Attempt 2: ~4.0s   (1.0 * 2^2 = 4.0, plus jitter)
#   Attempt 3: ~8.0s   (1.0 * 2^3 = 8.0, plus jitter)
#   Attempt 4: ~16.0s  (1.0 * 2^4 = 16.0, plus jitter)
#   ...
#   Attempt N: capped at 60.0s (max_delay)
# =============================================================================
class RetryPolicy(BaseModel):
    """Configuration for retry behavior with exponential backoff and jitter.

    This policy determines:
        1. HOW MANY times to retry (max_retries)
        2. HOW LONG to wait between retries (exponential backoff with jitter)
        3. WHICH errors to retry (retryable_errors whitelist)

    The policy is a Pydantic BaseModel so it can be:
        - Serialized to JSON/YAML for config files
        - Validated automatically (e.g., max_retries >= 0)
        - Passed as a constructor argument with type safety

    Attributes:
        max_retries: Maximum number of retry attempts before giving up.
            After max_retries failures, the error is sent to the dead letter
            queue. Set to 0 to disable retries entirely.
        initial_delay: Base delay in seconds for the first retry attempt.
            Subsequent attempts multiply this by backoff_multiplier.
        max_delay: Maximum delay in seconds. Caps the exponential growth
            so retries don't wait absurdly long on high attempt numbers.
        backoff_multiplier: Factor by which the delay increases each attempt.
            2.0 means each retry waits twice as long as the previous one.
        retryable_errors: List of error codes that are worth retrying.
            Only errors whose error_code is in this list will be retried.
            Non-retryable errors are immediately escalated.

    Example:
        >>> policy = RetryPolicy(max_retries=5, initial_delay=0.5)
        >>> policy.calculate_delay(attempt=2)  # ~2.0s (0.5 * 2^2 + jitter)
        >>> policy.is_retryable("LLM_TIMEOUT")  # True (in default list)
        >>> policy.is_retryable("INVALID_INPUT")  # False (not retryable)
    """

    max_retries: int = Field(
        default=3,
        ge=0,
        le=20,
        description=(
            "Maximum retry attempts before sending to dead letter queue. "
            "Matches ConductorConfig.max_agent_retries default."
        ),
    )
    initial_delay: float = Field(
        default=1.0,
        gt=0,
        le=30.0,
        description="Base delay in seconds for the first retry attempt",
    )
    max_delay: float = Field(
        default=60.0,
        gt=0,
        le=300.0,
        description="Maximum delay cap in seconds (prevents absurdly long waits)",
    )
    backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=10.0,
        description=(
            "Multiplier for exponential backoff. 2.0 means each retry "
            "waits twice as long as the previous one."
        ),
    )
    retryable_errors: list[str] = Field(
        default=["LLM_TIMEOUT", "LLM_RATE_LIMIT", "TRANSIENT_ERROR"],
        description=(
            "Error codes that are worth retrying. Non-listed codes are "
            "immediately escalated (they represent permanent failures)."
        ),
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate the retry delay for a given attempt number.

        Uses exponential backoff with jitter, capped at max_delay.
        The formula:

            base_delay = initial_delay * (backoff_multiplier ^ attempt)
            jitter     = random(0, base_delay * 0.1)
            delay      = min(base_delay + jitter, max_delay)

        Why jitter?
            Without jitter, if 100 agents all hit an LLM rate limit at
            the same time and all retry with the same delay, they'll ALL
            retry at the exact same moment — causing another rate limit.
            Jitter adds a small random offset so retries are spread out
            over time. This is called "decorrelated jitter" and it's the
            approach recommended by AWS and Google Cloud.

        Args:
            attempt: Zero-based attempt number (0 = first retry, 1 = second, etc.).

        Returns:
            Delay in seconds (float). Always between initial_delay and max_delay.

        Example:
            >>> policy = RetryPolicy(initial_delay=1.0, backoff_multiplier=2.0)
            >>> policy.calculate_delay(0)  # ~1.0s (1.0 * 2^0 + jitter)
            >>> policy.calculate_delay(2)  # ~4.0s (1.0 * 2^2 + jitter)
        """
        # --- Step 1: Calculate the base delay with exponential growth ---
        # The exponent is the attempt number, so delay doubles each time
        # (with default multiplier of 2.0):
        #   attempt 0: 1.0 * 1 = 1.0
        #   attempt 1: 1.0 * 2 = 2.0
        #   attempt 2: 1.0 * 4 = 4.0
        base_delay = self.initial_delay * (self.backoff_multiplier ** attempt)

        # --- Step 2: Add jitter (randomness) to prevent thundering herd ---
        # We add up to 10% of the base delay as random noise. This is
        # "proportional jitter" — the jitter scales with the delay so it's
        # noticeable but not dominant.
        #
        # random.uniform is NOT cryptographically secure, but we don't need
        # crypto-quality randomness for retry jitter — we just need enough
        # spread to de-synchronize concurrent retries.
        jitter = random.uniform(0, base_delay * 0.1)

        # --- Step 3: Cap at max_delay to prevent absurdly long waits ---
        # Without this cap, attempt 20 with multiplier 2.0 would be:
        #   1.0 * 2^20 = 1,048,576 seconds (12 days!)
        # The cap ensures we never wait longer than max_delay.
        return min(base_delay + jitter, self.max_delay)

    def is_retryable(self, error_code: str) -> bool:
        """Check if an error code is in the retryable errors list.

        Only errors whose code appears in ``retryable_errors`` are worth
        retrying. All other errors represent permanent failures that won't
        resolve by trying again (e.g., INVALID_INPUT, POLICY_VIOLATION).

        Args:
            error_code: The machine-readable error code from the exception.
                Convention: UPPER_SNAKE_CASE (e.g., "LLM_TIMEOUT").

        Returns:
            True if the error code is retryable, False otherwise.

        Example:
            >>> policy = RetryPolicy()
            >>> policy.is_retryable("LLM_TIMEOUT")      # True
            >>> policy.is_retryable("LLM_RATE_LIMIT")    # True
            >>> policy.is_retryable("INVALID_INPUT")     # False
        """
        return error_code in self.retryable_errors


# =============================================================================
# CircuitBreaker
# =============================================================================
# Implements the Circuit Breaker pattern for per-agent health tracking.
#
# The problem this solves:
#   Without a circuit breaker, if an agent's LLM API key expires, every single
#   task sent to that agent will fail, wait for retry delays, fail again, and
#   eventually go to the dead letter queue. This wastes time and resources.
#
# With a circuit breaker:
#   After N consecutive failures (failure_threshold), the breaker "opens" and
#   immediately rejects new requests to that agent without even trying. After
#   a recovery timeout, it allows a few test requests (HALF_OPEN). If they
#   succeed, normal operation resumes (CLOSED).
#
# Why per-agent?
#   Different agents may use different LLM providers, different API keys, or
#   have different failure modes. A coding agent hitting OpenAI rate limits
#   shouldn't prevent the review agent (which might use Anthropic) from working.
#
# Thread Safety:
#   Uses asyncio.Lock for coroutine-safe state mutations. All state reads
#   in can_execute() are atomic (reading a single attribute), so they don't
#   need the lock. Only state WRITES (record_success, record_failure) acquire
#   the lock.
#
# Time Source:
#   Uses time.monotonic() instead of datetime.now() because monotonic clocks
#   are immune to NTP adjustments, DST transitions, and system clock changes.
#   When measuring "has 60 seconds passed?", monotonic time is the correct
#   choice. We ONLY use datetime for human-readable timestamps in logs.
# =============================================================================
class CircuitBreaker:
    """Per-agent circuit breaker for health-based request gating.

    The circuit breaker prevents sending tasks to agents that are consistently
    failing. This avoids wasting time on doomed retries and gives the failing
    agent time to recover (e.g., rate limit window expires, API key is rotated).

    State Machine:
        ┌────────┐   failure_threshold    ┌────────┐
        │ CLOSED │ ─────────────────────> │  OPEN  │
        │        │                         │        │
        │ (normal│                         │(reject │
        │  flow) │                         │  all)  │
        └────────┘                         └────┬───┘
             ^                                  │
             │   success_threshold              │ recovery_timeout
             │                                  │
        ┌────┴────┐                             │
        │HALF_OPEN│ <───────────────────────────┘
        │         │
        │ (test   │ ──(any failure)──> OPEN
        │  mode)  │
        └─────────┘

    Attributes:
        failure_threshold: Number of consecutive failures before the circuit
            opens. Higher values are more tolerant of intermittent errors.
        recovery_timeout: Seconds to wait in OPEN state before transitioning
            to HALF_OPEN. This gives the failing service time to recover.
        success_threshold: Number of consecutive successes needed in HALF_OPEN
            state before the circuit closes again. Ensures the recovery is
            genuine, not a one-off success.

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        >>> if await breaker.can_execute():
        ...     try:
        ...         result = await agent.execute(task)
        ...         await breaker.record_success()
        ...     except Exception:
        ...         await breaker.record_failure()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ) -> None:
        """Initialize the circuit breaker in CLOSED state.

        The breaker starts CLOSED (allowing all requests). It only opens
        after ``failure_threshold`` consecutive failures are recorded.

        Args:
            failure_threshold: Number of consecutive failures before opening
                the circuit. Default is 5 (tolerant of occasional errors).
            recovery_timeout: Seconds before OPEN transitions to HALF_OPEN.
                Default is 60 seconds (gives services time to recover).
            success_threshold: Consecutive successes needed in HALF_OPEN to
                close the circuit. Default is 2 (confirms real recovery).
        """
        # -----------------------------------------------------------------
        # Configuration (immutable after creation)
        # -----------------------------------------------------------------
        self.failure_threshold: int = failure_threshold
        self.recovery_timeout: float = recovery_timeout
        self.success_threshold: int = success_threshold

        # -----------------------------------------------------------------
        # Internal State (mutable, protected by _lock)
        # -----------------------------------------------------------------
        # _state: Current circuit breaker state. Starts CLOSED (healthy).
        self._state: CircuitBreakerState = CircuitBreakerState.CLOSED

        # _failure_count: Running count of consecutive failures. Reset to 0
        # on any success. Compared against failure_threshold to decide
        # whether to open the circuit.
        self._failure_count: int = 0

        # _success_count: Consecutive successes in HALF_OPEN state. When
        # this reaches success_threshold, the circuit closes again.
        # Only meaningful in HALF_OPEN state; reset on state transitions.
        self._success_count: int = 0

        # _last_failure_time: Monotonic timestamp of the last failure.
        # Used to calculate whether recovery_timeout has elapsed for the
        # OPEN → HALF_OPEN transition.
        # Uses time.monotonic() because we need elapsed-time measurement,
        # not wall-clock time. Monotonic clocks are immune to NTP jumps.
        self._last_failure_time: Optional[float] = None

        # -----------------------------------------------------------------
        # Concurrency Lock
        # -----------------------------------------------------------------
        # asyncio.Lock ensures that concurrent coroutines don't create race
        # conditions when updating _failure_count, _success_count, or _state.
        # Example race condition without lock:
        #   Coroutine A reads _failure_count = 4
        #   Coroutine B reads _failure_count = 4
        #   Both increment to 5 and try to open the circuit
        # With the lock, only one can modify at a time.
        self._lock: asyncio.Lock = asyncio.Lock()

        # -----------------------------------------------------------------
        # Logger with circuit breaker context
        # -----------------------------------------------------------------
        self._logger = logger.bind(component="circuit_breaker")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def state(self) -> CircuitBreakerState:
        """Get the current circuit breaker state.

        This is a read-only property. The state is managed internally by
        ``record_success()`` and ``record_failure()``. External code should
        only read the state, never set it directly.

        Returns:
            The current CircuitBreakerState (CLOSED, OPEN, or HALF_OPEN).
        """
        return self._state

    # =========================================================================
    # Public Methods
    # =========================================================================

    async def can_execute(self) -> bool:
        """Check if the circuit breaker allows a request to proceed.

        This method also handles the automatic OPEN -> HALF_OPEN transition:
        if the circuit is OPEN and the recovery_timeout has elapsed, it
        transitions to HALF_OPEN to allow test requests.

        Decision Logic:
            - CLOSED:    Always returns True (normal operation)
            - OPEN:      Returns False UNLESS recovery_timeout has elapsed,
                         in which case it transitions to HALF_OPEN and
                         returns True
            - HALF_OPEN: Always returns True (allow test requests)

        Returns:
            True if the request should proceed, False if it should be rejected.

        Example:
            >>> if await breaker.can_execute():
            ...     # Safe to send a task to this agent
            ...     result = await agent.execute(task)
            ... else:
            ...     # Agent is unhealthy, skip or use a different agent
            ...     handle_circuit_open()
        """
        async with self._lock:
            # --- CLOSED: Normal operation, all requests proceed ---
            if self._state == CircuitBreakerState.CLOSED:
                return True

            # --- OPEN: Check if recovery_timeout has elapsed ---
            # If the circuit has been open long enough, transition to
            # HALF_OPEN to allow test requests. This is the automatic
            # recovery mechanism: we don't require manual intervention
            # to start testing again.
            if self._state == CircuitBreakerState.OPEN:
                if self._last_failure_time is not None:
                    elapsed = time.monotonic() - self._last_failure_time
                    if elapsed >= self.recovery_timeout:
                        # Transition OPEN → HALF_OPEN
                        self._state = CircuitBreakerState.HALF_OPEN
                        self._success_count = 0  # Reset for fresh counting
                        self._logger.info(
                            "circuit_breaker_half_open",
                            elapsed_seconds=round(elapsed, 2),
                            recovery_timeout=self.recovery_timeout,
                        )
                        return True

                # Still within recovery timeout: reject the request
                return False

            # --- HALF_OPEN: Allow test requests through ---
            # In HALF_OPEN state, we allow requests so we can test
            # whether the agent has recovered. The results of these
            # test requests determine whether we close the circuit
            # (recovered) or re-open it (still failing).
            if self._state == CircuitBreakerState.HALF_OPEN:
                return True

            # Defensive fallback (should never reach here with a valid enum)
            return False  # pragma: no cover

    async def record_success(self) -> None:
        """Record a successful operation.

        Effects depend on the current state:
            - CLOSED:    Reset failure count to 0 (clear any partial failures)
            - HALF_OPEN: Increment success count. If success_threshold is
                         reached, close the circuit (full recovery confirmed)
            - OPEN:      No effect (shouldn't happen — can_execute() returns
                         False in OPEN state, so no operations should occur)

        This method is called by the orchestration layer after an agent
        successfully completes a task. It signals to the circuit breaker
        that the agent is healthy (or recovering).
        """
        async with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                # --- HALF_OPEN: Count successes toward full recovery ---
                self._success_count += 1
                self._logger.info(
                    "circuit_breaker_half_open_success",
                    success_count=self._success_count,
                    success_threshold=self.success_threshold,
                )

                if self._success_count >= self.success_threshold:
                    # Enough consecutive successes: the agent has recovered.
                    # Close the circuit and resume normal operation.
                    self._state = CircuitBreakerState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._logger.info(
                        "circuit_breaker_closed",
                        reason="recovery_confirmed",
                    )
            else:
                # --- CLOSED (or OPEN, unlikely): Reset failure count ---
                # Any success in CLOSED state clears the failure counter,
                # because failures are only meaningful when consecutive.
                # One success "resets the clock" on failure tracking.
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed operation.

        Effects depend on the current state:
            - CLOSED:    Increment failure count. If failure_threshold is
                         reached, open the circuit (agent is unhealthy)
            - HALF_OPEN: Immediately re-open the circuit (the agent hasn't
                         recovered after all)
            - OPEN:      Update last_failure_time (extend recovery window)

        This method is called by the orchestration layer when an agent
        fails to complete a task. Consecutive failures accumulate toward
        the failure_threshold.
        """
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitBreakerState.HALF_OPEN:
                # --- HALF_OPEN: Any failure immediately re-opens ---
                # The agent failed during recovery testing. It's not ready
                # yet. Re-open the circuit and restart the recovery timer.
                # This is deliberately aggressive: in HALF_OPEN, we have
                # very low tolerance because we're actively testing recovery.
                self._state = CircuitBreakerState.OPEN
                self._success_count = 0
                self._logger.warning(
                    "circuit_breaker_reopened",
                    reason="failure_during_half_open",
                    failure_count=self._failure_count,
                )

            elif self._state == CircuitBreakerState.CLOSED:
                # --- CLOSED: Check if threshold reached ---
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitBreakerState.OPEN
                    self._logger.warning(
                        "circuit_breaker_opened",
                        failure_count=self._failure_count,
                        failure_threshold=self.failure_threshold,
                        recovery_timeout=self.recovery_timeout,
                    )

            # --- OPEN: Just update the timestamp (already open) ---
            # The failure_count and last_failure_time are already updated
            # above (before the state checks). No additional action needed.


# =============================================================================
# ErrorHandler
# =============================================================================
# The main error handling orchestrator. Combines RetryPolicy, CircuitBreaker,
# and Dead Letter Queue into a unified error response system.
#
# Architecture Role:
#   The ErrorHandler is the SINGLE POINT of error handling for the entire
#   orchestration layer. Instead of every component implementing its own
#   retry logic, they all delegate to ErrorHandler.handle_error() and
#   follow the returned ErrorAction.
#
# Component Dependencies:
#   - MessageBus:     Used to publish escalation messages (ERROR type)
#                     to the coordinator channel for human attention.
#   - StateManager:   Used to update agent state when errors occur
#                     (e.g., increment error_count, mark as FAILED).
#   - RetryPolicy:    Configures retry behavior (delays, max retries,
#                     which errors are retryable).
#   - CircuitBreaker: Per-agent health tracking (created on demand).
#
# Concurrency:
#   The ErrorHandler itself is stateless except for the DLQ and circuit
#   breakers dict. The DLQ is append-only (safe for concurrent access).
#   The circuit breakers dict uses .setdefault() for thread-safe creation.
#   Individual CircuitBreaker instances have their own asyncio.Lock.
# =============================================================================
class ErrorHandler:
    """Central error handling and resilience orchestrator for ConductorAI.

    The ErrorHandler sits between agents and the workflow engine, intercepting
    errors and applying a multi-layered resilience strategy:

    1. **Circuit Breaker Check**: Is the agent healthy enough to retry?
    2. **Retry Policy Check**: Is this error type retryable? Have we
       exhausted our retry budget?
    3. **Escalation**: Non-retryable errors are published to the message
       bus for coordinator/human attention.
    4. **Dead Letter Queue**: Unrecoverable errors are parked in the DLQ
       for later inspection and manual reprocessing.

    The handler does NOT execute retries itself — it returns an ErrorAction
    that tells the caller what to do. This keeps the handler focused on
    DECISION-MAKING and allows the caller (WorkflowEngine, Coordinator)
    to handle the actual execution in their own context.

    Attributes:
        _message_bus: Message bus for publishing escalation messages.
        _state_manager: State manager for reading/updating agent state.
        _default_retry_policy: Default retry policy applied to all errors
            unless overridden by context-specific policies.
        _dead_letter_queue: In-memory list of unrecoverable error records.
            Each entry is a dict with error details, context, and timestamp.
        _circuit_breakers: Map of agent_id -> CircuitBreaker. Created lazily
            on first error for each agent.
        _logger: Structured logger with component context.

    Example:
        >>> handler = ErrorHandler(
        ...     message_bus=bus,
        ...     state_manager=state_mgr,
        ...     default_retry_policy=RetryPolicy(max_retries=5),
        ... )
        >>>
        >>> # In the workflow engine's error handling path:
        >>> try:
        ...     await agent.execute(task)
        ... except AgentError as e:
        ...     context = {"agent_id": agent.id, "task_id": task.id, "attempt": 1}
        ...     action = await handler.handle_error(e, context)
        ...     if action == ErrorAction.RETRY:
        ...         await handler.retry_task(task.id, agent.id, attempt=1)
    """

    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager,
        default_retry_policy: RetryPolicy | None = None,
    ) -> None:
        """Initialize the ErrorHandler with its infrastructure dependencies.

        Args:
            message_bus: The message bus instance for publishing error
                escalation messages. Must be connected before use.
            state_manager: The state manager for reading/updating agent
                and workflow state. Must be connected before use.
            default_retry_policy: Default retry policy for all errors.
                If None, a RetryPolicy with default values (3 retries,
                1.0s initial delay, 2.0x backoff) is used.
        """
        # -----------------------------------------------------------------
        # Infrastructure Dependencies
        # -----------------------------------------------------------------
        # These are injected via constructor (Dependency Injection pattern).
        # The ErrorHandler doesn't create or own these — it borrows them
        # from the orchestration layer that creates everything.
        # -----------------------------------------------------------------
        self._message_bus: MessageBus = message_bus
        self._state_manager: StateManager = state_manager

        # -----------------------------------------------------------------
        # Default Retry Policy
        # -----------------------------------------------------------------
        # Applied to all errors unless a context-specific policy is provided.
        # If no policy is given, we create one with sensible defaults that
        # match the ConductorConfig.max_agent_retries default (3 retries).
        # -----------------------------------------------------------------
        self._default_retry_policy: RetryPolicy = (
            default_retry_policy or RetryPolicy()
        )

        # -----------------------------------------------------------------
        # Dead Letter Queue (DLQ)
        # -----------------------------------------------------------------
        # Stores errors that cannot be retried or have exhausted all retries.
        # Each entry is a dict containing:
        #   - error_type:  Exception class name
        #   - error_code:  Machine-readable error code
        #   - message:     Human-readable error message
        #   - context:     The context dict from handle_error()
        #   - timestamp:   When the error was added to the DLQ
        #   - traceback:   Python traceback string for debugging
        #
        # In-memory for now. Production would use Redis LPUSH/LRANGE or
        # a dedicated message queue (RabbitMQ DLQ, AWS SQS DLQ, etc.)
        # for persistence across process restarts.
        # -----------------------------------------------------------------
        self._dead_letter_queue: list[dict[str, Any]] = []

        # -----------------------------------------------------------------
        # Per-Agent Circuit Breakers
        # -----------------------------------------------------------------
        # Each agent gets its own circuit breaker, created lazily on first
        # error. This allows different agents to have independent health
        # tracking. For example, if the coding agent's LLM API is down,
        # only the coding agent's circuit opens — the review agent can
        # still work fine if it uses a different provider.
        #
        # Key:   agent_id (str)
        # Value: CircuitBreaker instance for that agent
        # -----------------------------------------------------------------
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

        # -----------------------------------------------------------------
        # Logger with ErrorHandler context
        # -----------------------------------------------------------------
        self._logger = logger.bind(component="error_handler")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def dead_letter_count(self) -> int:
        """Get the number of errors in the dead letter queue.

        This is a quick health check metric. A growing DLQ indicates
        systemic problems that need human attention.

        Returns:
            Number of error records in the DLQ.
        """
        return len(self._dead_letter_queue)

    # =========================================================================
    # Public Methods
    # =========================================================================

    async def handle_error(
        self, error: Exception, context: dict[str, Any]
    ) -> ErrorAction:
        """Main error handling entry point. Analyzes an error and decides the action.

        This is the primary method called by the orchestration layer when
        any error occurs. It implements the full decision tree:

            1. Extract error metadata (code, message, agent_id, attempt)
            2. Check the agent's circuit breaker
            3. Check if the error is retryable
            4. Check if retry budget is exhausted
            5. Return the appropriate ErrorAction

        The method does NOT execute the action — it only DECIDES. The caller
        is responsible for executing the returned action (retry, escalate,
        dead letter, or skip).

        Args:
            error: The exception that was raised. Can be any Exception, but
                ConductorError subclasses provide richer metadata (error_code,
                details dict).
            context: Dictionary with contextual information about the failure.
                Expected keys (all optional):
                    - agent_id (str): ID of the agent that failed
                    - task_id (str): ID of the task that failed
                    - attempt (int): Current retry attempt number (0-based)
                    - workflow_id (str): ID of the parent workflow

        Returns:
            ErrorAction indicating what the caller should do:
                - RETRY:       Retry the task with backoff delay
                - ESCALATE:    Publish error for coordinator/human attention
                - DEAD_LETTER: Send to DLQ (unrecoverable)
                - SKIP:        Skip and continue (non-critical)

        Example:
            >>> action = await handler.handle_error(
            ...     error=AgentError("LLM timed out", agent_id="coding-01",
            ...                      error_code="LLM_TIMEOUT"),
            ...     context={"agent_id": "coding-01", "task_id": "task-1", "attempt": 0},
            ... )
            >>> action  # ErrorAction.RETRY
        """
        # --- Step 1: Extract error metadata ---
        # ConductorError subclasses have structured error_code and details.
        # For generic exceptions, we use fallback values.
        error_code = getattr(error, "error_code", "UNKNOWN_ERROR")
        agent_id = context.get("agent_id", "unknown")
        task_id = context.get("task_id", "unknown")
        attempt = context.get("attempt", 0)

        self._logger.warning(
            "handling_error",
            error_type=type(error).__name__,
            error_code=error_code,
            error_message=str(error),
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
        )

        # --- Step 2: Check the agent's circuit breaker ---
        # If the circuit is OPEN (agent is unhealthy), skip retries entirely
        # and send directly to the dead letter queue. There's no point
        # retrying if the agent is consistently failing.
        circuit_breaker = self.get_circuit_breaker(agent_id)

        if not await circuit_breaker.can_execute():
            self._logger.error(
                "circuit_breaker_open_dead_letter",
                agent_id=agent_id,
                task_id=task_id,
                error_code=error_code,
            )
            await self.send_to_dead_letter(error, context)
            return ErrorAction.DEAD_LETTER

        # --- Step 3: Record the failure in the circuit breaker ---
        # Even if we decide to retry, the failure counts toward the
        # circuit breaker's failure threshold. This ensures that repeated
        # retries that keep failing will eventually trip the breaker.
        await circuit_breaker.record_failure()

        # --- Step 4: Check if the error is retryable ---
        # Some errors are permanent and will never resolve by retrying:
        #   - INVALID_INPUT: Bad task data won't fix itself
        #   - POLICY_VIOLATION: The policy will keep blocking
        #   - CONFIG_ERROR: Configuration needs manual fix
        # These should be escalated immediately.
        if not self._default_retry_policy.is_retryable(error_code):
            self._logger.info(
                "error_not_retryable_escalating",
                error_code=error_code,
                retryable_errors=self._default_retry_policy.retryable_errors,
            )
            await self.escalate_error(error, context)
            return ErrorAction.ESCALATE

        # --- Step 5: Check if retry budget is exhausted ---
        # If we've already retried max_retries times, send to the dead
        # letter queue. There's no point retrying indefinitely — if it
        # hasn't worked after N attempts, something is fundamentally wrong.
        if attempt >= self._default_retry_policy.max_retries:
            self._logger.error(
                "max_retries_exhausted_dead_letter",
                attempt=attempt,
                max_retries=self._default_retry_policy.max_retries,
                agent_id=agent_id,
                task_id=task_id,
            )
            await self.send_to_dead_letter(error, context)
            return ErrorAction.DEAD_LETTER

        # --- Step 6: Error is retryable and budget remains → RETRY ---
        self._logger.info(
            "error_retryable",
            error_code=error_code,
            attempt=attempt,
            max_retries=self._default_retry_policy.max_retries,
            agent_id=agent_id,
            task_id=task_id,
        )
        return ErrorAction.RETRY

    async def retry_task(
        self, task_id: str, agent_id: str, attempt: int
    ) -> bool:
        """Execute a retry by sleeping for the calculated backoff delay.

        This method implements the actual retry delay. The caller should
        invoke this method when ``handle_error()`` returns ``ErrorAction.RETRY``.
        After the delay, the caller is responsible for re-executing the task.

        The delay is calculated by the RetryPolicy using exponential backoff
        with jitter. This method only handles the WAITING — the actual task
        re-execution is the caller's responsibility.

        Args:
            task_id: ID of the task to retry.
            agent_id: ID of the agent that will retry the task.
            attempt: Current attempt number (0-based). Used to calculate
                the backoff delay — higher attempts = longer waits.

        Returns:
            True if the retry delay completed successfully.
            False if the delay was interrupted or an error occurred.

        Example:
            >>> # After handle_error returns RETRY:
            >>> success = await handler.retry_task("task-1", "coding-01", attempt=2)
            >>> if success:
            ...     # Re-execute the task
            ...     await agent.execute(task)
        """
        # Calculate the backoff delay for this attempt number
        delay = self._default_retry_policy.calculate_delay(attempt)

        self._logger.info(
            "retry_task_waiting",
            task_id=task_id,
            agent_id=agent_id,
            attempt=attempt,
            delay_seconds=round(delay, 2),
            max_retries=self._default_retry_policy.max_retries,
        )

        try:
            # --- Sleep for the calculated delay ---
            # asyncio.sleep yields control to the event loop, allowing
            # other coroutines to run while we wait. This is non-blocking
            # — the rest of the system continues operating during the delay.
            await asyncio.sleep(delay)

            self._logger.info(
                "retry_task_ready",
                task_id=task_id,
                agent_id=agent_id,
                attempt=attempt,
            )
            return True

        except asyncio.CancelledError:
            # --- Task was cancelled during the retry delay ---
            # This happens when the workflow is cancelled or the system is
            # shutting down. We propagate the cancellation by returning False
            # so the caller knows not to proceed with the retry.
            self._logger.warning(
                "retry_task_cancelled",
                task_id=task_id,
                agent_id=agent_id,
                attempt=attempt,
            )
            return False

        except Exception as exc:
            # --- Unexpected error during sleep (very unlikely) ---
            # asyncio.sleep rarely fails, but defensive programming requires
            # handling this. Log and return False to prevent the retry.
            self._logger.error(
                "retry_task_error",
                task_id=task_id,
                agent_id=agent_id,
                attempt=attempt,
                error=str(exc),
            )
            return False

    async def escalate_error(
        self, error: Exception, context: dict[str, Any]
    ) -> None:
        """Escalate an error by publishing it to the message bus.

        Escalation is used for non-retryable errors that need human or
        coordinator attention. The error is packaged as an ``AgentMessage``
        with ``MessageType.ERROR`` and published to the broadcast channel
        so the coordinator can pick it up and decide what to do.

        The coordinator might:
            - Reassign the task to a different agent
            - Abort the workflow
            - Notify a human operator
            - Trigger a different error recovery strategy

        Args:
            error: The exception that triggered the escalation.
            context: Contextual information about the failure (agent_id,
                task_id, workflow_id, attempt number, etc.).
        """
        # --- Build the ErrorPayload ---
        # ErrorPayload is the typed payload structure defined in
        # conductor.core.messages. It carries the machine-readable error
        # code, human-readable message, and source agent/task IDs.
        error_code = getattr(error, "error_code", "UNKNOWN_ERROR")
        agent_id = context.get("agent_id")
        task_id = context.get("task_id")

        # Build a traceback string for debugging. This is the Python
        # stack trace that shows WHERE the error occurred.
        tb_str: Optional[str] = None
        if error.__traceback__ is not None:
            tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        error_payload = ErrorPayload(
            error_code=error_code,
            error_message=str(error),
            agent_id=agent_id,
            task_id=task_id,
            traceback=tb_str,
        )

        # --- Build the AgentMessage envelope ---
        # The message is sent from "error_handler" (a virtual sender ID)
        # with CRITICAL priority because escalated errors need immediate
        # attention. No specific recipient — broadcast to all listeners
        # on the error channel.
        message = AgentMessage(
            message_type=MessageType.ERROR,
            sender_id="error_handler",
            payload=error_payload.model_dump(),
            priority=Priority.CRITICAL,
            metadata={
                "escalation_context": context,
                "error_type": type(error).__name__,
            },
        )

        # --- Publish to the broadcast channel ---
        # We use the broadcast channel so that any component interested
        # in error notifications (coordinator, monitoring dashboard, alerting
        # system) can subscribe and react appropriately.
        try:
            await self._message_bus.publish("conductor:errors", message)
            self._logger.warning(
                "error_escalated",
                error_code=error_code,
                agent_id=agent_id,
                task_id=task_id,
                message_id=message.message_id,
            )
        except Exception as publish_error:
            # --- Message bus publish failed ---
            # This is a meta-error: the error handler itself failed.
            # We log it but don't raise — we don't want error handling
            # errors to crash the system. The error is still captured
            # in the logs for debugging.
            self._logger.error(
                "error_escalation_failed",
                error_code=error_code,
                agent_id=agent_id,
                task_id=task_id,
                publish_error=str(publish_error),
            )

    async def send_to_dead_letter(
        self, error: Exception, context: dict[str, Any]
    ) -> None:
        """Store an unrecoverable error in the dead letter queue.

        The DLQ is the final resting place for errors that:
            - Exhausted all retry attempts
            - Were blocked by an open circuit breaker
            - Are non-retryable AND cannot be escalated

        Each DLQ entry is a self-contained record with all information
        needed to understand and potentially reprocess the failure:
            - What happened (error type, code, message, traceback)
            - Where it happened (agent_id, task_id, workflow_id)
            - When it happened (UTC timestamp)
            - How many times it was tried (attempt count)

        Operators can inspect the DLQ to:
            - Identify systemic issues (many similar errors)
            - Manually reprocess failed tasks after fixing the root cause
            - Generate incident reports

        Args:
            error: The exception that caused the failure.
            context: Contextual information about the failure.
        """
        # --- Build the DLQ entry ---
        # We capture everything needed for post-mortem debugging. This
        # record should be self-contained: an operator reading it should
        # understand what happened without looking at any other data source.
        error_code = getattr(error, "error_code", "UNKNOWN_ERROR")

        # Build traceback string for debugging
        tb_str: Optional[str] = None
        if error.__traceback__ is not None:
            tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        dlq_entry: dict[str, Any] = {
            # --- Error Information ---
            "error_type": type(error).__name__,
            "error_code": error_code,
            "error_message": str(error),
            "traceback": tb_str,
            # --- Context Information ---
            "context": context,
            "agent_id": context.get("agent_id", "unknown"),
            "task_id": context.get("task_id", "unknown"),
            "workflow_id": context.get("workflow_id", "unknown"),
            "attempt": context.get("attempt", 0),
            # --- Timestamp ---
            # ISO 8601 format for universal parsability. We use wall-clock
            # time here (not monotonic) because this is for human-readable
            # records, not elapsed-time measurement.
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # --- If the error is a ConductorError, include its structured details ---
        # ConductorError.details may contain valuable debugging info like
        # HTTP status codes, request/response data, or configuration values.
        if isinstance(error, ConductorError):
            dlq_entry["error_details"] = error.details

        # --- Append to the DLQ ---
        self._dead_letter_queue.append(dlq_entry)

        self._logger.error(
            "error_sent_to_dead_letter",
            error_type=type(error).__name__,
            error_code=error_code,
            agent_id=context.get("agent_id", "unknown"),
            task_id=context.get("task_id", "unknown"),
            dlq_size=len(self._dead_letter_queue),
        )

        # --- Also publish to the DLQ channel on the message bus ---
        # This allows monitoring components to react in real-time to
        # DLQ additions (e.g., trigger alerts when DLQ size exceeds
        # a threshold).
        try:
            dlq_message = AgentMessage(
                message_type=MessageType.ERROR,
                sender_id="error_handler",
                payload={
                    "dlq_entry": dlq_entry,
                    "dlq_size": len(self._dead_letter_queue),
                },
                priority=Priority.HIGH,
                metadata={"channel_purpose": "dead_letter_notification"},
            )
            await self._message_bus.publish("conductor:dlq", dlq_message)
        except Exception as publish_error:
            # Don't let DLQ notification failure prevent the DLQ write.
            # The entry is already safely stored in the in-memory DLQ.
            # If the message bus is down, the entry is still captured.
            self._logger.error(
                "dlq_notification_failed",
                publish_error=str(publish_error),
            )

    def get_circuit_breaker(self, agent_id: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a specific agent.

        Circuit breakers are created lazily on first access and cached
        for the lifetime of the ErrorHandler. Each agent has its own
        independent circuit breaker so that failures in one agent don't
        affect the health tracking of other agents.

        Args:
            agent_id: The unique identifier of the agent.

        Returns:
            The CircuitBreaker instance for the specified agent.
            Creates a new one with default settings if none exists.

        Example:
            >>> breaker = handler.get_circuit_breaker("coding-agent-01")
            >>> breaker.state  # CircuitBreakerState.CLOSED (initially)
        """
        # --- Lazy creation with setdefault ---
        # dict.setdefault() is atomic in CPython (due to the GIL), so
        # concurrent coroutines won't accidentally create duplicate
        # circuit breakers for the same agent. The first caller creates
        # the breaker; subsequent callers get the cached instance.
        if agent_id not in self._circuit_breakers:
            self._circuit_breakers[agent_id] = CircuitBreaker()
            self._logger.debug(
                "circuit_breaker_created",
                agent_id=agent_id,
            )
        return self._circuit_breakers[agent_id]

    def get_dead_letter_queue(self) -> list[dict[str, Any]]:
        """Get a copy of the dead letter queue contents.

        Returns a shallow copy to prevent external code from accidentally
        modifying the internal DLQ state. Each entry is a dict containing
        error details, context, and timestamp.

        Returns:
            List of DLQ entries (dicts). Empty list if no errors are in the DLQ.

        Example:
            >>> dlq = handler.get_dead_letter_queue()
            >>> for entry in dlq:
            ...     print(f"[{entry['timestamp']}] {entry['error_code']}: "
            ...           f"{entry['error_message']}")
        """
        # Return a copy to maintain encapsulation. External code should
        # not be able to .append() or .pop() the internal list.
        return list(self._dead_letter_queue)
