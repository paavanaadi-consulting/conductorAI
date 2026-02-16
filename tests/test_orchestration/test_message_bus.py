"""
Tests for conductor.orchestration.message_bus — InMemoryMessageBus
====================================================================

These tests verify the InMemoryMessageBus implementation, which is the
development/testing message bus for ConductorAI.

What's Being Tested:
    - Pub/Sub pattern:        publish → subscribers receive messages
    - Request-Response:       request() waits for correlated response
    - Subscription lifecycle: subscribe, unsubscribe, callback management
    - Error handling:         timeouts, no-subscriber scenarios
    - Metrics:                published_message_count tracking

All tests are async (pytest-asyncio with asyncio_mode=auto).
No external dependencies required (pure in-memory).

Architecture Context:
    The Message Bus is the communication backbone of ConductorAI.
    It enables agents to communicate without direct coupling:

        Agent A ──publish──→ [Message Bus] ──callback──→ Agent B
                                 │
                                 └──callback──→ Agent C

    Channels follow the naming convention:
        "conductor:agent:{agent_id}"      → Direct message
        "conductor:broadcast"             → Broadcast to all
        "conductor:phase:{phase_name}"    → Phase-level messages
"""

import asyncio
from typing import Any

import pytest

from conductor.core.enums import MessageType, Priority
from conductor.core.exceptions import MessageBusError
from conductor.core.messages import AgentMessage
from conductor.orchestration.message_bus import InMemoryMessageBus, MessageBus


# =============================================================================
# Helper: Create Test Messages
# =============================================================================
# This helper creates minimal AgentMessage instances for testing.
# We use STATUS_UPDATE as the default type because it's the simplest
# (doesn't require specific payload structure).
# =============================================================================
def _make_message(
    msg_type: MessageType = MessageType.STATUS_UPDATE,
    sender: str = "test",
) -> AgentMessage:
    """Create a minimal AgentMessage for testing.

    Args:
        msg_type: The message type to use (default: STATUS_UPDATE).
        sender: The sender_id to use (default: "test").

    Returns:
        An AgentMessage instance with the specified type and sender.
    """
    return AgentMessage(message_type=msg_type, sender_id=sender)


