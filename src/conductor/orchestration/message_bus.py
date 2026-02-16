"""
conductor.orchestration.message_bus - Agent Communication Bus
==============================================================

This module implements the Message Bus -- the communication backbone of
ConductorAI. Every message between agents, the coordinator, and the workflow
engine flows through the Message Bus.

Architecture Context:
    The Message Bus sits at the heart of the orchestration layer. It decouples
    agents from each other: agents never call each other directly. Instead,
    they publish messages to named channels, and the bus delivers them to all
    subscribers on those channels.

    ┌──────────────┐                           ┌──────────────┐
    │ Coding Agent │ ──publish──>  MESSAGE  ──> │ Coordinator  │
    └──────────────┘              BUS           └──────────────┘
    ┌──────────────┐              |             ┌──────────────┐
    │ Review Agent │ <──subscribe─┘             │ Monitor Agent│
    └──────────────┘                            └──────────────┘

Communication Patterns:
    1. **Pub/Sub** (fire-and-forget):
       Publisher sends to a channel; all subscribers on that channel receive it.
       Used for: broadcasts, status updates, phase transitions.

    2. **Request-Response** (synchronous over async):
       Publisher sends a request with a correlation_id, then waits for a
       response with the same correlation_id. Uses ``asyncio.Future`` under
       the hood to block the caller until the response arrives or timeout.
       Used for: task assignments (coordinator -> agent -> result).

Channel Naming Convention:
    Channels are hierarchical, colon-separated strings that categorize messages:

    - ``conductor:agent:{agent_id}``        Direct message to a specific agent.
                                            Example: "conductor:agent:coding-01"

    - ``conductor:broadcast``               Broadcast to ALL subscribed agents.
                                            Used for system-wide announcements.

    - ``conductor:phase:{phase_name}``      Messages scoped to a workflow phase.
                                            Example: "conductor:phase:development"

    - ``conductor:workflow:{workflow_id}``   Messages scoped to a specific workflow run.
                                            Example: "conductor:workflow:wf-abc-123"

    - ``conductor:dlq``                     Dead Letter Queue -- messages that could
                                            not be delivered after all retries.

Implementations:
    - InMemoryMessageBus:  For development and testing. All messages stay in
                           process memory. No external dependencies.
    - RedisMessageBus:     For production. Uses Redis Pub/Sub for cross-process
                           communication. (Stub -- to be fully implemented later.)

Usage:
    >>> bus = InMemoryMessageBus()
    >>> await bus.connect()
    >>>
    >>> # Subscribe to a channel
    >>> async def handler(msg: AgentMessage) -> None:
    ...     print(f"Received: {msg.message_type}")
    >>> await bus.subscribe("conductor:agent:coding-01", handler)
    >>>
    >>> # Publish a message
    >>> msg = AgentMessage(
    ...     message_type=MessageType.TASK_ASSIGNMENT,
    ...     sender_id="coordinator",
    ...     recipient_id="coding-01",
    ...     payload={"task": task_def.model_dump()},
    ... )
    >>> await bus.publish("conductor:agent:coding-01", msg)
    >>>
    >>> await bus.disconnect()
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Optional

import structlog

from conductor.core.exceptions import MessageBusError
from conductor.core.messages import AgentMessage


# =============================================================================
# Logger Setup
# =============================================================================
# We use structlog for structured logging throughout the orchestration layer.
# The module-level logger is shared across all classes in this file. Each class
# binds additional context (like component="message_bus", impl="in_memory") to
# their own logger instances for easy filtering in production logs.
# =============================================================================
logger = structlog.get_logger()


# =============================================================================
# Type Aliases
# =============================================================================
# A MessageCallback is an async function that takes an AgentMessage and returns
# nothing. This is the required signature for all channel subscription handlers.
#
# Example callback:
#     async def on_task_result(message: AgentMessage) -> None:
#         result = TaskResultPayload(**message.payload)
#         process_result(result)
#
# We use Callable[[AgentMessage], Awaitable[None]] instead of
# Callable[[AgentMessage], Coroutine[Any, Any, None]] because Awaitable is
# more general and works with any async callable (coroutines, Futures, etc.).
# =============================================================================
MessageCallback = Callable[[AgentMessage], Awaitable[None]]


# =============================================================================
# Abstract Base Class: MessageBus
# =============================================================================
# This ABC defines the contract that ALL message bus implementations must
# satisfy. By programming to this interface (not a concrete class), the rest
# of ConductorAI can swap between InMemoryMessageBus (for tests) and
# RedisMessageBus (for production) without changing any calling code.
#
# Design Decision: Why an ABC instead of a Protocol?
#   We chose ABC because:
#   1. We want to enforce method implementation at class definition time
#      (not just at call time like Protocol / duck typing).
#   2. We may add shared helper methods in the base class later.
#   3. ABCs provide clearer error messages when a method is missing.
#   4. Explicit inheritance communicates intent ("this IS-A MessageBus").
# =============================================================================
class MessageBus(ABC):
    """Abstract interface for agent-to-agent communication.

    The MessageBus is the communication backbone of ConductorAI. It supports
    two communication patterns:

    1. **Pub/Sub** (publish/subscribe):
       - ``publish(channel, message)`` sends a message to a channel.
       - ``subscribe(channel, callback)`` registers a handler for a channel.
       - All subscribers on a channel receive every message published to it.

    2. **Request-Response**:
       - ``request(channel, message, timeout)`` sends a message and waits
         for a correlated response (matched by ``correlation_id``).
       - The responder uses ``message.create_response(...)`` to create a
         reply with the same correlation_id.

    Lifecycle:
        The bus must be connected before use and disconnected after::

            bus = InMemoryMessageBus()
            await bus.connect()       # Initialize resources
            # ... use the bus ...
            await bus.disconnect()    # Clean up resources

    Subclasses must implement all abstract methods:
        - ``publish()``:      Deliver a message to all subscribers on a channel.
        - ``subscribe()``:    Register a callback for a channel.
        - ``unsubscribe()``:  Remove all callbacks for a channel.
        - ``request()``:      Send a message and await a correlated response.
        - ``connect()``:      Initialize the bus (establish connections, etc.).
        - ``disconnect()``:   Tear down the bus (close connections, etc.).
    """

    @abstractmethod
    async def publish(self, channel: str, message: AgentMessage) -> None:
        """Publish a message to a channel.

        All callbacks registered for the given channel via ``subscribe()``
        will be invoked with the message. If no subscribers exist on the
        channel, the message is silently dropped (no error raised).

        Messages that have exceeded their TTL (``message.is_expired()``)
        should be discarded by implementations rather than delivered.

        Args:
            channel: The channel name to publish to.
                Convention: "conductor:agent:{id}", "conductor:broadcast", etc.
            message: The AgentMessage to deliver to all subscribers.

        Raises:
            MessageBusError: If the bus is not connected or publishing fails
                due to an infrastructure error (e.g., Redis connection lost).
        """
        ...

    @abstractmethod
    async def subscribe(
        self, channel: str, callback: MessageCallback
    ) -> None:
        """Register a callback to receive messages on a channel.

        Multiple callbacks can be registered on the same channel -- each one
        will be invoked independently when a message arrives. The same
        callback can be registered on multiple channels.

        Callbacks are invoked concurrently (via ``asyncio.gather``) when a
        message is published to the channel. If a callback raises an
        exception, it should be caught and logged by the implementation
        (not propagated to the publisher).

        Args:
            channel: The channel name to subscribe to.
            callback: An async function with signature:
                ``async def handler(message: AgentMessage) -> None``

        Raises:
            MessageBusError: If the bus is not connected.
        """
        ...

    @abstractmethod
    async def unsubscribe(self, channel: str) -> None:
        """Remove ALL callbacks registered for a channel.

        After unsubscribing, no callbacks will be invoked when messages are
        published to this channel. If the channel has no subscribers, this
        is a no-op (no error raised).

        Note: This removes ALL callbacks for the channel, not a specific one.
        Fine-grained unsubscription (removing a single callback) is not
        supported in this version -- it can be added later if needed.

        Args:
            channel: The channel name to unsubscribe from.

        Raises:
            MessageBusError: If the bus is not connected.
        """
        ...

    @abstractmethod
    async def request(
        self,
        channel: str,
        message: AgentMessage,
        timeout: float = 30.0,
    ) -> AgentMessage:
        """Send a request message and wait for a correlated response.

        This implements the request-response pattern over the async message
        bus. It works as follows:

        1. A ``correlation_id`` is set on the message (if not already set).
        2. The message is published to the specified channel.
        3. The caller blocks (awaits) until a response message with the
           same ``correlation_id`` arrives, or the timeout expires.

        The responder must use ``message.create_response(...)`` or manually
        set the ``correlation_id`` on the response to match the request.

        Implementation Note:
            Uses an ``asyncio.Future`` internally. The bus watches for
            incoming messages whose ``correlation_id`` matches a pending
            request and resolves the corresponding Future.

        Args:
            channel: The channel to publish the request to.
            message: The request message. If ``correlation_id`` is None,
                the ``message_id`` will be used as the correlation_id.
            timeout: Maximum seconds to wait for a response. Defaults to
                30 seconds. Raises ``MessageBusError`` on timeout.

        Returns:
            The response AgentMessage with the matching correlation_id.

        Raises:
            MessageBusError: If the response does not arrive within the
                timeout period, or if the bus is not connected.
        """
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Initialize the message bus and prepare it for use.

        This must be called before any publish/subscribe/request operations.
        For the in-memory implementation, this is essentially a no-op.
        For Redis, this establishes the connection pool and starts the
        subscriber listener loop.

        Raises:
            MessageBusError: If the connection cannot be established
                (e.g., Redis server unreachable).
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down the message bus and release all resources.

        After disconnecting:
        - All subscriptions are cleared.
        - Any pending request() calls will raise MessageBusError.
        - The bus cannot be used again until connect() is called.

        For Redis, this closes the connection pool and stops the listener.
        For in-memory, this clears all internal data structures.

        This method should be safe to call multiple times (idempotent).
        """
        ...


