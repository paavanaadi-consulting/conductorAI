# Message Routing Flow

This diagram shows how messages flow through the MessageBus and get routed to the correct subscribers.

## Message Bus Architecture

```mermaid
flowchart TD
    Start([Component wants to<br/>send message]) --> CreateMsg[Create AgentMessage]
    CreateMsg --> SetFields[Set fields:<br/>- message_type<br/>- sender_id<br/>- recipient_id<br/>- payload<br/>- priority]
    
    SetFields --> DetermineChannel{Determine channel}
    DetermineChannel -->|Direct message| DirectChannel[Channel: conductor:agent:{agent_id}]
    DetermineChannel -->|Broadcast| BroadcastChannel[Channel: conductor:broadcast]
    DetermineChannel -->|Phase message| PhaseChannel[Channel: conductor:phase:{phase}]
    DetermineChannel -->|Workflow message| WorkflowChannel[Channel: conductor:workflow:{id}]
    
    DirectChannel --> Publish[MessageBus.publish channel, message]
    BroadcastChannel --> Publish
    PhaseChannel --> Publish
    WorkflowChannel --> Publish
    
    Publish --> CheckTTL{Message has TTL?}
    CheckTTL -->|Yes| SetExpiry[Set expiration time]
    CheckTTL -->|No| NoExpiry[No expiration]
    SetExpiry --> Store
    NoExpiry --> Store[Store message in channel]
    
    Store --> FindSubscribers[Find all subscribers<br/>on this channel]
    FindSubscribers --> HasSubs{Has subscribers?}
    HasSubs -->|No| LogNoSubs[Log: No subscribers]
    HasSubs -->|Yes| IterateSubs[For each subscriber]
    
    IterateSubs --> CheckExpired{Message expired?}
    CheckExpired -->|Yes| DropMsg[Drop message]
    CheckExpired -->|No| CallCallback[Call subscriber callback<br/>with message]
    
    CallCallback --> AsyncExec[Execute callback asynchronously]
    AsyncExec --> HandleError{Callback error?}
    HandleError -->|Yes| LogError[Log callback error]
    HandleError -->|No| Success[Callback completed]
    
    LogError --> NextSub{More subscribers?}
    Success --> NextSub
    NextSub -->|Yes| IterateSubs
    NextSub -->|No| Complete[All subscribers notified]
    
    Complete --> Cleanup[Cleanup expired messages]
    Cleanup --> End([Message delivered])
    LogNoSubs --> End
    DropMsg --> End
    
    style Start fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    style End fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style DropMsg fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

## Channel Naming Convention

```mermaid
flowchart LR
    Channels[Message Channels] --> Direct["conductor:agent:{agent_id}<br/>Direct to specific agent"]
    Channels --> Broadcast["conductor:broadcast<br/>All agents"]
    Channels --> Phase["conductor:phase:{phase_name}<br/>Phase-scoped messages"]
    Channels --> Workflow["conductor:workflow:{workflow_id}<br/>Workflow-scoped messages"]
    Channels --> DLQ["conductor:dlq<br/>Dead Letter Queue"]
    
    Direct --> Example1["Example:<br/>conductor:agent:coding-01"]
    Broadcast --> Example2["Example:<br/>conductor:broadcast"]
    Phase --> Example3["Example:<br/>conductor:phase:development"]
    Workflow --> Example4["Example:<br/>conductor:workflow:wf-123"]
    DLQ --> Example5["Example:<br/>conductor:dlq"]
    
    style Channels fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style Direct fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Broadcast fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
