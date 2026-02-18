# Task Dispatch and Execution Flow

This diagram shows the detailed flow of task assignment from coordinator to agent and back.

## Complete Task Dispatch Flow

```mermaid
flowchart TD
    Start([Coordinator.dispatch_task<br/>called with TaskDefinition]) --> ValidateTask{Task valid?}
    
    ValidateTask -->|No| InvalidTask[Raise ValueError]
    ValidateTask -->|Yes| DetermineType[Determine target<br/>agent_type from task]
    
    DetermineType --> CheckPolicy[PolicyEngine.enforce<br/>with task context]
    CheckPolicy --> PolicyCheck{All policies pass?}
    PolicyCheck -->|No| PolicyFail[Raise PolicyViolationError]
    PolicyCheck -->|Yes| FindAgents[Get all agents of<br/>target agent_type]
    
    FindAgents --> FilterIdle[Filter agents with<br/>status == IDLE]
    FilterIdle --> AgentCheck{Any IDLE agents?}
    
    AgentCheck -->|No| WaitOrError{Retry enabled?}
    WaitOrError -->|No| NoAgent[Raise AgentError:<br/>NO_AVAILABLE_AGENT]
    WaitOrError -->|Yes| Wait[Wait 1 second]
    Wait --> Retry{Retry count < max?}
    Retry -->|Yes| FindAgents
    Retry -->|No| NoAgent
    
    AgentCheck -->|Yes| SelectAgent[Select first<br/>available agent]
    SelectAgent --> UpdateState1[Update agent state:<br/>status = RUNNING<br/>current_task_id = task.task_id]
    UpdateState1 --> SaveState1[StateManager.save_agent_state]
    
    SaveState1 --> CreateMessage[Create AgentMessage<br/>type = TASK_ASSIGNMENT<br/>payload = TaskAssignmentPayload]
    CreateMessage --> PublishTask[MessageBus.publish<br/>channel: conductor:agent:{agent_id}]
    
    PublishTask --> WaitForAgent[Wait for agent<br/>to process task...]
    
    WaitForAgent --> AgentReceives[Agent receives message<br/>via MessageBus subscription]
    AgentReceives --> AgentHandle[Agent.handle_message<br/>extracts TaskDefinition]
    AgentHandle --> AgentExecute[Agent.execute_task<br/>Template Method]
    
    %% Agent execution details
    AgentExecute --> Validate[Agent._validate_task]
    Validate --> ValidCheck{Task valid for<br/>this agent?}
    ValidCheck -->|No| ValidationFail[Raise AgentError:<br/>TASK_VALIDATION_FAILED]
    ValidCheck -->|Yes| SetRunning[Update status to RUNNING]
    
    SetRunning --> Execute[Agent._execute<br/>Core agent logic]
    Execute --> LLMCall{Needs LLM?}
    LLMCall -->|Yes| CallLLM[LLMProvider.generate]
    CallLLM --> ProcessLLM[Process LLM response]
    ProcessLLM --> CreateArtifact
    LLMCall -->|No| CreateArtifact[Create artifacts]
    
    CreateArtifact --> SaveArtifact[ArtifactStore.save]
    SaveArtifact --> BuildResult[Build TaskResult<br/>status = COMPLETED<br/>output_data = {...}]
    
    BuildResult --> UpdateState2[Update agent state:<br/>status = IDLE<br/>completed_tasks += task_id]
    UpdateState2 --> SaveState2[StateManager.save_agent_state]
    
    SaveState2 --> CreateResponse[Create AgentMessage<br/>type = TASK_RESULT<br/>payload = TaskResultPayload]
    CreateResponse --> PublishResult[MessageBus.publish<br/>channel: conductor:broadcast]
    
    PublishResult --> CoordReceives[Coordinator receives<br/>task result message]
    CoordReceives --> SaveTaskResult[StateManager.save_task_result]
    SaveTaskResult --> ReturnResult([Return TaskResult<br/>to WorkflowEngine])
    
    %% Error paths
    Execute --> ExecuteError{Error during<br/>execution?}
    ExecuteError -->|Yes| ErrorHandler[ErrorHandler.handle_error]
    ErrorHandler --> ErrorAction{What action?}
    ErrorAction -->|RETRY| RetryTask[Retry task after backoff]
    RetryTask --> Execute
    ErrorAction -->|ESCALATE| EscalateError[Publish error message<br/>to coordinator]
    ErrorAction -->|DEAD_LETTER| DLQ[Add to Dead Letter Queue]
    ErrorAction -->|SKIP| SkipTask[Mark task as skipped]
    
    EscalateError --> BuildFailResult[Build TaskResult<br/>status = FAILED<br/>error_message = ...]
    DLQ --> BuildFailResult
    SkipTask --> BuildFailResult
    BuildFailResult --> UpdateState3[Update agent state:<br/>status = IDLE<br/>failed_tasks += task_id]
    UpdateState3 --> SaveState3[StateManager.save_agent_state]
    SaveState3 --> CreateFailResponse[Create error message]
    CreateFailResponse --> PublishFail[MessageBus.publish]
    PublishFail --> CoordReceives
    
    ValidationFail --> BuildFailResult
    
    InvalidTask --> End([End])
    PolicyFail --> End
    NoAgent --> End
    ReturnResult --> End
    
    style Start fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    style End fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    style Execute fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style ReturnResult fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style PolicyFail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    style NoAgent fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

## Agent Task Execution Lifecycle

```mermaid
stateDiagram-v2
    [*] --> IDLE: Agent registered
    IDLE --> RUNNING: Task assigned
    RUNNING --> EXECUTING: _execute() called
    EXECUTING --> LLM_CALL: LLM generation needed
    LLM_CALL --> PROCESSING: LLM response received
    PROCESSING --> ARTIFACT_SAVE: Create artifacts
    ARTIFACT_SAVE --> COMPLETED: Success
    EXECUTING --> FAILED: Error occurred
    FAILED --> ERROR_HANDLING: ErrorHandler.handle_error
    ERROR_HANDLING --> EXECUTING: RETRY action
    ERROR_HANDLING --> IDLE: ESCALATE/DLQ/SKIP
    COMPLETED --> IDLE: Ready for next task
    IDLE --> [*]: Agent unregistered