# =============================================================================
# Test Class: InMemoryMessageBus
# =============================================================================
class TestInMemoryMessageBus:
    """Tests for the InMemoryMessageBus implementation.

    Each test creates a fresh bus instance to ensure isolation.
    Tests cover pub/sub, request-response, subscription management,
    and metric tracking.
    """

    # -------------------------------------------------------------------------
    # Test: Basic Pub/Sub
    # -------------------------------------------------------------------------

    async def test_publish_subscribe(self) -> None:
        """Subscribing to a channel and publishing should deliver the message.

        Scenario:
            1. Create a bus and connect
            2. Subscribe to "conductor:test" with a callback that stores messages
            3. Publish a STATUS_UPDATE message to "conductor:test"
            4. Verify the callback received exactly one message
            5. Verify the received message matches the published one

        This is the fundamental pub/sub test — the building block for all
        agent-to-agent communication in ConductorAI.
        """
        bus = InMemoryMessageBus()
        await bus.connect()

        # We'll collect received messages in this list.
        # The callback appends each message it receives.
        received: list[AgentMessage] = []

        async def callback(msg: AgentMessage) -> None:
            received.append(msg)

        # Subscribe to the test channel
        await bus.subscribe("conductor:test", callback)

        # Create and publish a test message
        message = _make_message(sender="agent-01")
        await bus.publish("conductor:test", message)

        # Verify the callback was invoked with the correct message
        assert len(received) == 1, "Callback should have received exactly one message"
        assert received[0].message_id == message.message_id, (
            "Received message should have the same message_id as published"
        )
        assert received[0].sender_id == "agent-01", (
            "Received message should preserve the sender_id"
        )
        assert received[0].message_type == MessageType.STATUS_UPDATE, (
            "Received message should preserve the message_type"
        )

        await bus.disconnect()

    async def test_publish_no_subscribers(self) -> None:
        """Publishing to a channel with no subscribers should NOT raise an error.

        Scenario:
            1. Create a bus and connect
            2. Publish a message to "conductor:empty" (no subscribers)
            3. Verify no exception is raised
            4. Verify the message count still increments

        This is important because agents may publish status updates even
        when no one is listening yet (e.g., during system startup).
        """
        bus = InMemoryMessageBus()
        await bus.connect()

        # This should not raise — fire-and-forget semantics
        message = _make_message(sender="lonely-agent")
        await bus.publish("conductor:empty", message)

        # The message was still "published" (counted), just not delivered
        assert bus.published_message_count == 1, (
            "Published count should increment even with no subscribers"
        )

        await bus.disconnect()

    async def test_multiple_subscribers(self) -> None:
        """Multiple callbacks on the same channel should all receive the message.

        Scenario:
            1. Subscribe three different callbacks to "conductor:broadcast"
            2. Publish one message
            3. Verify ALL three callbacks received the message

        This validates the fan-out pattern used for broadcast messages
        (e.g., status updates sent to all agents on conductor:broadcast).
        """
        bus = InMemoryMessageBus()
        await bus.connect()

        # Three separate receivers, each collecting their own messages
        received_a: list[AgentMessage] = []
        received_b: list[AgentMessage] = []
        received_c: list[AgentMessage] = []

        async def callback_a(msg: AgentMessage) -> None:
            received_a.append(msg)

        async def callback_b(msg: AgentMessage) -> None:
            received_b.append(msg)

        async def callback_c(msg: AgentMessage) -> None:
            received_c.append(msg)

        # All three subscribe to the same channel
        await bus.subscribe("conductor:broadcast", callback_a)
        await bus.subscribe("conductor:broadcast", callback_b)
        await bus.subscribe("conductor:broadcast", callback_c)

        # Publish one message
        message = _make_message(sender="coordinator")
        await bus.publish("conductor:broadcast", message)

        # All three should have received the message
        assert len(received_a) == 1, "Callback A should have received the message"
        assert len(received_b) == 1, "Callback B should have received the message"
        assert len(received_c) == 1, "Callback C should have received the message"

        # All received the SAME message (same message_id)
        assert received_a[0].message_id == message.message_id
        assert received_b[0].message_id == message.message_id
        assert received_c[0].message_id == message.message_id

        await bus.disconnect()

    # -------------------------------------------------------------------------
    # Test: Unsubscribe
    # -------------------------------------------------------------------------

    async def test_unsubscribe(self) -> None:
        """After unsubscribe, the callback should NOT be called for new messages.

        Scenario:
            1. Subscribe a callback to "conductor:test"
            2. Publish a message — callback receives it (1 message)
            3. Unsubscribe the callback
            4. Publish another message — callback should NOT receive it
            5. Verify the callback still has only 1 message (from step 2)

        This ensures that unsubscribe truly removes the callback from the
        channel's subscriber list. Agents use this when shutting down to
        stop receiving messages.
        """
        bus = InMemoryMessageBus()
        await bus.connect()

        received: list[AgentMessage] = []

        async def callback(msg: AgentMessage) -> None:
            received.append(msg)

        # Subscribe and receive one message
        sub_id = await bus.subscribe("conductor:test", callback)
        await bus.publish("conductor:test", _make_message(sender="before"))
        assert len(received) == 1, "Should have received the first message"

        # Unsubscribe
        await bus.unsubscribe(sub_id)

        # Publish again — callback should NOT fire
        await bus.publish("conductor:test", _make_message(sender="after"))
        assert len(received) == 1, (
            "Should still have only 1 message — the post-unsubscribe "
            "message should not have been delivered"
        )

        await bus.disconnect()

    # -------------------------------------------------------------------------
    # Test: Multiple Channels (Isolation)
    # -------------------------------------------------------------------------

    async def test_multiple_channels(self) -> None:
        """Subscribers on different channels should only get their own messages.

        Scenario:
            1. Subscribe callback_a to "conductor:agent:agent-a"
            2. Subscribe callback_b to "conductor:agent:agent-b"
            3. Publish a message to "conductor:agent:agent-a"
            4. Verify callback_a received it but callback_b did NOT
            5. Publish a message to "conductor:agent:agent-b"
            6. Verify callback_b received it but callback_a still has only 1

        This validates channel isolation — critical for directing messages
        to specific agents (direct messaging pattern).
        """
        bus = InMemoryMessageBus()
        await bus.connect()

        received_a: list[AgentMessage] = []
        received_b: list[AgentMessage] = []

        async def callback_a(msg: AgentMessage) -> None:
            received_a.append(msg)

        async def callback_b(msg: AgentMessage) -> None:
            received_b.append(msg)

        # Subscribe to different channels
        await bus.subscribe("conductor:agent:agent-a", callback_a)
        await bus.subscribe("conductor:agent:agent-b", callback_b)

        # Publish to channel A only
        msg_for_a = _make_message(sender="coordinator")
        await bus.publish("conductor:agent:agent-a", msg_for_a)

        assert len(received_a) == 1, "Callback A should have received the message"
        assert len(received_b) == 0, (
            "Callback B should NOT have received a message published to channel A"
        )

        # Publish to channel B only
        msg_for_b = _make_message(sender="coordinator")
        await bus.publish("conductor:agent:agent-b", msg_for_b)

        assert len(received_a) == 1, (
            "Callback A should still have only 1 message (the one from channel A)"
        )
        assert len(received_b) == 1, "Callback B should have received the message"

        await bus.disconnect()

    # -------------------------------------------------------------------------
    # Test: Request-Response Pattern
    # -------------------------------------------------------------------------

    async def test_request_response(self) -> None:
        """request() should return the correlated response message.

        Scenario:
            1. Subscribe a handler to "conductor:agent:coding-01" that:
               a. Receives a TASK_ASSIGNMENT message
               b. Creates a response using message.create_response()
               c. Publishes the response back to the request sender's channel
            2. Call request() with a TASK_ASSIGNMENT message
            3. Verify we get back the correct response

        This is the synchronous-style communication pattern used when the
        Coordinator sends a task to an agent and waits for the result.

        Flow:
            request()
              → publish(TASK_ASSIGNMENT) to agent channel
              → handler receives it, creates response with create_response()
              → handler publishes response (correlation_id matches)
              → request() Future is resolved
              → request() returns the response
        """
        bus = InMemoryMessageBus()
        await bus.connect()

        # Handler simulates an agent processing a task assignment.
        # It creates a response using the AgentMessage.create_response() method,
        # which automatically sets the correlation_id to link request and response.
        async def handler(msg: AgentMessage) -> None:
            # Create a response linked to the original message
            response = msg.create_response(
                sender_id="coding-01",
                message_type=MessageType.TASK_RESULT,
                payload={"result": "code generated"},
            )
            # Publish the response — the bus matches correlation_id
            # and resolves the pending Future in request()
            await bus.publish("conductor:agent:coordinator", response)

        # Subscribe the handler to the agent's channel
        await bus.subscribe("conductor:agent:coding-01", handler)

        # Create a request message (Coordinator → Agent)
        request_msg = AgentMessage(
            message_type=MessageType.TASK_ASSIGNMENT,
            sender_id="coordinator",
            recipient_id="coding-01",
            payload={"task": "generate code"},
        )

        # Send the request and wait for the response
        response = await bus.request(
            "conductor:agent:coding-01",
            request_msg,
            timeout=5.0,
        )

        # Verify the response is correctly correlated
        assert response.message_type == MessageType.TASK_RESULT, (
            "Response should be a TASK_RESULT message"
        )
        assert response.sender_id == "coding-01", (
            "Response should come from the agent that handled the request"
        )
        assert response.payload["result"] == "code generated", (
            "Response payload should contain the agent's output"
        )
        assert response.correlation_id == request_msg.message_id, (
            "Response correlation_id should match the request's message_id, "
            "linking the two messages together"
        )

        await bus.disconnect()

    async def test_request_timeout(self) -> None:
        """request() should raise MessageBusError when no response arrives in time.

        Scenario:
            1. Call request() with a very short timeout (0.05 seconds)
            2. No subscriber exists to respond
            3. Verify MessageBusError is raised with REQUEST_TIMEOUT error code

        This prevents the system from hanging indefinitely when an agent
        is down or fails to respond. The Coordinator can then retry or
        escalate the task.
        """
        bus = InMemoryMessageBus()
        await bus.connect()

        # No subscriber is registered — nobody will respond
        request_msg = _make_message(
            msg_type=MessageType.TASK_ASSIGNMENT,
            sender="coordinator",
        )

        # request() should raise after the timeout elapses
        with pytest.raises(MessageBusError) as exc_info:
            await bus.request(
                "conductor:agent:missing-agent",
                request_msg,
                timeout=0.05,  # 50ms — very short timeout for fast tests
            )

        # Verify the error has the correct error code
        assert exc_info.value.error_code == "REQUEST_TIMEOUT", (
            "Error should have REQUEST_TIMEOUT code for programmatic handling"
        )
        # Verify error details include useful debugging context
        assert "timeout" in exc_info.value.message.lower(), (
            "Error message should mention 'timeout' for human readability"
        )

        await bus.disconnect()

    # -------------------------------------------------------------------------
    # Test: Connect / Disconnect Lifecycle
    # -------------------------------------------------------------------------

    async def test_connect_disconnect(self) -> None:
        """connect() and disconnect() should manage the bus lifecycle cleanly.

        Scenario:
            1. Create a bus — starts disconnected
            2. Connect — bus is ready
            3. Subscribe and publish to verify it works
            4. Disconnect — cleans up subscriptions
            5. Verify subscriptions are cleared

        This tests the infrastructure lifecycle that production code
        uses during application startup and shutdown.
        """
        bus = InMemoryMessageBus()

        # Bus starts in a clean state
        assert bus.published_message_count == 0, (
            "Fresh bus should have zero published messages"
        )

        # Connect the bus
        await bus.connect()

        # Use the bus (subscribe + publish)
        received: list[AgentMessage] = []

        async def callback(msg: AgentMessage) -> None:
            received.append(msg)

        await bus.subscribe("conductor:lifecycle-test", callback)
        await bus.publish("conductor:lifecycle-test", _make_message())
        assert len(received) == 1, "Message should be delivered while connected"

        # Disconnect cleans up everything
        await bus.disconnect()

        # After disconnect, internal state should be cleared.
        # We verify this by checking the published_message_count is preserved
        # (it's a counter, not a subscription) but subscriptions are gone.
        # A fresh connect + publish should NOT trigger the old callback.
        await bus.connect()
        await bus.publish("conductor:lifecycle-test", _make_message())
        assert len(received) == 1, (
            "Old callback should NOT fire after disconnect — "
            "subscriptions should have been cleared"
        )

        await bus.disconnect()

    # -------------------------------------------------------------------------
    # Test: Message Count Tracking
    # -------------------------------------------------------------------------

    async def test_message_count_tracking(self) -> None:
        """published_message_count should increment with each publish call.

        Scenario:
            1. Create a bus — count starts at 0
            2. Publish 3 messages to various channels
            3. Verify the count is 3
            4. Publish 2 more messages
            5. Verify the count is 5

        This metric is used by monitoring and debugging tools to track
        bus throughput. It counts all publishes, regardless of whether
        there are subscribers or not.
        """
        bus = InMemoryMessageBus()
        await bus.connect()

        # Start at zero
        assert bus.published_message_count == 0, (
            "Fresh bus should have zero published messages"
        )

        # Publish 3 messages to different channels
        await bus.publish("conductor:agent:a", _make_message(sender="test-1"))
        await bus.publish("conductor:agent:b", _make_message(sender="test-2"))
        await bus.publish("conductor:broadcast", _make_message(sender="test-3"))

        assert bus.published_message_count == 3, (
            "Count should be 3 after publishing 3 messages"
        )

        # Publish 2 more
        await bus.publish("conductor:agent:c", _make_message(sender="test-4"))
        await bus.publish("conductor:agent:d", _make_message(sender="test-5"))

        assert bus.published_message_count == 5, (
            "Count should be 5 after publishing 5 total messages"
        )

        await bus.disconnect()