```

## Pub/Sub Pattern Flow

```mermaid
sequenceDiagram
    participant P as Publisher
    participant MB as MessageBus
    participant S1 as Subscriber 1
    participant S2 as Subscriber 2
    participant S3 as Subscriber 3
    
    Note over S1,S3: Subscription Phase
    S1->>MB: subscribe("conductor:broadcast", callback1)
    MB->>MB: Register callback1 on channel
    S2->>MB: subscribe("conductor:broadcast", callback2)
    MB->>MB: Register callback2 on channel
    S3->>MB: subscribe("conductor:agent:coding-01", callback3)
    MB->>MB: Register callback3 on channel
    
    Note over P,S3: Publishing Phase
    P->>MB: publish("conductor:broadcast", msg)
    MB->>MB: Find subscribers on channel
    
    par Parallel delivery
        MB->>S1: callback1(msg)
        S1->>S1: Process message
        MB->>S2: callback2(msg)
        S2->>S2: Process message
    end
    
    Note over P,S3: Direct message
    P->>MB: publish("conductor:agent:coding-01", msg)
    MB->>S3: callback3(msg)
    S3->>S3: Process message
```

## Request-Response Pattern

```mermaid
flowchart TD
    Start([Client wants<br/>request-response]) --> CreateMsg[Create request message<br/>with unique correlation_id]
    CreateMsg --> CreateFuture[Create asyncio.Future<br/>for response]
    CreateFuture --> Register[Register Future in<br/>pending_requests dict<br/>key: correlation_id]
    
    Register --> Publish[MessageBus.publish<br/>request message]
    Publish --> AwaitFuture[await Future with timeout]
    
    AwaitFuture --> Timeout{Timeout reached?}
    Timeout -->|Yes| CancelFuture[Cancel Future]
    CancelFuture --> RaiseTimeout[Raise TimeoutError]
    
    Timeout -->|No| WaitResponse[Wait for response...]
    
    WaitResponse -.-> ResponderReceives[Responder receives<br/>request message]
    ResponderReceives --> Process[Process request]
    Process --> CreateResponse[Create response message<br/>with same correlation_id]
    CreateResponse --> PublishResponse[MessageBus.publish<br/>response message]
    
    PublishResponse -.-> BusReceives[MessageBus receives<br/>response]
    BusReceives --> LookupCorrelation[Lookup pending_requests<br/>by correlation_id]
    LookupCorrelation --> FoundFuture{Future found?}
    
    FoundFuture -->|No| LogOrphan[Log orphaned response]
    FoundFuture -->|Yes| SetResult[Future.set_result response]
    
    SetResult --> AwaitCompletes[await completes]
    AwaitCompletes --> Cleanup[Remove from pending_requests]
    Cleanup --> ReturnResponse([Return response<br/>to caller])
    
    LogOrphan --> Drop[Drop message]
    RaiseTimeout --> End([Error returned])
    ReturnResponse --> End2([Response returned])
    Drop --> End
    
    style Start fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    style ReturnResponse fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style RaiseTimeout fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

## Message Priority Handling

```mermaid
flowchart TD
    MsgArrives[Messages arrive] --> Queue[Add to priority queue]
    Queue --> Critical{Priority?}
    
    Critical -->|CRITICAL| Q1[Critical queue<br/>Priority: 1]
    Critical -->|HIGH| Q2[High queue<br/>Priority: 2]
    Critical -->|MEDIUM| Q3[Medium queue<br/>Priority: 3]
    Critical -->|LOW| Q4[Low queue<br/>Priority: 4]
    
    Q1 --> Dispatch[Message dispatcher]
    Q2 --> Dispatch
    Q3 --> Dispatch
    Q4 --> Dispatch
    
    Dispatch --> ProcessOrder[Process in order:<br/>1. CRITICAL<br/>2. HIGH<br/>3. MEDIUM<br/>4. LOW]
    ProcessOrder --> Deliver[Deliver to subscribers]
    
    style Q1 fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    style Q2 fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Q3 fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    style Q4 fill:#e0e0e0,stroke:#616161,stroke-width:2px
```

## Message Deduplication

