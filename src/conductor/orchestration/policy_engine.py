"""
conductor.orchestration.policy_engine - Policy Evaluation & Enforcement
=========================================================================

This module implements the Policy Engine -- the rule enforcement layer that
sits between the Coordinator and the agents. Before any action is taken in
the system (task assignment, phase transition, agent activation), the Policy
Engine evaluates a set of registered policies to determine whether the action
should be allowed.

Architecture Context:
    The Policy Engine acts as a GATEKEEPER. Every significant action passes
    through it before execution. Think of it like a security checkpoint:
    no action proceeds unless ALL policies approve it.

    Request Flow (with Policy Engine):

        ┌─────────────┐    "Can I assign    ┌─────────────────┐
        │ Coordinator  │ ── this task?" ──→  │  Policy Engine   │
        │              │                     │                  │
        │              │ ←── YES / NO ─────  │  ┌────────────┐  │
        └─────────────┘                     │  │ Policy 1   │  │
              │                             │  │ Policy 2   │  │
              │ (only if YES)               │  │ Policy 3   │  │
              ↓                             │  │ ...        │  │
        ┌─────────────┐                     │  └────────────┘  │
        │   Agent      │                     └─────────────────┘
        └─────────────┘

    Without the Policy Engine, the Coordinator would need to hard-code
    every rule (max concurrency, timeouts, phase gates, etc.) directly
    into its dispatch logic. The Policy Engine decouples RULES from
    ORCHESTRATION, making both easier to maintain, test, and extend.

Evaluation Flow (inside the Policy Engine):

    Context dict ──→ ┌──────────────────────────┐
    (task, agent,     │  evaluate_all(context)    │
     workflow, etc.)  │                          │
                      │  for policy in policies: │
                      │    result = policy(ctx)   │
                      │    results.append(result) │
                      │                          │
                      │  return results           │
                      └──────────────────────────┘
                                  │
                                  ↓
                      ┌──────────────────────────┐
                      │  PolicyResult[]           │
                      │  [allowed=True,  ...]     │
                      │  [allowed=True,  ...]     │
                      │  [allowed=False, ...]  ← VIOLATION │
                      └──────────────────────────┘
                                  │
                                  ↓
                      enforce() raises PolicyViolationError
                      check()   returns False

Built-in Policies:
    1. MaxConcurrentTasksPolicy  - Limits number of simultaneously running agents
    2. TaskTimeoutPolicy         - Validates task timeout values are within bounds
    3. PhaseGatePolicy           - Controls phase transitions based on success rate
    4. AgentAvailabilityPolicy   - Ensures target agent is available for assignment

Extensibility:
    Custom policies are easy to add. Simply subclass ``Policy``, implement
    the ``evaluate()`` method, and register the policy with the engine:

        class MyCustomPolicy(Policy):
            @property
            def name(self) -> str:
                return "MyCustomPolicy"

            @property
            def description(self) -> str:
                return "Checks something custom"

            async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
                # Your logic here
                return PolicyResult(allowed=True, policy_name=self.name)

        engine = PolicyEngine()
        engine.register_policy(MyCustomPolicy())

Design Decisions:
    1. Policies are evaluated SEQUENTIALLY, not in parallel, because later
       policies might depend on side effects or logging from earlier ones.
       If performance becomes a concern, we can add a ``parallel_evaluate()``
       method in the future.
    2. The context dict is intentionally untyped (dict[str, Any]) to keep
       policies flexible. Each policy documents what keys it expects.
    3. ``enforce()`` raises on the FIRST violation. This is a fail-fast
       strategy: if one policy says no, there is no point evaluating more.
       Use ``evaluate_all()`` if you need to collect ALL violations.
    4. ``check()`` is a convenience method that returns a simple bool.
       Use it in conditional logic where you do not need error details.

Usage:
    >>> engine = PolicyEngine()
    >>> engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=5))
    >>> engine.register_policy(TaskTimeoutPolicy(default_timeout=300.0))
    >>>
    >>> # Soft check (returns bool)
    >>> is_ok = await engine.check({"agent_states": agent_states})
    >>>
    >>> # Hard enforce (raises on violation)
    >>> await engine.enforce({"task": task, "agent_state": agent_state})
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog
from pydantic import BaseModel, Field

from conductor.core.enums import AgentStatus
from conductor.core.exceptions import PolicyViolationError


# =============================================================================
# Logger Setup
# =============================================================================
# We use structlog for structured logging throughout the orchestration layer.
# Each policy evaluation is logged with the policy name and result, making it
# easy to trace exactly which policy allowed or denied an action in production.
# =============================================================================
logger = structlog.get_logger()


# =============================================================================
# Policy Result Model
# =============================================================================
# PolicyResult is the return type for every policy evaluation. It carries
# enough information for the caller to understand:
#   - Whether the action is allowed
#   - Which policy made the decision
#   - Why the decision was made (human-readable reason)
#   - Any extra context (metadata dict for programmatic use)
#
# Design Decision: Why a Pydantic model instead of a named tuple?
#   1. Pydantic gives us automatic validation (e.g., ``allowed`` must be bool).
#   2. Pydantic models serialize to JSON cleanly (for logging and API responses).
#   3. Pydantic models support default values (``reason`` and ``metadata``).
#   4. Consistent with the rest of ConductorAI's data model conventions.
# =============================================================================
class PolicyResult(BaseModel):
    """Result of a single policy evaluation.

    Every time a policy evaluates a context, it produces a PolicyResult that
    tells the Policy Engine whether the action should proceed or be blocked.

    Attributes:
        allowed: Whether the policy permits the action. True means the action
            can proceed (from this policy's perspective). False means the
            policy is blocking the action.
        policy_name: Name of the policy that produced this result. Used for
            logging, error messages, and debugging. Should match the
            ``Policy.name`` property of the policy that evaluated.
        reason: Human-readable explanation of why the policy allowed or denied
            the action. This is shown in error messages and logs. Keep it
            concise but informative.
            Example: "Agent coding-01 is FAILED and cannot accept tasks"
        metadata: Arbitrary key-value pairs with additional context about
            the evaluation. Useful for programmatic handling of policy results.
            Example: {"current_count": 5, "max_allowed": 5, "agent_id": "..."}

    Example (allowed):
        >>> PolicyResult(
        ...     allowed=True,
        ...     policy_name="MaxConcurrentTasksPolicy",
        ...     reason="3 of 5 slots in use",
        ...     metadata={"current": 3, "max": 5},
        ... )

    Example (denied):
        >>> PolicyResult(
        ...     allowed=False,
        ...     policy_name="AgentAvailabilityPolicy",
        ...     reason="Agent is in FAILED status",
        ...     metadata={"agent_id": "coding-01", "status": "failed"},
        ... )
    """

    allowed: bool = Field(
        description="Whether the action is permitted by this policy",
    )
    policy_name: str = Field(
        description="Name of the policy that produced this result",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation of the decision",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context about the evaluation",
    )


# =============================================================================
# Abstract Base Class: Policy
# =============================================================================
# This is the interface that ALL policies must implement. The Policy Engine
# does not care about the internal logic of a policy -- it only cares that:
#   1. The policy has a ``name`` (for identification in logs and errors).
#   2. The policy has a ``description`` (for documentation and discovery).
#   3. The policy has an ``evaluate()`` method that takes a context dict
#      and returns a PolicyResult.
#
# Design Decision: Why ABC instead of Protocol?
#   We chose ABC for the same reasons as MessageBus (see message_bus.py):
#   - Enforces method implementation at class definition time
#   - Provides clearer error messages when a method is missing
#   - Allows shared helper methods in the base class in the future
#   - Explicit inheritance communicates intent ("this IS-A Policy")
#
# Context Dict Convention:
#   The context dict is the primary way to pass data to policies. Common keys:
#
#     Key               Type                  Used By
#     ───               ────                  ───────
#     task              TaskDefinition        TaskTimeoutPolicy
#     agent_state       AgentState            AgentAvailabilityPolicy
#     agent_states      list[AgentState]      MaxConcurrentTasksPolicy
#     workflow_state    WorkflowState         PhaseGatePolicy
#
#   Policies should gracefully handle missing keys by returning allowed=True
#   with a note that the required context was not provided (fail-open for
#   missing context, fail-closed for violated rules).
# =============================================================================
class Policy(ABC):
    """Abstract base class for all ConductorAI policies.

    A Policy is a rule that determines whether a specific action should be
    allowed. Policies are registered with the PolicyEngine and evaluated
    before actions are executed.

    Subclasses must implement:
        - ``name`` property: Returns the policy's unique identifier.
        - ``description`` property: Returns a human-readable description.
        - ``evaluate()`` method: Evaluates the policy against a context dict.

    The ``evaluate()`` method receives a context dict containing relevant
    state information (task definitions, agent states, workflow state, etc.)
    and returns a PolicyResult indicating whether the action is allowed.

    Example:
        >>> class MyPolicy(Policy):
        ...     @property
        ...     def name(self) -> str:
        ...         return "MyPolicy"
        ...
        ...     @property
        ...     def description(self) -> str:
        ...         return "Checks a custom condition"
        ...
        ...     async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
        ...         if some_condition(context):
        ...             return PolicyResult(allowed=True, policy_name=self.name)
        ...         return PolicyResult(
        ...             allowed=False,
        ...             policy_name=self.name,
        ...             reason="Condition not met",
        ...         )
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name identifying this policy.

        Used in:
            - Log messages to identify which policy evaluated
            - PolicyResult.policy_name to trace decisions
            - PolicyViolationError.policy_name for error reporting
            - PolicyEngine.unregister_policy() to remove by name

        Returns:
            A unique string name for this policy.
            Convention: PascalCase matching the class name.
        """
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this policy checks.

        Used for:
            - API documentation / policy discovery endpoints
            - Logging and debugging
            - Administrative dashboards

        Returns:
            A concise description of the policy's purpose and behavior.
        """
        ...

    @abstractmethod
    async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
        """Evaluate this policy against the provided context.

        This is the core method of every policy. It examines the context
        dict, applies the policy's rules, and returns a PolicyResult
        indicating whether the action is allowed.

        Args:
            context: A dictionary containing relevant state for evaluation.
                The keys depend on the specific policy. Common keys include:
                - ``task``: TaskDefinition being assigned
                - ``agent_state``: AgentState of the target agent
                - ``agent_states``: list[AgentState] of all agents
                - ``workflow_state``: WorkflowState of the current workflow

        Returns:
            A PolicyResult with ``allowed=True`` if the action is permitted,
            or ``allowed=False`` with a reason explaining the violation.

        Note:
            Policies should handle missing context keys gracefully. If a
            required key is absent, return ``allowed=True`` with a reason
            noting the missing context. This is the "fail-open for missing
            context" convention -- we do not block actions just because the
            caller forgot to include a context key.
        """
        ...


# =============================================================================
# Built-in Policy: MaxConcurrentTasksPolicy
# =============================================================================
# This policy prevents the system from being overwhelmed by too many
# simultaneously running agents. It acts as a concurrency limiter.
#
# Why is this important?
#   - Each running agent consumes resources (LLM API calls, memory, CPU).
#   - LLM APIs have rate limits that can be exceeded with too many concurrent
#     requests (especially GPT-4 with low rate limits on new accounts).
#   - Too many concurrent tasks can degrade system stability and increase
#     error rates.
#   - A configurable limit lets operators tune based on their infrastructure.
#
# How it works:
#   1. Counts agents with status == RUNNING in the provided agent_states list.
#   2. If the count is >= max_tasks, returns allowed=False.
#   3. If the count is < max_tasks, returns allowed=True.
#
# Expected context keys:
#   - agent_states: list[AgentState] — all agent states to check
# =============================================================================
class MaxConcurrentTasksPolicy(Policy):
    """Limits the number of simultaneously running agents.

    This policy prevents resource exhaustion by capping how many agents
    can be in the RUNNING state at the same time. When the limit is
    reached, new task assignments are blocked until a running agent
    completes its current task.

    Attributes:
        _max_tasks: Maximum number of agents that can be RUNNING concurrently.

    Example:
        >>> policy = MaxConcurrentTasksPolicy(max_tasks=3)
        >>> result = await policy.evaluate({
        ...     "agent_states": [state1, state2, state3],  # 2 RUNNING
        ... })
        >>> result.allowed  # True (2 < 3)
    """

    def __init__(self, max_tasks: int = 5) -> None:
        """Initialize the max concurrent tasks policy.

        Args:
            max_tasks: Maximum number of agents allowed in RUNNING state
                simultaneously. Default is 5, which is a conservative limit
                suitable for most LLM API rate limits. Increase for high-
                throughput deployments with generous rate limits.
        """
        self._max_tasks = max_tasks

    @property
    def name(self) -> str:
        """Return the policy name for identification."""
        return "MaxConcurrentTasksPolicy"

    @property
    def description(self) -> str:
        """Return a description of what this policy enforces."""
        return (
            f"Limits concurrent running agents to a maximum of {self._max_tasks}. "
            f"Prevents resource exhaustion and LLM API rate limit violations."
        )

    async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
        """Check whether the number of running agents is within the limit.

        Counts agents with ``status == AgentStatus.RUNNING`` in the provided
        ``agent_states`` list and compares against ``_max_tasks``.

        Args:
            context: Must contain:
                - ``agent_states`` (list[AgentState]): All agent states to check.

        Returns:
            PolicyResult with ``allowed=True`` if under the limit,
            ``allowed=False`` if the limit has been reached or exceeded.
            If ``agent_states`` is missing from context, returns allowed=True
            (fail-open: do not block actions due to missing context).
        """
        # --- Graceful handling of missing context ---
        # If the caller did not provide agent_states, we cannot evaluate
        # this policy. We fail-open (allow) rather than blocking an action
        # just because the caller forgot to include the key.
        agent_states = context.get("agent_states")
        if agent_states is None:
            return PolicyResult(
                allowed=True,
                policy_name=self.name,
                reason="No agent_states provided in context; skipping evaluation",
                metadata={"skipped": True},
            )

        # --- Count the number of agents currently in RUNNING state ---
        # We iterate through all agent states and count how many have
        # status == RUNNING. This is an O(n) scan, but the number of
        # agents is typically small (< 50), so performance is not a concern.
        running_count = sum(
            1 for state in agent_states
            if state.status == AgentStatus.RUNNING
        )

        # --- Compare against the limit ---
        if running_count >= self._max_tasks:
            return PolicyResult(
                allowed=False,
                policy_name=self.name,
                reason=(
                    f"Maximum concurrent tasks reached: {running_count} "
                    f"agents are RUNNING (limit: {self._max_tasks})"
                ),
                metadata={
                    "running_count": running_count,
                    "max_tasks": self._max_tasks,
                },
            )

        # --- Under the limit: action is allowed ---
        return PolicyResult(
            allowed=True,
            policy_name=self.name,
            reason=(
                f"{running_count} of {self._max_tasks} concurrent task slots in use"
            ),
            metadata={
                "running_count": running_count,
                "max_tasks": self._max_tasks,
            },
        )


# =============================================================================
# Built-in Policy: TaskTimeoutPolicy
# =============================================================================
# This policy validates that a task's timeout value is within acceptable
# bounds. It prevents two dangerous scenarios:
#
#   1. Timeout too low (≤ 0): The task would immediately time out or never
#      start, wasting resources and producing confusing error messages.
#
#   2. Timeout too high (> 3600s / 1 hour): An excessively long timeout
#      could allow a stuck task to consume resources indefinitely, blocking
#      the workflow pipeline. One hour is a generous upper bound -- most
#      LLM tasks complete in seconds to minutes.
#
# This policy operates on the TaskDefinition model, specifically the
# ``timeout_seconds`` field. Note that TaskDefinition already has Pydantic
# validation (ge=1, le=3600), but this policy provides runtime enforcement
# at the orchestration level, which catches dynamically constructed tasks
# and provides better error messages.
#
# Expected context keys:
#   - task: TaskDefinition — the task to validate
# =============================================================================
class TaskTimeoutPolicy(Policy):
    """Validates that task timeouts are within acceptable bounds.

    Prevents tasks from having unreasonable timeout values that could
    cause immediate failures (too low) or resource hogging (too high).

    Bounds:
        - Minimum: > 0 seconds (tasks must have a positive timeout)
        - Maximum: < 3600 seconds (1 hour; prevents stuck-task resource waste)

    Attributes:
        _default_timeout: The default timeout value used for reference
            in log messages and descriptions. This policy does NOT set
            the timeout — it only validates that the existing timeout
            on the task is within bounds.

    Example:
        >>> policy = TaskTimeoutPolicy(default_timeout=300.0)
        >>> result = await policy.evaluate({
        ...     "task": TaskDefinition(name="test", timeout_seconds=120),
        ... })
        >>> result.allowed  # True (0 < 120 < 3600)
    """

    def __init__(self, default_timeout: float = 300.0) -> None:
        """Initialize the task timeout policy.

        Args:
            default_timeout: Reference default timeout in seconds. This value
                is stored for informational purposes (descriptions, metadata)
                but does not affect the validation bounds. The hard bounds
                are always > 0 and < 3600. Default is 300s (5 minutes),
                which is suitable for most LLM-based agent tasks.
        """
        self._default_timeout = default_timeout

    @property
    def name(self) -> str:
        """Return the policy name for identification."""
        return "TaskTimeoutPolicy"

    @property
    def description(self) -> str:
        """Return a description of what this policy enforces."""
        return (
            f"Validates task timeouts are within bounds (> 0 and < 3600 seconds). "
            f"Default reference timeout: {self._default_timeout}s."
        )

    async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
        """Check whether the task's timeout is within acceptable bounds.

        Validates that ``task.timeout_seconds`` is > 0 AND < 3600.

        Args:
            context: Must contain:
                - ``task`` (TaskDefinition): The task whose timeout to validate.

        Returns:
            PolicyResult with ``allowed=True`` if the timeout is within bounds,
            ``allowed=False`` if the timeout is out of bounds.
            If ``task`` is missing from context, returns allowed=True
            (fail-open for missing context).
        """
        # --- Graceful handling of missing context ---
        task = context.get("task")
        if task is None:
            return PolicyResult(
                allowed=True,
                policy_name=self.name,
                reason="No task provided in context; skipping evaluation",
                metadata={"skipped": True},
            )

        timeout = task.timeout_seconds

        # --- Check lower bound ---
        # A timeout of 0 or negative makes no sense: the task would
        # immediately time out before doing any work.
        if timeout <= 0:
            return PolicyResult(
                allowed=False,
                policy_name=self.name,
                reason=(
                    f"Task timeout must be positive, got {timeout}s. "
                    f"A non-positive timeout would cause immediate task failure."
                ),
                metadata={
                    "timeout_seconds": timeout,
                    "min_allowed": 0,
                    "max_allowed": 3600,
                    "default_timeout": self._default_timeout,
                },
            )

        # --- Check upper bound ---
        # A timeout over 1 hour is excessive for any ConductorAI task.
        # If a task genuinely needs more than an hour, the workflow
        # design should break it into smaller subtasks.
        if timeout >= 3600:
            return PolicyResult(
                allowed=False,
                policy_name=self.name,
                reason=(
                    f"Task timeout exceeds maximum: {timeout}s >= 3600s (1 hour). "
                    f"Consider breaking the task into smaller subtasks."
                ),
                metadata={
                    "timeout_seconds": timeout,
                    "min_allowed": 0,
                    "max_allowed": 3600,
                    "default_timeout": self._default_timeout,
                },
            )

        # --- Within bounds: action is allowed ---
        return PolicyResult(
            allowed=True,
            policy_name=self.name,
            reason=f"Task timeout {timeout}s is within bounds (0, 3600)",
            metadata={
                "timeout_seconds": timeout,
                "default_timeout": self._default_timeout,
            },
        )


# =============================================================================
# Built-in Policy: PhaseGatePolicy
# =============================================================================
# This policy controls workflow phase transitions. Before the WorkflowEngine
# advances from one phase to the next (e.g., DEVELOPMENT -> DEVOPS), it
# checks this policy to ensure enough tasks in the current phase succeeded.
#
# Why is this important?
#   Advancing to DEVOPS when most Development tasks failed would be wasteful:
#   you would be deploying broken code. The PhaseGatePolicy acts as a quality
#   gate that ensures a minimum success rate before proceeding.
#
# How it works:
#   1. Reads the workflow_state from context.
#   2. Calculates the success rate: completed_tasks / (completed + failed).
#   3. If the success rate is below required_success_rate, blocks advancement.
#   4. Special case: if completed_task_count is 0, blocks advancement
#      (no tasks have completed, so we cannot assess quality).
#
# Expected context keys:
#   - workflow_state: WorkflowState — the current workflow state
# =============================================================================
class PhaseGatePolicy(Policy):
    """Controls phase transitions based on task success rate.

    Before a workflow advances to the next phase, this policy verifies
    that enough tasks in the current phase completed successfully. This
    prevents broken or incomplete work from flowing downstream.

    Success Rate Calculation:
        success_rate = completed_count / (completed_count + failed_count)

        If no tasks have been attempted (completed_count == 0), the gate
        blocks advancement because there is no evidence of quality.

    Attributes:
        _required_success_rate: Minimum fraction (0.0 to 1.0) of tasks
            that must succeed for the phase gate to open. Default is 0.8
            (80%), meaning up to 20% of tasks can fail before the gate
            blocks advancement.

    Example:
        >>> policy = PhaseGatePolicy(required_success_rate=0.8)
        >>> # Workflow with 8 completed, 2 failed → 80% success → allowed
        >>> result = await policy.evaluate({"workflow_state": state})
        >>> result.allowed  # True (0.8 >= 0.8)
    """

    def __init__(self, required_success_rate: float = 0.8) -> None:
        """Initialize the phase gate policy.

        Args:
            required_success_rate: Minimum success rate (0.0 to 1.0) required
                to advance to the next phase. Default is 0.8 (80%). Set to
                1.0 for zero-tolerance (every task must succeed). Set lower
                for more lenient workflows that can tolerate some failures.
        """
        self._required_success_rate = required_success_rate

    @property
    def name(self) -> str:
        """Return the policy name for identification."""
        return "PhaseGatePolicy"

    @property
    def description(self) -> str:
        """Return a description of what this policy enforces."""
        return (
            f"Requires a minimum task success rate of "
            f"{self._required_success_rate:.0%} before allowing phase "
            f"transitions. Prevents broken work from flowing downstream."
        )

    async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
        """Check whether the workflow's task success rate meets the threshold.

        Calculates the success rate from the WorkflowState's completed and
        failed task counts, then compares against the required rate.

        Args:
            context: Must contain:
                - ``workflow_state`` (WorkflowState): The current workflow state.

        Returns:
            PolicyResult with ``allowed=True`` if the success rate meets the
            threshold, ``allowed=False`` if it does not.
            If ``workflow_state`` is missing from context, returns allowed=True
            (fail-open for missing context).
        """
        # --- Graceful handling of missing context ---
        workflow_state = context.get("workflow_state")
        if workflow_state is None:
            return PolicyResult(
                allowed=True,
                policy_name=self.name,
                reason="No workflow_state provided in context; skipping evaluation",
                metadata={"skipped": True},
            )

        completed_count = workflow_state.completed_task_count
        failed_count = workflow_state.failed_task_count
        total_count = completed_count + failed_count

        # --- Special case: no tasks completed ---
        # If no tasks have completed at all, we cannot assess quality.
        # Block advancement because there is nothing to advance WITH.
        # This catches scenarios where the phase just started and no
        # agents have reported results yet.
        if completed_count == 0:
            return PolicyResult(
                allowed=False,
                policy_name=self.name,
                reason=(
                    "No tasks have completed yet. Cannot assess quality "
                    "for phase advancement."
                ),
                metadata={
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "total_count": total_count,
                    "required_success_rate": self._required_success_rate,
                    "actual_success_rate": 0.0,
                },
            )

        # --- Calculate the actual success rate ---
        # success_rate = completed / total (where total = completed + failed).
        # We use total_count (not just completed_count) to include failures
        # in the denominator, giving an accurate picture of task quality.
        actual_success_rate = completed_count / total_count

        # --- Compare against the required threshold ---
        if actual_success_rate < self._required_success_rate:
            return PolicyResult(
                allowed=False,
                policy_name=self.name,
                reason=(
                    f"Task success rate {actual_success_rate:.1%} is below "
                    f"the required {self._required_success_rate:.1%}. "
                    f"({completed_count} completed, {failed_count} failed "
                    f"out of {total_count} total)"
                ),
                metadata={
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "total_count": total_count,
                    "required_success_rate": self._required_success_rate,
                    "actual_success_rate": actual_success_rate,
                },
            )

        # --- Success rate meets the threshold: allow phase transition ---
        return PolicyResult(
            allowed=True,
            policy_name=self.name,
            reason=(
                f"Task success rate {actual_success_rate:.1%} meets the "
                f"required {self._required_success_rate:.1%} threshold. "
                f"({completed_count} completed, {failed_count} failed)"
            ),
            metadata={
                "completed_count": completed_count,
                "failed_count": failed_count,
                "total_count": total_count,
                "required_success_rate": self._required_success_rate,
                "actual_success_rate": actual_success_rate,
            },
        )


# =============================================================================
# Built-in Policy: AgentAvailabilityPolicy
# =============================================================================
# This policy checks whether a specific agent is available to receive a
# new task assignment. An agent is considered UNAVAILABLE if it is:
#
#   - FAILED:    The agent encountered an error and needs recovery.
#   - RUNNING:   The agent is already executing a task.
#
# An agent IS available if it is:
#   - IDLE:      The agent is ready and waiting for work.
#   - COMPLETED: The agent finished its last task and can accept a new one.
#   - WAITING:   The agent is blocked but could potentially accept work
#                (depends on the waiting reason — we allow it here and let
#                the coordinator decide whether to assign).
#
# This policy prevents task assignment to agents that cannot accept work,
# which would result in dropped tasks or confusing error states.
#
# Expected context keys:
#   - agent_state: AgentState — the state of the target agent
# =============================================================================
class AgentAvailabilityPolicy(Policy):
    """Checks whether a target agent is available for task assignment.

    An agent is considered unavailable if it is in FAILED or RUNNING status.
    This prevents assigning tasks to agents that are broken or already busy.

    Available statuses: IDLE, COMPLETED, WAITING, CANCELLED
    Unavailable statuses: FAILED, RUNNING

    Example:
        >>> policy = AgentAvailabilityPolicy()
        >>> result = await policy.evaluate({
        ...     "agent_state": AgentState(
        ...         agent_id="coding-01",
        ...         agent_type=AgentType.CODING,
        ...         status=AgentStatus.IDLE,
        ...     ),
        ... })
        >>> result.allowed  # True (IDLE is available)
    """

    @property
    def name(self) -> str:
        """Return the policy name for identification."""
        return "AgentAvailabilityPolicy"

    @property
    def description(self) -> str:
        """Return a description of what this policy enforces."""
        return (
            "Checks that the target agent is not in FAILED or RUNNING status "
            "before allowing task assignment. Prevents assigning work to "
            "broken or already-busy agents."
        )

    async def evaluate(self, context: dict[str, Any]) -> PolicyResult:
        """Check whether the target agent is available for assignment.

        Examines the agent's status to determine availability. Agents in
        FAILED or RUNNING status are considered unavailable.

        Args:
            context: Must contain:
                - ``agent_state`` (AgentState): The state of the target agent.

        Returns:
            PolicyResult with ``allowed=True`` if the agent can accept a task,
            ``allowed=False`` if the agent is FAILED or RUNNING.
            If ``agent_state`` is missing from context, returns allowed=True
            (fail-open for missing context).
        """
        # --- Graceful handling of missing context ---
        agent_state = context.get("agent_state")
        if agent_state is None:
            return PolicyResult(
                allowed=True,
                policy_name=self.name,
                reason="No agent_state provided in context; skipping evaluation",
                metadata={"skipped": True},
            )

        # --- Define which statuses are considered unavailable ---
        # FAILED: The agent encountered an error and has not recovered.
        #   Assigning a new task would likely fail again.
        # RUNNING: The agent is already executing a task.
        #   ConductorAI agents handle one task at a time (no multi-tasking).
        unavailable_statuses = {AgentStatus.FAILED, AgentStatus.RUNNING}

        if agent_state.status in unavailable_statuses:
            return PolicyResult(
                allowed=False,
                policy_name=self.name,
                reason=(
                    f"Agent '{agent_state.agent_id}' is in "
                    f"{agent_state.status.value.upper()} status and cannot "
                    f"accept new tasks"
                ),
                metadata={
                    "agent_id": agent_state.agent_id,
                    "agent_type": agent_state.agent_type.value,
                    "current_status": agent_state.status.value,
                    "unavailable_statuses": [s.value for s in unavailable_statuses],
                },
            )

        # --- Agent is available ---
        return PolicyResult(
            allowed=True,
            policy_name=self.name,
            reason=(
                f"Agent '{agent_state.agent_id}' is in "
                f"{agent_state.status.value.upper()} status and can accept tasks"
            ),
            metadata={
                "agent_id": agent_state.agent_id,
                "agent_type": agent_state.agent_type.value,
                "current_status": agent_state.status.value,
            },
        )


# =============================================================================
# Policy Engine
# =============================================================================
# The PolicyEngine is the central coordinator for all policies. It maintains
# a registry of policies and provides three evaluation modes:
#
#   1. evaluate_all(context) → list[PolicyResult]
#      Runs ALL policies and returns every result. Use this when you need
#      to see the full picture (e.g., for dashboards or debugging).
#
#   2. enforce(context) → None (raises PolicyViolationError)
#      Runs all policies and raises an error on the FIRST violation.
#      Use this when the action MUST comply with all policies (e.g., task
#      assignment in production).
#
#   3. check(context) → bool
#      Runs all policies and returns True only if ALL pass. Use this for
#      simple conditional logic where you do not need error details.
#
# Evaluation Flow Diagram:
#
#     context dict
#         │
#         ▼
#   ┌─────────────┐
#   │  evaluate_   │──→ Policy 1 ──→ PolicyResult
#   │  all()       │──→ Policy 2 ──→ PolicyResult
#   │              │──→ Policy 3 ──→ PolicyResult
#   └─────────────┘──→ Policy N ──→ PolicyResult
#         │                              │
#         ▼                              ▼
#   list[PolicyResult]            All collected
#         │
#    ┌────┴─────┐
#    │          │
#    ▼          ▼
# enforce()  check()
#    │          │
#    ▼          ▼
# Raises if   Returns
# any False   True/False
#
# Thread Safety:
#   The PolicyEngine is NOT thread-safe. It is designed to be used within
#   a single asyncio event loop. The list of policies is modified via
#   register/unregister, which are synchronous operations. If concurrent
#   modification is needed, external synchronization should be added.
# =============================================================================
class PolicyEngine:
    """Central engine for evaluating and enforcing policies.

    The PolicyEngine maintains a registry of Policy instances and provides
    methods to evaluate them against a context dict. It is the single point
    of contact for all policy checks in the orchestration layer.

    Three Evaluation Modes:
        1. ``evaluate_all(context)`` - Returns all results (for inspection)
        2. ``enforce(context)``      - Raises on first violation (for gating)
        3. ``check(context)``        - Returns bool (for conditionals)

    Attributes:
        _policies: Internal list of registered Policy instances. Policies
            are evaluated in the order they were registered.
        _logger: Structured logger bound with component context for
            filtering policy engine logs.

    Example:
        >>> engine = PolicyEngine()
        >>> engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=5))
        >>> engine.register_policy(AgentAvailabilityPolicy())
        >>>
        >>> # Check before assigning a task
        >>> context = {
        ...     "agent_states": all_agent_states,
        ...     "agent_state": target_agent_state,
        ... }
        >>> await engine.enforce(context)  # Raises if any policy denies
    """

    def __init__(self) -> None:
        """Initialize the PolicyEngine with an empty policy registry.

        The engine starts with no policies registered. Use ``register_policy()``
        to add policies before evaluation. An engine with no policies will
        allow all actions (evaluate_all returns empty list, check returns True,
        enforce does nothing).
        """
        # -----------------------------------------------------------------
        # Policy Registry
        # -----------------------------------------------------------------
        # Policies are stored in a list to preserve registration order.
        # They are evaluated sequentially in this order. Using a list
        # (rather than a dict) because:
        #   1. Order matters for logging clarity and predictability.
        #   2. Multiple policies of the same type (with different configs)
        #      are allowed (e.g., two MaxConcurrentTasksPolicy instances
        #      with different limits for different agent types).
        #   3. Lists are simpler than ordered dicts for this use case.
        # -----------------------------------------------------------------
        self._policies: list[Policy] = []

        # -----------------------------------------------------------------
        # Logger with component context
        # -----------------------------------------------------------------
        # Every log line from the PolicyEngine includes:
        #   {"component": "policy_engine"}
        # This makes it easy to filter policy evaluation logs in production.
        # -----------------------------------------------------------------
        self._logger = logger.bind(component="policy_engine")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def policies(self) -> list[Policy]:
        """Return the list of registered policies.

        Returns a copy of the internal list to prevent external mutation.
        Modifying the returned list will NOT affect the engine's registry.
        Use ``register_policy()`` and ``unregister_policy()`` to modify
        the registry.

        Returns:
            A list of all registered Policy instances, in registration order.
        """
        # Return a shallow copy to prevent callers from modifying the
        # internal list (e.g., engine.policies.append(sneaky_policy) would
        # bypass registration logging if we returned the actual list).
        return list(self._policies)

    @property
    def policy_count(self) -> int:
        """Return the number of registered policies.

        This is a convenience property for quick checks and logging.

        Returns:
            The integer count of registered policies.
        """
        return len(self._policies)

    # =========================================================================
    # Policy Registration
    # =========================================================================

    def register_policy(self, policy: Policy) -> None:
        """Register a policy with the engine.

        The policy will be included in all subsequent evaluate_all(),
        enforce(), and check() calls. Policies are evaluated in the order
        they are registered.

        Duplicate policies (same name) are allowed. This enables scenarios
        like registering the same policy type with different configurations
        (e.g., different max_tasks limits for different contexts). If you
        want to replace a policy, unregister the old one first.

        Args:
            policy: The Policy instance to register. Must implement the
                Policy ABC (name, description, evaluate).

        Example:
            >>> engine = PolicyEngine()
            >>> engine.register_policy(MaxConcurrentTasksPolicy(max_tasks=3))
            >>> engine.policy_count  # 1
        """
        self._policies.append(policy)
        self._logger.info(
            "policy_registered",
            policy_name=policy.name,
            policy_description=policy.description,
            total_policies=len(self._policies),
        )

    def unregister_policy(self, policy_name: str) -> bool:
        """Remove a policy from the engine by name.

        Removes the FIRST policy with the given name. If multiple policies
        share the same name, only the first one is removed. Call repeatedly
        to remove all.

        Args:
            policy_name: The name of the policy to remove. Must match
                the ``Policy.name`` property exactly (case-sensitive).

        Returns:
            True if a policy was found and removed, False if no policy
            with the given name was registered.

        Example:
            >>> engine.register_policy(MaxConcurrentTasksPolicy())
            >>> engine.unregister_policy("MaxConcurrentTasksPolicy")  # True
            >>> engine.unregister_policy("NonexistentPolicy")         # False
        """
        # Iterate through the policies to find the first one with the
        # matching name. We use enumerate + break instead of a list
        # comprehension because we only want to remove the FIRST match.
        for i, policy in enumerate(self._policies):
            if policy.name == policy_name:
                self._policies.pop(i)
                self._logger.info(
                    "policy_unregistered",
                    policy_name=policy_name,
                    total_policies=len(self._policies),
                )
                return True

        # No policy found with the given name
        self._logger.warning(
            "policy_not_found_for_unregister",
            policy_name=policy_name,
        )
        return False

    # =========================================================================
    # Evaluation Methods
    # =========================================================================

    async def evaluate_all(self, context: dict[str, Any]) -> list[PolicyResult]:
        """Evaluate ALL registered policies and return their results.

        Runs every registered policy against the provided context and
        collects the results. All policies are evaluated regardless of
        whether earlier ones passed or failed (unlike ``enforce()``,
        which stops on first failure).

        This method is useful for:
            - Dashboards showing which policies pass/fail
            - Debugging why an action was blocked
            - Collecting metrics on policy evaluation patterns

        Args:
            context: A dictionary containing the state needed by the
                registered policies. Each policy documents its expected keys.

        Returns:
            A list of PolicyResult objects, one per registered policy,
            in the same order as the policies were registered.
            Returns an empty list if no policies are registered.

        Note:
            Policies are evaluated SEQUENTIALLY (not concurrently). This
            ensures deterministic evaluation order and prevents potential
            issues with shared mutable context. If performance becomes
            a concern, a ``parallel_evaluate_all()`` method can be added.
        """
        results: list[PolicyResult] = []

        self._logger.debug(
            "evaluating_all_policies",
            policy_count=len(self._policies),
            context_keys=list(context.keys()),
        )

        # --- Evaluate each policy sequentially ---
        # We iterate through the list in registration order. Each policy
        # receives the same context dict and returns its own PolicyResult.
        for policy in self._policies:
            try:
                result = await policy.evaluate(context)
                results.append(result)

                # Log each individual evaluation for traceability.
                # In production, operators can filter by policy_name to see
                # how often each policy allows or denies actions.
                self._logger.debug(
                    "policy_evaluated",
                    policy_name=policy.name,
                    allowed=result.allowed,
                    reason=result.reason,
                )

            except Exception as exc:
                # --- Handle policy evaluation errors ---
                # If a policy raises an unexpected exception (bug in the
                # policy code), we do NOT let it crash the entire engine.
                # Instead, we log the error and record a DENIED result.
                #
                # Design Decision: Fail-closed on evaluation errors.
                # If a policy cannot evaluate properly, we treat it as a
                # denial. This is the safer option: a broken policy should
                # block actions rather than silently allowing them.
                self._logger.error(
                    "policy_evaluation_error",
                    policy_name=policy.name,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                results.append(
                    PolicyResult(
                        allowed=False,
                        policy_name=policy.name,
                        reason=f"Policy evaluation failed with error: {exc}",
                        metadata={"error": str(exc), "error_type": type(exc).__name__},
                    )
                )

        self._logger.debug(
            "all_policies_evaluated",
            total=len(results),
            allowed_count=sum(1 for r in results if r.allowed),
            denied_count=sum(1 for r in results if not r.allowed),
        )

        return results

    async def enforce(self, context: dict[str, Any]) -> None:
        """Evaluate all policies and raise an error if any deny the action.

        This is the primary enforcement method. It evaluates all registered
        policies and raises a ``PolicyViolationError`` on the FIRST violation
        found. Use this method when an action MUST comply with all policies.

        This method is designed for the "gatekeeper" pattern:
            1. Coordinator prepares to assign a task
            2. Coordinator calls ``await engine.enforce(context)``
            3. If enforce() returns normally, proceed with the assignment
            4. If enforce() raises, abort the assignment and handle the error

        Args:
            context: A dictionary containing the state needed by the
                registered policies.

        Raises:
            PolicyViolationError: If any registered policy denies the action.
                The error includes the policy_name and violation_details
                from the first denying policy.

        Example:
            >>> try:
            ...     await engine.enforce({"agent_state": agent_state})
            ...     assign_task(agent_state, task)  # Only reached if allowed
            ... except PolicyViolationError as e:
            ...     logger.warning("Blocked by policy", policy=e.policy_name)
        """
        # Evaluate all policies to get the complete picture.
        # We call evaluate_all() rather than duplicating the loop because:
        #   1. DRY — evaluation logic is defined in one place
        #   2. All policies get logged even if we raise on the first failure
        #   3. evaluate_all() handles errors gracefully
        results = await self.evaluate_all(context)

        # --- Check for violations ---
        # Find the first denied result and raise a PolicyViolationError.
        # We raise on the FIRST violation (fail-fast) because:
        #   1. The action cannot proceed regardless of how many policies deny it
        #   2. The caller usually only needs to know WHY it was blocked, not
        #      every reason it was blocked
        #   3. It produces cleaner error messages
        for result in results:
            if not result.allowed:
                self._logger.warning(
                    "policy_violation_enforced",
                    policy_name=result.policy_name,
                    reason=result.reason,
                    metadata=result.metadata,
                )
                raise PolicyViolationError(
                    message=f"Policy '{result.policy_name}' denied the action: {result.reason}",
                    policy_name=result.policy_name,
                    violation_details=result.reason,
                    details=result.metadata,
                )

        # --- All policies passed ---
        self._logger.debug(
            "all_policies_passed",
            policy_count=len(results),
        )

    async def check(self, context: dict[str, Any]) -> bool:
        """Evaluate all policies and return whether all pass.

        This is a convenience method for simple conditional logic. It returns
        True only if ALL registered policies allow the action. Unlike
        ``enforce()``, it does not raise an exception — it simply returns
        a bool.

        Use this when you want to CHECK whether an action is allowed without
        blocking execution:
            if await engine.check(context):
                proceed()
            else:
                try_alternative()

        Args:
            context: A dictionary containing the state needed by the
                registered policies.

        Returns:
            True if ALL registered policies allow the action (or if no
            policies are registered). False if ANY policy denies the action.

        Example:
            >>> if await engine.check({"agent_states": states}):
            ...     print("All policies passed")
            ... else:
            ...     print("At least one policy denied")
        """
        results = await self.evaluate_all(context)
        # Optimization: Instead of calling `evaluate_all()`, we iterate through
        # policies and short-circuit on the first failure. This is more
        # efficient for a simple boolean check, as it avoids evaluating
        # all policies if one of the first ones returns a denial.
        for policy in self._policies:
            try:
                result = await policy.evaluate(context)
                if not result.allowed:
                    self._logger.debug(
                        "policy_check_denied",
                        policy_name=policy.name,
                        reason=result.reason,
                    )
                    return False
            except Exception as exc:
                # For safety, any unexpected error during a policy's evaluation
                # is treated as a denial (fail-closed).
                self._logger.error(
                    "policy_evaluation_error_during_check",
                    policy_name=policy.name,
                    error=str(exc),
                )
                return False

        # All policies must return allowed=True for check() to return True.
        # An empty results list (no policies) returns True (vacuously true:
        # no policies means no objections).
        all_passed = all(result.allowed for result in results)

        self._logger.debug(
            "policy_check_result",
            all_passed=all_passed,
            policy_count=len(results),
        )

        return all_passed
        # If the loop completes, all policies passed.
        self._logger.debug("policy_check_passed", policy_count=len(self._policies))
        return True
