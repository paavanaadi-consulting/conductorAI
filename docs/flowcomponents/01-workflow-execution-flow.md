# Workflow Execution Flow

This diagram shows the complete flow of a workflow execution from start to finish, including all three phases and the feedback loop.

## Complete Workflow Execution Flow

```mermaid
flowchart TD
    Start([User calls run_workflow]) --> Init[Initialize WorkflowState]
    Init --> CreateState[Create WorkflowState with IN_PROGRESS]
    CreateState --> SaveInitialState[StateManager.save_workflow_state]
    
    SaveInitialState --> Phase1{Enter DEVELOPMENT Phase}
    
    %% DEVELOPMENT Phase
    Phase1 --> CollectDevTasks[Collect tasks for<br/>CODING, REVIEW, TEST_DATA, TEST]
    CollectDevTasks --> DevLoop{More dev tasks?}
    
    DevLoop -->|Yes| DispatchDevTask[Coordinator.dispatch_task]
    DispatchDevTask --> CheckPolicy1[PolicyEngine.enforce]
    CheckPolicy1 --> PolicyOK1{Policy allows?}
    PolicyOK1 -->|No| PolicyViolation1[Raise PolicyViolationError]
    PolicyOK1 -->|Yes| FindAgent1[Find available agent]
    FindAgent1 --> AgentFound1{Agent available?}
    AgentFound1 -->|No| WaitOrFail1[Wait or raise AgentError]
    AgentFound1 -->|Yes| AssignTask1[Assign task to agent]
    AssignTask1 --> ExecuteTask1[Agent.execute_task]
    ExecuteTask1 --> TaskResult1[Receive TaskResult]
    TaskResult1 --> SaveResult1[StateManager.save_task_result]
    SaveResult1 --> DevLoop
    
    DevLoop -->|No| PhaseGate1{PolicyEngine: Check<br/>DEVELOPMENT gate}
    PhaseGate1 -->|Failed| WorkflowFailed[Set status=FAILED]
    PhaseGate1 -->|Passed| Phase2{Enter DEVOPS Phase}
    
    %% DEVOPS Phase
    Phase2 --> CollectDevOpsTasks[Collect tasks for<br/>DEVOPS, DEPLOYING]
    CollectDevOpsTasks --> DevOpsLoop{More DevOps tasks?}
    
    DevOpsLoop -->|Yes| DispatchDevOpsTask[Coordinator.dispatch_task]
    DispatchDevOpsTask --> CheckPolicy2[PolicyEngine.enforce]
    CheckPolicy2 --> PolicyOK2{Policy allows?}
    PolicyOK2 -->|No| PolicyViolation2[Raise PolicyViolationError]
    PolicyOK2 -->|Yes| FindAgent2[Find available agent]
    FindAgent2 --> AgentFound2{Agent available?}
    AgentFound2 -->|No| WaitOrFail2[Wait or raise AgentError]
    AgentFound2 -->|Yes| AssignTask2[Assign task to agent]
    AssignTask2 --> ExecuteTask2[Agent.execute_task]
    ExecuteTask2 --> TaskResult2[Receive TaskResult]
    TaskResult2 --> SaveResult2[StateManager.save_task_result]
    SaveResult2 --> DevOpsLoop
    
    DevOpsLoop -->|No| PhaseGate2{PolicyEngine: Check<br/>DEVOPS gate}
    PhaseGate2 -->|Failed| WorkflowFailed
    PhaseGate2 -->|Passed| Phase3{Enter MONITORING Phase}
    
    %% MONITORING Phase
    Phase3 --> CollectMonTasks[Collect tasks for<br/>MONITOR]
    CollectMonTasks --> MonLoop{More monitoring tasks?}
    
    MonLoop -->|Yes| DispatchMonTask[Coordinator.dispatch_task]
    DispatchMonTask --> CheckPolicy3[PolicyEngine.enforce]
    CheckPolicy3 --> PolicyOK3{Policy allows?}
    PolicyOK3 -->|No| PolicyViolation3[Raise PolicyViolationError]
    PolicyOK3 -->|Yes| FindAgent3[Find available agent]
    FindAgent3 --> AgentFound3{Agent available?}
    AgentFound3 -->|No| WaitOrFail3[Wait or raise AgentError]
    AgentFound3 -->|Yes| AssignTask3[Assign task to agent]
    AssignTask3 --> ExecuteTask3[Agent.execute_task]
    ExecuteTask3 --> TaskResult3[Receive TaskResult]
    TaskResult3 --> SaveResult3[StateManager.save_task_result]
    SaveResult3 --> MonLoop
    
    MonLoop -->|No| CheckFeedback{Feedback from<br/>MonitorAgent?}
    
    %% Feedback Loop
    CheckFeedback -->|Yes, critical issues| CheckLoopCount{Feedback loops < max?}
    CheckLoopCount -->|No| MaxLoopsReached[Log: Max feedback loops reached]
    MaxLoopsReached --> WorkflowCompleted
    CheckLoopCount -->|Yes| IncrementLoop[Increment feedback_loop_count]
    IncrementLoop --> Phase1
    
    CheckFeedback -->|No issues| WorkflowCompleted[Set status=COMPLETED]
    
    WorkflowCompleted --> SaveFinalState[StateManager.save_workflow_state]
    WorkflowFailed --> SaveFailedState[StateManager.save_workflow_state]
    
    SaveFinalState --> Return([Return WorkflowState])
    SaveFailedState --> Return
    PolicyViolation1 --> Return
    PolicyViolation2 --> Return
    PolicyViolation3 --> Return
    
    style Start fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    style Return fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    style Phase1 fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    style Phase2 fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Phase3 fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    style WorkflowCompleted fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style WorkflowFailed fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

## Phase Execution Details

### Development Phase
```mermaid
flowchart LR
    Dev[DEVELOPMENT Phase] --> Coding[CodingAgent:<br/>Generate code]
    Coding --> Review[ReviewAgent:<br/>Review code]
    Review --> TestData[TestDataAgent:<br/>Generate test data]
    TestData --> Test[TestAgent:<br/>Run tests]
    Test --> Gate{Phase Gate:<br/>Success rate > threshold?}
    Gate -->|Yes| NextPhase[→ DEVOPS]
    Gate -->|No| Failed[Workflow FAILED]
    
    style Dev fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    style NextPhase fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Failed fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