```mermaid
flowchart TD
    Receive[Receive message] --> Extract[Extract message_id]
    Extract --> CheckCache{message_id in<br/>seen_messages cache?}
    
    CheckCache -->|Yes| Duplicate[Mark as duplicate]
    Duplicate --> LogDup[Log duplicate]
    LogDup --> Drop[Drop message]
    
    CheckCache -->|No| AddCache[Add message_id to cache]
    AddCache --> SetTTL[Set cache TTL<br/>default: 60 seconds]
    SetTTL --> Process[Process message normally]
    Process --> Deliver[Deliver to subscribers]
    
    Drop --> End([Message dropped])
    Deliver --> End2([Message delivered])
    
    style Duplicate fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Deliver fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

## Dead Letter Queue Flow

```mermaid
flowchart TD
    Start[Message cannot<br/>be delivered] --> Reason{Why?}
    
    Reason -->|Callback error| Error[Subscriber callback failed]
    Reason -->|No subscribers| NoSub[No subscribers on channel]
    Reason -->|Message expired| Expired[TTL exceeded]
    Reason -->|Invalid message| Invalid[Message validation failed]
    
    Error --> CreateDLQ[Create DLQ entry]
    NoSub --> CreateDLQ
    Expired --> CreateDLQ
    Invalid --> CreateDLQ
    
    CreateDLQ --> AddMetadata[Add metadata:<br/>- original_channel<br/>- failure_reason<br/>- timestamp<br/>- retry_count]
    
    AddMetadata --> Publish[MessageBus.publish<br/>channel: conductor:dlq]
    Publish --> Store[Store in DLQ]
    Store --> Monitor[Monitor process can<br/>inspect and retry]
    
    Monitor --> Manual{Manual review?}
    Manual -->|Retry| ExtractOriginal[Extract original message]
    ExtractOriginal --> IncrementRetry[Increment retry_count]
    IncrementRetry --> Republish[Republish to original channel]
    
    Manual -->|Archive| Archive[Move to long-term storage]
    Manual -->|Delete| Delete[Delete from DLQ]
    
    Republish --> End([Message reprocessed])
    Archive --> End2([Message archived])
    Delete --> End3([Message deleted])
    
    style Start fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    style End fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

## Subscription Management

```mermaid
flowchart TD
    Start([Component wants to<br/>receive messages]) --> Subscribe[MessageBus.subscribe<br/>channel, callback]
    Subscribe --> ValidateChannel{Valid channel?}
    
    ValidateChannel -->|No| InvalidChannel[Raise ValueError]
    ValidateChannel -->|Yes| ValidateCallback{Valid callback?}
    
    ValidateCallback -->|No| InvalidCallback[Raise ValueError]
    ValidateCallback -->|Yes| CheckExists{Callback already<br/>subscribed?}
    
    CheckExists -->|Yes| LogDuplicate[Log duplicate subscription]
    CheckExists -->|No| AddSubscription[Add to subscriptions dict<br/>channel -> [callbacks]]
    
    AddSubscription --> RegisterCleanup[Register cleanup on disconnect]
    RegisterCleanup --> Active[Subscription active]
    
    Active --> ReceiveMsg[Receive messages...]
    
    ReceiveMsg --> Unsubscribe{Want to unsubscribe?}
    Unsubscribe -->|Yes| Remove[MessageBus.unsubscribe<br/>channel, callback]
    Remove --> RemoveFromDict[Remove from subscriptions dict]
    RemoveFromDict --> CheckEmpty{Channel has<br/>other subscribers?}
    CheckEmpty -->|No| CleanupChannel[Remove channel entry]
    CheckEmpty -->|Yes| KeepChannel[Keep channel active]
    
    CleanupChannel --> End([Unsubscribed])
    KeepChannel --> End
    LogDuplicate --> End2([Subscription exists])
    InvalidChannel --> End3([Error])
    InvalidCallback --> End3
    
    style Start fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    style Active fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style End fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

## Message Correlation

```mermaid
flowchart LR
    Request1[Request Message] --> ID1[correlation_id: abc-123]
    Request2[Request Message] --> ID2[correlation_id: def-456]
    Request3[Request Message] --> ID3[correlation_id: ghi-789]
    
    ID1 --> Process1[Agent processes...]
    ID2 --> Process2[Agent processes...]
    ID3 --> Process3[Agent processes...]
    
    Process1 --> Response1[Response Message<br/>correlation_id: abc-123]
    Process2 --> Response2[Response Message<br/>correlation_id: def-456]
    Process3 --> Response3[Response Message<br/>correlation_id: ghi-789]
    
    Response1 --> Match1[Match to original request]
    Response2 --> Match2[Match to original request]
    Response3 --> Match3[Match to original request]
    
    Match1 --> Fulfill1[Fulfill Future 1]
    Match2 --> Fulfill2[Fulfill Future 2]
    Match3 --> Fulfill3[Fulfill Future 3]
    
    style Request1 fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style Response1 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