```

## Message Flow Detail

### Task Assignment Message
```mermaid
sequenceDiagram
    participant C as Coordinator
    participant MB as MessageBus
    participant A as Agent
    
    C->>C: Create TaskAssignmentPayload
    C->>MB: publish("conductor:agent:coding-01", msg)
    Note over MB: Message stored in channel queue
    MB->>A: Deliver message to subscriber
    A->>A: handle_message(msg)
    A->>A: Extract TaskDefinition from payload
    A->>A: execute_task(task)
```

### Task Result Message
```mermaid
sequenceDiagram
    participant A as Agent
    participant MB as MessageBus
    participant C as Coordinator
    participant SM as StateManager
    
    A->>A: Build TaskResult
    A->>A: Create TaskResultPayload
    A->>MB: publish("conductor:broadcast", msg)
    MB->>C: Deliver to all subscribers
    C->>C: Extract TaskResult from payload
    C->>SM: save_task_result(result)
    C->>C: Return result to WorkflowEngine
```

## Policy Enforcement Detail

```mermaid
flowchart TD
    Start[PolicyEngine.enforce<br/>with context] --> LoadPolicies[Load all registered policies]
    LoadPolicies --> Loop{More policies?}
    
    Loop -->|Yes| NextPolicy[Get next policy]
    NextPolicy --> Evaluate[policy.evaluate context]
    Evaluate --> Result[Get PolicyResult]
    Result --> Allowed{allowed == True?}
    
    Allowed -->|No| Violation[Collect violation details]
    Violation --> RaiseError[Raise PolicyViolationError<br/>with policy_name and reason]
    
    Allowed -->|Yes| LogPass[Log policy passed]
    LogPass --> Loop
    
    Loop -->|No| AllPass[All policies passed]
    AllPass --> Return([Return success])
    
    style Start fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Return fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style RaiseError fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

## Agent Selection Algorithm

```mermaid
flowchart TD
    Start[Find available agent<br/>for task] --> GetType[Extract agent_type<br/>from task]
    GetType --> GetAll[Get all registered agents<br/>from coordinator registry]
    GetAll --> FilterType[Filter by agent_type]
    
    FilterType --> TypeMatch{Any matches?}
    TypeMatch -->|No| NoType[Raise AgentError:<br/>NO_AGENT_OF_TYPE]
    TypeMatch -->|Yes| FilterStatus[Filter by status == IDLE]
    
    FilterStatus --> StatusCheck{Any IDLE?}
    StatusCheck -->|No| CheckCB{CircuitBreaker open<br/>for any agent?}
    CheckCB -->|All open| AllBroken[Raise AgentError:<br/>ALL_AGENTS_UNHEALTHY]
    CheckCB -->|Some closed| WaitRetry[Wait and retry]
    
    StatusCheck -->|Yes| SortAgents[Sort by priority:<br/>1. Least loaded<br/>2. Most successful<br/>3. Least errors]
    SortAgents --> SelectFirst[Select first agent]
    SelectFirst --> CheckHealth[Check CircuitBreaker]
    CheckHealth --> HealthOK{Breaker closed?}
    
    HealthOK -->|No| TryNext[Try next agent]
    TryNext --> SortAgents
    HealthOK -->|Yes| Return([Return selected agent])
    
    style Start fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style Return fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style NoType fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    style AllBroken fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

## Concurrent Task Handling

```mermaid
flowchart TD
    Start[Multiple tasks arrive] --> Check[Check MaxConcurrentTasksPolicy]
    Check --> Count[Count currently RUNNING agents]
    Count --> Limit{count < max?}
    
    Limit -->|No| Queue[Add to wait queue]
    Queue --> Monitor[Monitor for agent IDLE events]
    Monitor --> AgentDone{Agent became IDLE?}
    AgentDone -->|Yes| DequeueTask[Dequeue next task]
    DequeueTask --> Limit
    AgentDone -->|No| Monitor
    
    Limit -->|Yes| Dispatch[Dispatch task immediately]
    Dispatch --> Increment[Increment running count]
    Increment --> AgentExec[Agent executes]
    AgentExec --> Done[Task completes]
    Done --> Decrement[Decrement running count]
    Decrement --> CheckQueue{Tasks in queue?}
    CheckQueue -->|Yes| DequeueTask
    CheckQueue -->|No| End([Done])
    
    style Start fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style End fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