### DevOps Phase
```mermaid
flowchart LR
    DevOps[DEVOPS Phase] --> Config[DevOpsAgent:<br/>Create CI/CD configs]
    Config --> Deploy[DeployingAgent:<br/>Deploy to environment]
    Deploy --> Gate{Phase Gate:<br/>Deployment successful?}
    Gate -->|Yes| NextPhase[→ MONITORING]
    Gate -->|No| Failed[Workflow FAILED]
    
    style DevOps fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style NextPhase fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    style Failed fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

### Monitoring Phase
```mermaid
flowchart LR
    Mon[MONITORING Phase] --> Collect[MonitorAgent:<br/>Collect metrics]
    Collect --> Analyze[Analyze against<br/>thresholds]
    Analyze --> Issues{Critical issues?}
    Issues -->|Yes| Feedback[Generate FeedbackPayload]
    Feedback --> Loop{feedback_loop_count<br/>< max_loops?}
    Loop -->|Yes| ReturnToDev[→ DEVELOPMENT]
    Loop -->|No| MaxReached[Complete with warnings]
    Issues -->|No| Success[Workflow COMPLETED]
    
    style Mon fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    style ReturnToDev fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    style Success fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

## State Transitions

```mermaid
stateDiagram-v2
    [*] --> PENDING: WorkflowDefinition created
    PENDING --> IN_PROGRESS: WorkflowEngine.run_workflow()
    IN_PROGRESS --> DEVELOPMENT: Enter first phase
    
    DEVELOPMENT --> DEVOPS: Phase gate passed
    DEVELOPMENT --> FAILED: Phase gate failed
    
    DEVOPS --> MONITORING: Phase gate passed
    DEVOPS --> FAILED: Phase gate failed
    
    MONITORING --> COMPLETED: No critical issues
    MONITORING --> DEVELOPMENT: Feedback loop (issues found)
    MONITORING --> FAILED: Max loops reached with issues
    
    FAILED --> [*]: Return to user
    COMPLETED --> [*]: Return to user
```

## Workflow State Properties

During execution, WorkflowState tracks:

```yaml
WorkflowState:
  workflow_id: "wf-abc-123"
  status: IN_PROGRESS | COMPLETED | FAILED
  current_phase: DEVELOPMENT | DEVOPS | MONITORING
  
  # Per-phase tracking
  pending_tasks: ["task-1", "task-2"]
  completed_tasks: ["task-0"]
  failed_tasks: []
  
  # Results by task ID
  task_results:
    "task-0":
      status: COMPLETED
      output_data: {...}
  
  # Agent states
  agent_states:
    "coding-01":
      status: IDLE
      completed_tasks: ["task-0"]
  
  # Feedback loop tracking
  feedback_loop_count: 0
  
  # Timing
  started_at: 2026-02-17T10:00:00Z
  completed_at: null
```

## Key Decision Points

### 1. Phase Gate Decisions
**Input**: Task results from current phase  
**Logic**: Check success rate against threshold  
**Output**: PASS → next phase, FAIL → workflow failed

Example:
```python
success_rate = completed_tasks / total_tasks
if success_rate < policy.min_success_rate:
    workflow.status = FAILED
else:
    workflow.current_phase = next_phase
```

### 2. Feedback Loop Decisions
**Input**: FeedbackPayload from MonitorAgent  
**Logic**: Check severity and loop count  
**Output**: Loop back or complete

Example:
```python
if feedback.severity in ["error", "critical"]:
    if workflow.feedback_loop_count < max_loops:
        workflow.feedback_loop_count += 1
        workflow.current_phase = DEVELOPMENT
    else:
        workflow.status = COMPLETED  # with warnings
else:
    workflow.status = COMPLETED
```

### 3. Agent Selection Decisions
**Input**: Task with agent_type requirement  
**Logic**: Find IDLE agent of correct type  
**Output**: Agent assignment or error

Example:
```python
available_agents = [
    a for a in agents 
    if a.agent_type == task.assigned_to 
    and a.status == IDLE
]
if not available_agents:
    raise AgentError("NO_AVAILABLE_AGENT")
selected = available_agents[0]
```

## Error Handling in Workflow

```mermaid
flowchart TD
    TaskFail[Task Execution Failed] --> EH[ErrorHandler.handle_error]
    EH --> CB{CircuitBreaker open?}
    CB -->|Yes| DLQ1[Dead Letter Queue]
    CB -->|No| Retryable{Error retryable?}
    Retryable -->|No| Escalate[Escalate to coordinator]
    Retryable -->|Yes| Attempts{Attempts < max?}
    Attempts -->|No| DLQ2[Dead Letter Queue]
    Attempts -->|Yes| Retry[Retry with backoff]
    
    Retry --> TaskSuccess{Retry succeeded?}
    TaskSuccess -->|Yes| Continue[Continue workflow]
    TaskSuccess -->|No| EH
    
    Escalate --> UserDecision{User reviews}
    UserDecision -->|Fix and retry| Retry
    UserDecision -->|Skip| SkipTask[Mark task as skipped]
    UserDecision -->|Abort| AbortWorkflow[Workflow FAILED]
    
    style TaskFail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    style Continue fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style AbortWorkflow fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

## Performance Characteristics

### Timing Expectations
- **Development Phase**: 30-120 seconds (LLM calls dominant)
- **DevOps Phase**: 10-30 seconds (config generation)
- **Monitoring Phase**: 5-15 seconds (metrics analysis)
- **Total Workflow**: 45-165 seconds (without feedback loops)

### With Feedback Loops
- **Single loop**: +60-180 seconds (re-run development)
- **Max loops (3)**: Up to 10+ minutes total

### Bottlenecks
1. **LLM API calls**: 5-15 seconds per generation
2. **Agent availability**: Waiting for IDLE agents
3. **Phase gates**: Policy evaluations are fast (<1ms)
4. **State persistence**: Redis writes are fast (<10ms)

## Optimization Opportunities

### Parallel Task Execution
```mermaid
flowchart LR
    Phase[Phase Tasks] --> Split{Can parallelize?}
    Split -->|Yes| P1[Task 1] & P2[Task 2] & P3[Task 3]
    P1 & P2 & P3 --> Sync[Wait for all]
    Split -->|No| Sequential[Execute sequentially]
    Sync --> Next[Next phase]
    Sequential --> Next
```

### Caching
- **LLM responses**: Cache identical prompts
- **Artifacts**: Reuse from previous runs
- **Policy results**: Cache by context hash

This flow diagram shows the complete lifecycle of a workflow execution in ConductorAI!