## Message State Diagram

```mermaid
stateDiagram-v2
    [*] --> Created: Create AgentMessage
    Created --> Published: publish() called
    Published --> InTransit: Stored in channel
    InTransit --> Delivered: Callback invoked
    InTransit --> Expired: TTL exceeded
    InTransit --> Failed: Delivery error
    Delivered --> Acknowledged: Callback completed
    Failed --> DLQ: Move to Dead Letter Queue
    Expired --> DLQ
    DLQ --> Retry: Manual retry
    Retry --> Published
    DLQ --> Archived: Long-term storage
    DLQ --> Deleted: Removed
    Acknowledged --> [*]
    Archived --> [*]
    Deleted --> [*]
```

## Message Flow Patterns

### 1. Coordinator → Agent (Task Assignment)
```mermaid
sequenceDiagram
    participant C as Coordinator
    participant MB as MessageBus
    participant A as Agent
    
    C->>MB: publish("conductor:agent:coding-01", task_assignment)
    Note over MB: Store in channel
    MB->>A: Deliver to subscriber
    A->>A: Execute task
    A->>MB: publish("conductor:broadcast", task_result)
    MB->>C: Deliver result
```

### 2. Monitor → Coordinator (Feedback)
```mermaid
sequenceDiagram
    participant M as MonitorAgent
    participant MB as MessageBus
    participant C as Coordinator
    participant WE as WorkflowEngine
    
    M->>MB: publish("conductor:broadcast", feedback)
    MB->>C: Deliver feedback
    C->>WE: Forward feedback
    WE->>WE: Decide on feedback loop
    WE->>MB: publish("conductor:phase:development", new_tasks)
    MB->>C: Deliver phase tasks
```

### 3. Error → Dead Letter Queue
```mermaid
sequenceDiagram
    participant A as Agent
    participant MB as MessageBus
    participant DLQ as Dead Letter Queue
    participant M as Monitor
    
    A->>MB: publish("conductor:broadcast", task_result)
    MB->>MB: Delivery error (callback failed)
    MB->>DLQ: publish("conductor:dlq", failed_message)
    DLQ->>DLQ: Store for inspection
    M->>DLQ: Query failed messages
    DLQ->>M: Return failed messages
    M->>M: Analyze and alert
```

## Performance Characteristics

### Message Latency (InMemory)
```
Publish: < 1ms
Subscription lookup: < 1ms
Callback invocation: < 1ms
Total: < 5ms
```

### Message Latency (Redis Pub/Sub)
```
Publish to Redis: 5-20ms
Redis to subscribers: 5-20ms
Callback invocation: < 1ms
Total: 10-50ms
```

### Throughput
```
InMemory: 100,000+ messages/second
Redis: 10,000-50,000 messages/second
```

### Backpressure Handling
```mermaid
flowchart TD
    High[Message rate too high] --> QueueSize{Queue size?}
    QueueSize -->|< threshold| Accept[Accept message]
    QueueSize -->|>= threshold| Reject[Reject with error]
    Reject --> Retry[Publisher retries]
    Retry --> Backoff[Exponential backoff]
    Accept --> Process[Process message]
```

This flow diagram details the complete message routing system in ConductorAI!