## Task Priority Handling

```mermaid
flowchart LR
    Tasks[Incoming Tasks] --> Queue[Priority Queue]
    Queue --> Critical[Priority: CRITICAL]
    Queue --> High[Priority: HIGH]
    Queue --> Medium[Priority: MEDIUM]
    Queue --> Low[Priority: LOW]
    
    Critical --> Dispatch1[Dispatch first]
    High --> Dispatch2[Dispatch second]
    Medium --> Dispatch3[Dispatch third]
    Low --> Dispatch4[Dispatch last]
    
    Dispatch1 --> Agent[Available Agent]
    Dispatch2 --> Agent
    Dispatch3 --> Agent
    Dispatch4 --> Agent
    
    style Critical fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    style High fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Agent fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

## State Synchronization

```mermaid
sequenceDiagram
    participant A as Agent
    participant C as Coordinator
    participant SM as StateManager
    participant R as Redis
    
    Note over A,C: Task Assignment
    C->>A: Assign task
    C->>C: Update in-memory agent state
    C->>SM: save_agent_state(RUNNING)
    SM->>R: SET agent:{id} {state JSON}
    
    Note over A,C: Task Execution
    A->>A: Execute task
    A->>A: Update local state
    
    Note over A,C: Task Completion
    A->>C: Return result
    C->>C: Update in-memory agent state
    C->>SM: save_agent_state(IDLE)
    SM->>R: SET agent:{id} {state JSON}
    C->>SM: save_task_result(result)
    SM->>R: SET task_result:{id} {result JSON}
```

## Error Recovery Flow

```mermaid
flowchart TD
    Error[Task execution error] --> Capture[Capture error details]
    Capture --> CreateContext[Build error context:<br/>- agent_id<br/>- task_id<br/>- error_code<br/>- attempt_count]
    
    CreateContext --> EH[ErrorHandler.handle_error]
    EH --> CB{Check CircuitBreaker}
    CB -->|Open| Skip1[Skip to DLQ]
    CB -->|Closed/HalfOpen| CheckRetry[Check RetryPolicy]
    
    CheckRetry --> Retryable{is_retryable?}
    Retryable -->|No| Escalate[ErrorAction.ESCALATE]
    Retryable -->|Yes| Attempts{attempt < max?}
    Attempts -->|No| MaxRetries[ErrorAction.DEAD_LETTER]
    Attempts -->|Yes| CalcDelay[Calculate backoff delay]
    
    CalcDelay --> Sleep[Sleep with exponential backoff]
    Sleep --> RecordCB[CircuitBreaker.record_attempt]
    RecordCB --> Retry[ErrorAction.RETRY]
    
    Retry --> NewAttempt[Retry task execution]
    NewAttempt --> Success{Succeeded?}
    Success -->|Yes| RecordSuccess[CircuitBreaker.record_success]
    Success -->|No| RecordFailure[CircuitBreaker.record_failure]
    
    RecordSuccess --> Complete[Task completed]
    RecordFailure --> CheckCBState{Failure threshold<br/>reached?}
    CheckCBState -->|Yes| OpenCB[CircuitBreaker: OPEN]
    CheckCBState -->|No| EH
    
    OpenCB --> DLQMsg[Add to Dead Letter Queue]
    
    Escalate --> Notify[Notify coordinator]
    MaxRetries --> DLQMsg
    Skip1 --> DLQMsg
    
    DLQMsg --> Log[Log to monitoring]
    Log --> End([Task marked FAILED])
    Complete --> End2([Task marked COMPLETED])
    
    style Error fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    style Complete fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style End2 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

## Performance Metrics

### Task Dispatch Latency
```
Policy check: < 1ms
Agent lookup: < 5ms
State save: 5-10ms (InMemory) | 10-50ms (Redis)
Message publish: < 5ms (InMemory) | 10-50ms (Redis)
---
Total: ~20-100ms
```

### Agent Execution Time
```
Validation: < 1ms
LLM call: 5-15 seconds (dominant)
Artifact save: 5-20ms
State update: 5-10ms
Result publish: < 5ms
---
Total: ~5-15 seconds (LLM dependent)
```

### Task Throughput
```
Sequential: ~4-12 tasks/minute (LLM bottleneck)
Parallel (5 agents): ~20-60 tasks/minute
Parallel (10 agents): ~40-120 tasks/minute
```

This flow diagram details the complete task dispatch and execution lifecycle in ConductorAI!