# =============================================================================
# In-Memory Implementation: InMemoryMessageBus
# =============================================================================
# This is the development/testing implementation of the MessageBus interface.
# All messages are delivered synchronously within the same Python process.
#
# Design Decisions:
#   - dict[str, list[MessageCallback]] for channel->callbacks mapping because
#     we need O(1) channel lookup and O(n) callback iteration per publish.
#   - asyncio.Lock for thread safety because the bus may be accessed from
#     multiple coroutines concurrently (e.g., agents publishing simultaneously).
#   - dict[str, asyncio.Future] for pending request-response correlations.
#     The correlation_id is the key, and the Future is resolved when a
#     matching response arrives.
#   - We track _published_count for testing assertions (e.g., "verify that
#     3 messages were published during this test").
#
# Limitations:
#   - Single-process only. Messages don't cross process boundaries.
#   - No message persistence. If the process dies, all messages are lost.
#   - No message ordering guarantees beyond Python's asyncio task scheduling.
#   - No backpressure. Fast publishers can overwhelm slow subscribers.
#
# These limitations are acceptable for development and testing. Production
# deployments should use RedisMessageBus (see below).
# =============================================================================
class InMemoryMessageBus(MessageBus):
    """In-memory message bus for development and testing.

    This implementation stores all subscriptions and pending requests in
    Python dictionaries. Messages are delivered by directly invoking the
    registered callbacks -- no network I/O, no serialization.

    Thread Safety:
        All mutable state is protected by an ``asyncio.Lock``. This makes
        the bus safe to use from multiple concurrent coroutines (but NOT
        from multiple OS threads -- use Redis for multi-threaded scenarios).

    Testing Support:
        The ``published_count`` property tracks how many messages have been
        published since the bus was created (or last connected). This is
        useful for test assertions::

            bus = InMemoryMessageBus()
            await bus.connect()
            assert bus.published_count == 0
            await bus.publish("channel", msg)
            assert bus.published_count == 1

    Attributes:
        _subscriptions: Maps channel names to lists of registered callbacks.
            Example: {"conductor:agent:coding-01": [handler1, handler2]}
        _pending_requests: Maps correlation_id to asyncio.Future for the
            request-response pattern. When a response with a matching
            correlation_id arrives, the Future is resolved.
        _lock: asyncio.Lock protecting all mutable state from concurrent
            access by multiple coroutines.
        _connected: Whether the bus has been connected (ready for use).
        _published_count: Running count of published messages for testing.
        _logger: Structured logger bound with component context.

    Example:
        >>> bus = InMemoryMessageBus()
        >>> await bus.connect()
        >>>
        >>> received = []
        >>> async def handler(msg):
        ...     received.append(msg)
        >>> await bus.subscribe("test-channel", handler)
        >>>
        >>> msg = AgentMessage(
        ...     message_type=MessageType.STATUS_UPDATE,
        ...     sender_id="agent-1",
        ... )
        >>> await bus.publish("test-channel", msg)
        >>> assert len(received) == 1
        >>>
        >>> await bus.disconnect()
    """

    def __init__(self) -> None:
        """Initialize the in-memory message bus.

        Sets up internal data structures but does NOT connect the bus.
        You must call ``await bus.connect()`` before using publish/subscribe.
        """
        # -----------------------------------------------------------------
        # Channel -> Callbacks mapping
        # -----------------------------------------------------------------
        # Each channel can have zero or more callbacks registered.
        # When a message is published to a channel, ALL callbacks for that
        # channel are invoked concurrently.
        # -----------------------------------------------------------------
        self._subscriptions: dict[str, list[MessageCallback]] = {}

        # -----------------------------------------------------------------
        # Pending Request-Response Futures
        # -----------------------------------------------------------------
        # When request() is called, we create a Future keyed by the
        # correlation_id. When a response arrives with a matching
        # correlation_id (detected in publish()), we resolve the Future.
        # This allows request() to await the Future and get the response.
        # -----------------------------------------------------------------
        self._pending_requests: dict[str, asyncio.Future[AgentMessage]] = {}

        # -----------------------------------------------------------------
        # Concurrency Lock
        # -----------------------------------------------------------------
        # asyncio.Lock is a coroutine-safe mutex. We acquire it before
        # modifying _subscriptions or _pending_requests to prevent race
        # conditions when multiple coroutines publish/subscribe concurrently.
        #
        # Important: asyncio.Lock is NOT thread-safe. It protects against
        # concurrent coroutine access within a single event loop. For
        # multi-threaded access, use RedisMessageBus instead.
        # -----------------------------------------------------------------
        self._lock: asyncio.Lock = asyncio.Lock()

        # -----------------------------------------------------------------
        # Connection State
        # -----------------------------------------------------------------
        # Tracks whether connect() has been called. Operations will raise
        # MessageBusError if the bus is not connected.
        # -----------------------------------------------------------------
        self._connected: bool = False

        # -----------------------------------------------------------------
        # Published Message Counter (for testing)
        # -----------------------------------------------------------------
        # Tracks the total number of messages published through this bus.
        # Reset to 0 on connect(). Useful in tests:
        #   assert bus.published_count == expected_count
        # -----------------------------------------------------------------
        self._published_count: int = 0

        # -----------------------------------------------------------------
        # Logger with component context
        # -----------------------------------------------------------------
        # Every log line from this class will include:
        #   {"component": "message_bus", "impl": "in_memory"}
        # This makes it easy to filter message bus logs in production.
        # -----------------------------------------------------------------
        self._logger = logger.bind(component="message_bus", impl="in_memory")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def published_count(self) -> int:
        """Get the total number of messages published since connect().

        This counter is primarily for testing -- it lets tests verify that
        the expected number of messages flowed through the bus.

        Returns:
            The count of messages published via ``publish()``.
        """
        return self._published_count

    @property
    def is_connected(self) -> bool:
        """Check whether the bus is connected and ready for use.

        Returns:
            True if ``connect()`` has been called and ``disconnect()`` has not.
        """
        return self._connected

    # =========================================================================
    # Connection Lifecycle
    # =========================================================================

    async def connect(self) -> None:
        """Initialize the in-memory message bus.

        For the in-memory implementation, this simply sets the connected flag
        and resets internal state. There are no external resources to connect to.

        This is idempotent -- calling connect() on an already-connected bus
        resets the internal state (clears subscriptions, pending requests,
        and the published count).
        """
        async with self._lock:
            # Clear all state to start fresh. This ensures that reconnecting
            # after a disconnect does not retain stale subscriptions or
            # orphaned pending requests from the previous session.
            self._subscriptions.clear()
            self._pending_requests.clear()
            self._published_count = 0
            self._connected = True

        self._logger.info("message_bus_connected")

    async def disconnect(self) -> None:
        """Shut down the in-memory message bus.

        Clears all subscriptions and cancels any pending request-response
        Futures (they will raise MessageBusError when awaited).

        This is idempotent -- calling disconnect() on an already-disconnected
        bus is a safe no-op.
        """
        async with self._lock:
            # Cancel all pending request-response Futures so that any
            # coroutines awaiting them get an immediate error rather than
            # hanging forever. This is important for clean shutdown: if
            # an agent is waiting for a response when the bus disconnects,
            # it should get a clear error, not a deadlock.
            for correlation_id, future in self._pending_requests.items():
                if not future.done():
                    future.set_exception(
                        MessageBusError(
                            message=(
                                "Message bus disconnected while waiting "
                                "for response"
                            ),
                            error_code="BUS_DISCONNECTED",
                            details={"correlation_id": correlation_id},
                        )
                    )

            # Clear all internal state to free memory and prevent stale
            # references from being used after reconnection.
            self._subscriptions.clear()
            self._pending_requests.clear()
            self._connected = False

        self._logger.info("message_bus_disconnected")

    # =========================================================================
    # Core Operations
    # =========================================================================

    async def publish(self, channel: str, message: AgentMessage) -> None:
        """Publish a message to all subscribers on a channel.

        This method performs the following steps:
        1. Checks that the bus is connected.
        2. Checks that the message has not expired (TTL).
        3. Checks if the message resolves a pending request-response Future
           (by matching the ``correlation_id``).
        4. Invokes all registered callbacks for the channel concurrently.
        5. Increments the published message counter.

        Callback errors are caught and logged -- they do NOT propagate to
        the publisher. This design prevents a buggy subscriber from blocking
        the entire message flow.

        Args:
            channel: The channel name to publish to.
            message: The AgentMessage to deliver.

        Raises:
            MessageBusError: If the bus is not connected.
        """
        # --- Guard: Ensure the bus is connected ---
        self._ensure_connected()

        # --- Guard: Discard expired messages ---
        # Messages with a TTL that has been exceeded are silently dropped.
        # This prevents stale messages from being processed after long delays
        # (e.g., if the system was paused or a consumer was slow).
        if message.is_expired():
            self._logger.warning(
                "message_expired_dropping",
                message_id=message.message_id,
                channel=channel,
                ttl_seconds=message.ttl_seconds,
            )
            return

        self._logger.debug(
            "message_publishing",
            channel=channel,
            message_id=message.message_id,
            message_type=message.message_type.value,
            sender_id=message.sender_id,
        )

        async with self._lock:
            # --- Step 1: Check for pending request-response Futures ---
            # If this message has a correlation_id that matches a pending
            # request(), resolve the Future so the requester gets the response.
            # This is the key mechanism for the request-response pattern:
            # publish() acts as both the delivery mechanism AND the response
            # resolver.
            if (
                message.correlation_id
                and message.correlation_id in self._pending_requests
            ):
                future = self._pending_requests.pop(message.correlation_id)
                if not future.done():
                    future.set_result(message)
                    self._logger.debug(
                        "request_response_resolved",
                        correlation_id=message.correlation_id,
                        message_id=message.message_id,
                    )

            # --- Step 2: Get the list of callbacks for this channel ---
            # We copy the list to avoid issues if a callback modifies
            # subscriptions during iteration (e.g., a callback that
            # unsubscribes itself). This is defensive programming.
            callbacks = list(self._subscriptions.get(channel, []))

            # --- Step 3: Increment the published count ---
            # This is done inside the lock to ensure the counter is accurate
            # even when multiple coroutines publish concurrently.
            self._published_count += 1

        # --- Step 4: Invoke all callbacks concurrently ---
        # IMPORTANT: We release the lock BEFORE invoking callbacks to avoid
        # holding the lock for the duration of callback execution. Callbacks
        # may do slow I/O (like calling an LLM) and we don't want to block
        # other publishers during that time.
        if callbacks:
            # Create tasks for all callbacks and run them concurrently.
            # We use asyncio.gather with return_exceptions=True so that
            # one failing callback doesn't prevent others from running.
            results = await asyncio.gather(
                *(self._invoke_callback(cb, message) for cb in callbacks),
                return_exceptions=True,
            )

            # Log any callback errors (but don't propagate them to the
            # publisher). This is a critical design decision: a buggy
            # subscriber should NOT prevent other subscribers from receiving
            # messages, and should NOT cause the publisher to see an error.
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self._logger.error(
                        "subscriber_callback_error",
                        channel=channel,
                        message_id=message.message_id,
                        error=str(result),
                        callback_index=i,
                    )

        self._logger.debug(
            "message_published",
            channel=channel,
            message_id=message.message_id,
            subscriber_count=len(callbacks),
        )

    async def subscribe(
        self, channel: str, callback: MessageCallback
    ) -> None:
        """Register a callback to receive messages on a channel.

        The callback will be invoked every time a message is published to
        the specified channel. Multiple callbacks can be registered on the
        same channel -- each one will be invoked independently.

        Args:
            channel: The channel name to subscribe to.
            callback: An async function ``(AgentMessage) -> None``.

        Raises:
            MessageBusError: If the bus is not connected.
        """
        self._ensure_connected()

        async with self._lock:
            # Create the callback list for this channel if it doesn't exist.
            # We check explicitly rather than using defaultdict because we
            # want to keep _subscriptions as a plain dict (easier to reason
            # about, and .get() with default works fine for publish()).
            if channel not in self._subscriptions:
                self._subscriptions[channel] = []

            self._subscriptions[channel].append(callback)

        self._logger.debug(
            "channel_subscribed",
            channel=channel,
            total_subscribers=len(self._subscriptions.get(channel, [])),
        )

    async def unsubscribe(self, channel: str) -> None:
        """Remove ALL callbacks registered for a channel.

        After this call, messages published to the channel will have no
        subscribers (they are silently dropped). This is a no-op if the
        channel has no subscribers.

        Args:
            channel: The channel name to unsubscribe from.

        Raises:
            MessageBusError: If the bus is not connected.
        """
        self._ensure_connected()

        async with self._lock:
            # Remove the channel entirely from the subscriptions dict.
            # pop() with a default avoids KeyError if the channel was never
            # subscribed to (makes this method idempotent and safe).
            removed = self._subscriptions.pop(channel, [])

        self._logger.debug(
            "channel_unsubscribed",
            channel=channel,
            removed_callbacks=len(removed),
        )

    async def request(
        self,
        channel: str,
        message: AgentMessage,
        timeout: float = 30.0,
    ) -> AgentMessage:
        """Send a request and wait for a correlated response.

        This implements the request-response pattern over the pub/sub bus.
        It works as follows:

        1. If the message doesn't have a ``correlation_id``, we set it to the
           ``message_id`` (so the responder can use ``create_response()``).
        2. We create an ``asyncio.Future`` keyed by the correlation_id.
        3. We publish the message to the channel.
        4. We await the Future with a timeout.
        5. When a response with the matching correlation_id is published
           (by the responder), the ``publish()`` method resolves the Future.
        6. We return the response message.

        If the timeout expires before a response arrives, we clean up the
        Future and raise MessageBusError.

        Args:
            channel: The channel to send the request to.
            message: The request message.
            timeout: Maximum seconds to wait for a response (default: 30s).

        Returns:
            The response AgentMessage with matching correlation_id.

        Raises:
            MessageBusError: If no response arrives within the timeout,
                or if the bus is not connected.
        """
        self._ensure_connected()

        # --- Step 1: Ensure the message has a correlation_id ---
        # The correlation_id links the request to its response. If the
        # caller didn't set one, we use the message_id as the correlation_id.
        # This is safe because message_id is always a unique UUID4.
        correlation_id = message.correlation_id or message.message_id
        if message.correlation_id is None:
            # Create a copy of the message with the correlation_id set.
            # We don't modify the original message to respect the
            # immutability convention used throughout ConductorAI models.
            message = message.model_copy(
                update={"correlation_id": correlation_id}
            )

        self._logger.debug(
            "request_sending",
            channel=channel,
            correlation_id=correlation_id,
            message_id=message.message_id,
            timeout=timeout,
        )

        # --- Step 2: Create a Future for the response ---
        # asyncio.Future is a low-level awaitable that represents a value
        # that will be available in the future. We store it in
        # _pending_requests so that publish() can resolve it when the
        # response arrives (matched by correlation_id).
        loop = asyncio.get_running_loop()
        future: asyncio.Future[AgentMessage] = loop.create_future()

        async with self._lock:
            self._pending_requests[correlation_id] = future

        # --- Step 3: Publish the request message ---
        # The responder (usually an agent) will receive this message via
        # their subscribe() callback, process it, and publish a response
        # with the same correlation_id back to the bus.
        await self.publish(channel, message)

        # --- Step 4: Await the response with timeout ---
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            self._logger.debug(
                "request_response_received",
                correlation_id=correlation_id,
                response_message_id=response.message_id,
            )
            return response

        except asyncio.TimeoutError:
            # --- Timeout: Clean up the pending Future ---
            # Remove the Future from _pending_requests so it doesn't leak
            # memory. Then raise a descriptive MessageBusError so the caller
            # knows what happened and can decide whether to retry.
            async with self._lock:
                self._pending_requests.pop(correlation_id, None)

            self._logger.warning(
                "request_timeout",
                channel=channel,
                correlation_id=correlation_id,
                timeout=timeout,
            )
            raise MessageBusError(
                message=(
                    f"Request timed out after {timeout}s waiting for response"
                ),
                error_code="REQUEST_TIMEOUT",
                details={
                    "channel": channel,
                    "correlation_id": correlation_id,
                    "timeout_seconds": timeout,
                },
            )

    # =========================================================================
    # Internal Helper Methods
    # =========================================================================

    def _ensure_connected(self) -> None:
        """Verify that the bus is connected before performing operations.

        This is a guard method called at the top of every public operation
        (publish, subscribe, unsubscribe, request). It raises a clear error
        message if someone tries to use the bus before calling connect().

        Raises:
            MessageBusError: If the bus has not been connected.
        """
        if not self._connected:
            raise MessageBusError(
                message="Message bus is not connected. Call connect() first.",
                error_code="BUS_NOT_CONNECTED",
            )

    async def _invoke_callback(
        self, callback: MessageCallback, message: AgentMessage
    ) -> None:
        """Safely invoke a single subscriber callback.

        Wraps the callback invocation in a try-except to prevent one
        failing callback from affecting other subscribers or the publisher.
        Errors are logged with full context for debugging.

        Args:
            callback: The async callback function to invoke.
            message: The AgentMessage to pass to the callback.

        Raises:
            Exception: Re-raises the original exception so that
                ``asyncio.gather(return_exceptions=True)`` can capture it.
                The caller (``publish()``) handles logging.
        """
        try:
            await callback(message)
        except Exception as exc:
            # Log the error with structured context for debugging.
            # We include the message_id and type so operators can trace
            # which message caused the callback failure.
            self._logger.error(
                "callback_invocation_error",
                message_id=message.message_id,
                message_type=message.message_type.value,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            # Re-raise so asyncio.gather(return_exceptions=True) can
            # capture the exception. The publisher will log it but not
            # propagate it to the calling code.
            raise


# =============================================================================
# Redis Implementation (Stub): RedisMessageBus
# =============================================================================
# This is a skeleton implementation for production use with Redis Pub/Sub.
# It establishes the class structure and documents the intended behavior,
# but the actual Redis integration is deferred to a later implementation
# phase (Day 7+).
#
# Why Redis for Production?
#   1. Cross-process communication: Multiple ConductorAI worker processes
#      can share a single message bus via Redis.
#   2. Persistence: Redis can persist messages to disk (if configured with
#      AOF or RDB snapshotting).
#   3. Scalability: Redis handles thousands of concurrent pub/sub channels
#      and subscribers with low latency.
#   4. Reliability: The redis-py library provides built-in connection
#      pooling and automatic reconnection.
#
# Implementation Strategy (for future development):
#   - Use ``redis.asyncio`` (async Redis client) for non-blocking I/O.
#   - Messages are serialized to JSON via Pydantic's ``model_dump_json()``.
#   - Messages are deserialized via ``AgentMessage.model_validate_json()``.
#   - Each channel maps to a Redis Pub/Sub channel with the same name.
#   - Request-response uses a combination of Pub/Sub and Redis lists
#     (BLPOP on a temporary response queue) to ensure the response is not
#     lost if the requester momentarily disconnects.
#   - A background listener task runs in an ``asyncio.Task``, reading
#     messages from Redis and dispatching them to local callbacks.
# =============================================================================
class RedisMessageBus(MessageBus):
    """Redis-backed message bus for production deployments.

    This implementation uses Redis Pub/Sub for cross-process agent
    communication. It is suitable for production environments where
    multiple worker processes need to share a single message bus.

    .. note::
        This is currently a **stub implementation**. All methods raise
        ``NotImplementedError``. The full implementation will use
        ``redis.asyncio`` for async Redis operations.

    Configuration:
        Requires a Redis connection URL with the standard format::

            redis://[:password@]host[:port][/db]

        Example: ``redis://localhost:6379/0``

    TODO:
        - [ ] Implement connect() with redis.asyncio connection pool
        - [ ] Implement publish() with JSON serialization via model_dump_json()
        - [ ] Implement subscribe() with Redis Pub/Sub listener loop
        - [ ] Implement unsubscribe() with Redis UNSUBSCRIBE command
        - [ ] Implement request() with Redis lists for response queues
        - [ ] Implement disconnect() with connection pool cleanup
        - [ ] Add connection health checks and automatic reconnection
        - [ ] Add message serialization/deserialization with schema validation
        - [ ] Add metrics collection (message throughput, latency)
        - [ ] Add dead letter queue support for undeliverable messages
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        """Initialize the Redis message bus.

        Args:
            redis_url: Redis connection URL in the format:
                ``redis://[:password@]host[:port][/db]``
                Defaults to localhost on the default Redis port, database 0.
        """
        # Store the Redis connection URL for use in connect().
        self._redis_url: str = redis_url

        # -----------------------------------------------------------------
        # Placeholder for the async Redis client instance.
        # Will be initialized in connect() as:
        #   self._redis_client = redis.asyncio.from_url(self._redis_url)
        # -----------------------------------------------------------------
        # TODO: Type this as redis.asyncio.Redis once redis-py is added
        #       as a project dependency.
        self._redis_client: Any = None

        # -----------------------------------------------------------------
        # Placeholder for the Redis Pub/Sub subscriber object.
        # Will be initialized in connect() as:
        #   self._pubsub = self._redis_client.pubsub()
        # -----------------------------------------------------------------
        # TODO: Type this as redis.asyncio.client.PubSub
        self._pubsub: Any = None

        # -----------------------------------------------------------------
        # Local callback registry.
        # Even with Redis, we need a local mapping of channel -> callbacks
        # because Redis Pub/Sub delivers raw bytes. We deserialize the
        # message and then dispatch to local callbacks.
        # -----------------------------------------------------------------
        self._subscriptions: dict[str, list[MessageCallback]] = {}

        # -----------------------------------------------------------------
        # Pending request-response Futures (same pattern as InMemory).
        # -----------------------------------------------------------------
        self._pending_requests: dict[str, asyncio.Future[AgentMessage]] = {}

        # -----------------------------------------------------------------
        # Background listener task handle.
        # This task continuously reads from Redis Pub/Sub and dispatches
        # messages to local callbacks.
        # -----------------------------------------------------------------
        self._listener_task: Optional[asyncio.Task[None]] = None

        # -----------------------------------------------------------------
        # Connection state flag.
        # -----------------------------------------------------------------
        self._connected: bool = False

        # -----------------------------------------------------------------
        # Published message counter for monitoring.
        # -----------------------------------------------------------------
        self._published_count: int = 0

        # -----------------------------------------------------------------
        # Logger with Redis-specific context for log filtering.
        # -----------------------------------------------------------------
        self._logger = logger.bind(
            component="message_bus",
            impl="redis",
            redis_url=redis_url,
        )

    async def publish(self, channel: str, message: AgentMessage) -> None:
        """Publish a message to a Redis Pub/Sub channel.

        TODO: Implement with:
            1. Serialize message to JSON: ``message.model_dump_json()``
            2. Publish to Redis: ``await self._redis_client.publish(channel, json_bytes)``
            3. Check for pending request-response Futures (same as InMemory)
            4. Handle connection errors with retry logic
            5. Increment ``_published_count``

        Raises:
            NotImplementedError: Always (stub implementation).
        """
        raise NotImplementedError(
            "RedisMessageBus.publish() is not yet implemented. "
            "Use InMemoryMessageBus for development and testing."
        )

    async def subscribe(
        self, channel: str, callback: MessageCallback
    ) -> None:
        """Subscribe to a Redis Pub/Sub channel.

        TODO: Implement with:
            1. Register callback in local ``_subscriptions`` mapping
            2. Subscribe to Redis channel: ``await self._pubsub.subscribe(channel)``
            3. Start the background listener task if not already running

        Raises:
            NotImplementedError: Always (stub implementation).
        """
        raise NotImplementedError(
            "RedisMessageBus.subscribe() is not yet implemented. "
            "Use InMemoryMessageBus for development and testing."
        )

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a Redis Pub/Sub channel.

        TODO: Implement with:
            1. Remove callbacks from local ``_subscriptions`` mapping
            2. Unsubscribe from Redis: ``await self._pubsub.unsubscribe(channel)``

        Raises:
            NotImplementedError: Always (stub implementation).
        """
        raise NotImplementedError(
            "RedisMessageBus.unsubscribe() is not yet implemented. "
            "Use InMemoryMessageBus for development and testing."
        )

    async def request(
        self,
        channel: str,
        message: AgentMessage,
        timeout: float = 30.0,
    ) -> AgentMessage:
        """Send a request via Redis and wait for a correlated response.

        TODO: Implement with:
            1. Create a temporary response channel:
               ``"conductor:response:{correlation_id}"``
            2. Subscribe to the response channel
            3. Publish the request to the target channel
            4. Wait for a message on the response channel (with timeout)
            5. Clean up the temporary response channel subscription

        Raises:
            NotImplementedError: Always (stub implementation).
        """
        raise NotImplementedError(
            "RedisMessageBus.request() is not yet implemented. "
            "Use InMemoryMessageBus for development and testing."
        )

    async def connect(self) -> None:
        """Establish a connection to the Redis server.

        TODO: Implement with:
            1. Create async Redis client:
               ``redis.asyncio.from_url(self._redis_url)``
            2. Verify connectivity: ``await self._redis_client.ping()``
            3. Create PubSub object: ``self._pubsub = self._redis_client.pubsub()``
            4. Start the background listener task for incoming messages
            5. Set ``self._connected = True``

        Raises:
            NotImplementedError: Always (stub implementation).
        """
        raise NotImplementedError(
            "RedisMessageBus.connect() is not yet implemented. "
            "Use InMemoryMessageBus for development and testing."
        )

    async def disconnect(self) -> None:
        """Disconnect from the Redis server and clean up resources.

        TODO: Implement with:
            1. Cancel the background listener task
            2. Unsubscribe from all channels via Redis UNSUBSCRIBE
            3. Close the PubSub object: ``await self._pubsub.close()``
            4. Close the Redis connection pool:
               ``await self._redis_client.close()``
            5. Cancel all pending request-response Futures
            6. Clear local state and set ``self._connected = False``

        Raises:
            NotImplementedError: Always (stub implementation).
        """
        raise NotImplementedError(
            "RedisMessageBus.disconnect() is not yet implemented. "
            "Use InMemoryMessageBus for development and testing."
        )
