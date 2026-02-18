# System Architecture Overview

This diagram provides a complete view of the ConductorAI system architecture, showing how all layers interact.

## High-Level Architecture Diagram

```mermaid
graph TB
    %% ==========================================
    %% User/Client Layer
    %% ==========================================
    User[User/Client Application]
    
    %% ==========================================
    %% Facade Layer
    %% ==========================================
    subgraph Facade["🎭 Facade Layer"]
        ConductorAI[ConductorAI Facade]
    end
    
    %% ==========================================
    %% Orchestration Layer
    %% ==========================================
    subgraph Orchestration["🎼 Orchestration Layer"]
        WE[Workflow Engine]
        AC[Agent Coordinator]
        MB[Message Bus]
        SM[State Manager]
        PE[Policy Engine]
        EH[Error Handler]
    end
    
    %% ==========================================
    %% Agent Layer
    %% ==========================================
    subgraph Agents["🤖 Agent Layer"]
        subgraph DevPhase["Development Phase"]
            CA[Coding Agent]
            RA[Review Agent]
            TDA[Test Data Agent]
            TA[Test Agent]
        end
        
        subgraph DevOpsPhase["DevOps Phase"]
            DA[DevOps Agent]
            DPA[Deploying Agent]
        end
        
        subgraph MonPhase["Monitoring Phase"]
            MA[Monitor Agent]
        end
    end
    
    %% ==========================================
    %% Infrastructure Layer
    %% ==========================================
    subgraph Infrastructure["🏗️ Infrastructure Layer"]
        AS[Artifact Store]
    end
    
    %% ==========================================
    %% Integration Layer
    %% ==========================================
    subgraph Integration["🔌 Integration Layer"]
        LLM[LLM Providers<br/>Mock/OpenAI/Anthropic]
    end
    
    %% ==========================================
    %% External Services
    %% ==========================================
    subgraph External["☁️ External Services"]
        Redis[(Redis<br/>State & Messages)]
        OpenAI[OpenAI API]
        Anthropic[Anthropic API]
        S3[(S3<br/>Artifacts)]
    end
    
    %% ==========================================
    %% Relationships
    %% ==========================================
    
    %% User to Facade
    User -->|run_workflow| ConductorAI
    User -->|register_agent| ConductorAI
    
    %% Facade to Orchestration
    ConductorAI --> WE
    ConductorAI --> AC
    ConductorAI --> MB
    ConductorAI --> SM
    
    %% Orchestration Internal
    WE -->|dispatch_task| AC
    AC -->|publish| MB
    AC -->|check_policy| PE
    AC -->|handle_error| EH
    AC -->|save_state| SM
    WE -->|save_workflow_state| SM
    
    %% Orchestration to Agents
    MB -.->|task_assignment| CA
    MB -.->|task_assignment| RA
    MB -.->|task_assignment| TDA
    MB -.->|task_assignment| TA
    MB -.->|task_assignment| DA
    MB -.->|task_assignment| DPA
    MB -.->|task_assignment| MA
    
    CA -.->|task_result| MB
    RA -.->|task_result| MB
    TDA -.->|task_result| MB
    TA -.->|task_result| MB
    DA -.->|task_result| MB
    DPA -.->|task_result| MB
    MA -.->|feedback| MB
    
    %% Agents to Infrastructure
    CA --> AS
    RA --> AS
    TDA --> AS
    TA --> AS
    DA --> AS
    DPA --> AS
    MA --> AS
    
    %% Agents to Integration
    CA --> LLM
    RA --> LLM
    TDA --> LLM
    TA --> LLM
    DA --> LLM
    DPA --> LLM
    MA --> LLM
    
    %% Infrastructure/Integration to External
    SM -.->|persist| Redis
    MB -.->|pub/sub| Redis
    AS -.->|store| S3
    LLM -.->|API calls| OpenAI
    LLM -.->|API calls| Anthropic
    
    %% Styling
    classDef facade fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef orchestration fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef agent fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef infrastructure fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef integration fill:#fff8e1,stroke:#f57f17,stroke-width:2px
    classDef external fill:#eceff1,stroke:#263238,stroke-width:2px
    
    class ConductorAI facade
    class WE,AC,MB,SM,PE,EH orchestration
    class CA,RA,TDA,TA,DA,DPA,MA agent
    class AS infrastructure
    class LLM integration
    class Redis,OpenAI,Anthropic,S3 external
```

## Detailed Component Diagram

```mermaid
classDiagram
    %% ==========================================
    %% Top-Level System
    %% ==========================================
    class ConductorAI {
        <<Facade>>
        -WorkflowEngine _workflow_engine
        -AgentCoordinator _coordinator
        -MessageBus _message_bus
        -StateManager _state_manager
        -PolicyEngine _policy_engine
        -ErrorHandler _error_handler
        -ArtifactStore _artifact_store
        -BaseLLMProvider _llm_provider
        
        +initialize() void
        +shutdown() void
        +register_agent(BaseAgent) void
        +run_workflow(WorkflowDefinition) WorkflowState
        +get_workflow_state(workflow_id) WorkflowState
        +get_artifact(artifact_id) Artifact
    }
    
    %% ==========================================
    %% Orchestration Components
    %% ==========================================
    class WorkflowEngine {
        +run_workflow(WorkflowDefinition) WorkflowState
    }
    
    class AgentCoordinator {
        +register_agent(BaseAgent) void
        +dispatch_task(TaskDefinition) TaskResult
    }
    
    class MessageBus {
        +publish(channel, message) void
        +subscribe(channel, callback) void
    }
    
    class StateManager {
        +save_agent_state(AgentState) void
        +save_workflow_state(WorkflowState) void
    }
    
    class PolicyEngine {
        +enforce(context) void
        +check(context) bool
    }
    
    class ErrorHandler {
        +handle_error(error, context) ErrorAction
    }
    
    %% ==========================================
    %% Agent Layer
    %% ==========================================
    class BaseAgent {
        <<abstract>>
        +execute_task(TaskDefinition) TaskResult
    }
    
    class CodingAgent {
        +_execute(TaskDefinition) TaskResult
    }
    
    class ReviewAgent {
        +_execute(TaskDefinition) TaskResult
    }
    
    class MonitorAgent {
        +_execute(TaskDefinition) TaskResult
    }
    
    %% ==========================================
    %% Infrastructure & Integration
    %% ==========================================
    class ArtifactStore {
        +save(Artifact) void
        +get(artifact_id) Artifact
    }
    
    class BaseLLMProvider {
        +generate(prompt) LLMResponse
    }
    
    %% ==========================================
    %% Core Models
    %% ==========================================
    class WorkflowDefinition {
        +workflow_id str
        +name str
        +tasks list~TaskDefinition~
    }
    
    class WorkflowState {
        +workflow_id str
        +status TaskStatus
        +current_phase WorkflowPhase
    }
    
    class TaskDefinition {
        +task_id str
        +assigned_to AgentType
        +input_data dict
    }
    
    class TaskResult {
        +task_id str
        +status TaskStatus
        +output_data dict
    }
    
    class AgentState {
        +agent_id str
        +status AgentStatus
        +current_task_id str
    }
    
    class Artifact {
        +artifact_id str
        +workflow_id str
        +content str
    }
    
    %% ==========================================
    %% Relationships
    %% ==========================================
    
    %% Facade Composition
    ConductorAI *-- WorkflowEngine
    ConductorAI *-- AgentCoordinator
    ConductorAI *-- MessageBus
    ConductorAI *-- StateManager
    ConductorAI *-- PolicyEngine
    ConductorAI *-- ErrorHandler
    ConductorAI *-- ArtifactStore
    ConductorAI *-- BaseLLMProvider
    
    %% Orchestration Dependencies
    WorkflowEngine --> AgentCoordinator
    WorkflowEngine --> StateManager
    WorkflowEngine --> PolicyEngine
    AgentCoordinator --> MessageBus
    AgentCoordinator --> StateManager
    AgentCoordinator --> PolicyEngine
    AgentCoordinator --> ErrorHandler
    
    %% Agent Dependencies
    BaseAgent <|-- CodingAgent
    BaseAgent <|-- ReviewAgent
    BaseAgent <|-- MonitorAgent
    AgentCoordinator o-- BaseAgent
    BaseAgent --> BaseLLMProvider
    BaseAgent --> ArtifactStore
    
    %% Data Flow
    ConductorAI ..> WorkflowDefinition : receives
    WorkflowEngine ..> WorkflowState : manages
    AgentCoordinator ..> TaskDefinition : dispatches
    BaseAgent ..> TaskResult : produces
    BaseAgent ..> Artifact : creates
    StateManager ..> AgentState : persists
```

## Workflow Execution Flow

```mermaid
sequenceDiagram
    participant User
    participant Facade as ConductorAI
    participant WE as WorkflowEngine
    participant AC as AgentCoordinator
    participant PE as PolicyEngine
    participant MB as MessageBus
    participant Agent as CodingAgent
    participant LLM as LLM Provider
    participant AS as ArtifactStore
    participant SM as StateManager
    
    %% Setup
    User->>Facade: run_workflow(definition)
    Facade->>WE: run_workflow(definition)
    WE->>SM: create WorkflowState
    
    %% Phase 1: Development
    Note over WE: Phase: DEVELOPMENT
    WE->>AC: dispatch_task(coding_task)
    AC->>PE: enforce(context)
    PE-->>AC: allowed=True
    AC->>MB: publish("conductor:agent:coding-01", task)
    MB-->>Agent: deliver task
    
    %% Agent Execution
    Agent->>Agent: execute_task()
    Agent->>LLM: generate_with_system(prompt)
    LLM-->>Agent: LLMResponse(code)
    Agent->>AS: save(artifact)
    Agent->>MB: publish(task_result)
    MB-->>AC: deliver result
    
    %% Result Processing
    AC->>SM: save_task_result(result)
    AC->>SM: update_agent_state(IDLE)
    AC-->>WE: return result
    
    %% Phase Gate
    WE->>PE: check(phase_gate)
    PE-->>WE: allowed=True
    
    %% Phase 2: DevOps
    Note over WE: Phase: DEVOPS
    WE->>AC: dispatch_task(devops_task)
    Note over Agent: Similar flow...
    
    %% Phase 3: Monitoring
    Note over WE: Phase: MONITORING
    WE->>AC: dispatch_task(monitor_task)
    Note over Agent: Monitor executes...
    Agent->>MB: publish(feedback)
    
    %% Feedback Loop
    alt Feedback indicates issues
        Note over WE: Loop back to DEVELOPMENT
        WE->>AC: dispatch_task(fix_task)
    else No issues
        WE->>SM: save_workflow_state(COMPLETED)
        WE-->>Facade: return WorkflowState
        Facade-->>User: WorkflowState(COMPLETED)
    end
```

## Layer Responsibilities

### 1. Facade Layer
**ConductorAI** - Single entry point
- System initialization and configuration
- Component lifecycle management
- High-level API for users
- Graceful shutdown

### 2. Orchestration Layer
**Workflow Engine** - Multi-phase execution
- Executes workflows phase by phase
- Manages phase transitions
- Handles feedback loops
- Coordinates task dependencies

**Agent Coordinator** - Agent registry & dispatcher
- Registers/unregisters agents
- Finds available agents by type
- Dispatches tasks to agents
- Syncs agent states

**Message Bus** - Pub/Sub communication
- Decouples agent communication
- Supports broadcast and direct messaging
- Request-response pattern
- Dead letter queue

**State Manager** - Persistence
- Stores agent states
- Stores workflow states
- Stores task results
- Supports Redis backend

**Policy Engine** - Rule enforcement
- Validates actions before execution
- Phase gate enforcement
- Concurrency limits
- Agent availability checks

**Error Handler** - Resilience
- Retry with exponential backoff
- Circuit breaker per agent
- Dead letter queue
- Error escalation

### 3. Agent Layer
**BaseAgent** - Abstract template
- Template Method pattern
- Lifecycle management
- State tracking
- Message handling

**Specialized Agents** - Domain experts
- **Development**: Coding, Review, TestData, Test
- **DevOps**: DevOps, Deploying
- **Monitoring**: Monitor

### 4. Infrastructure Layer
**Artifact Store** - Work products
- Stores code, tests, configs, reports
- Query by workflow/task/agent/type
- Supports multiple backends

### 5. Integration Layer
**LLM Providers** - AI integration
- Abstract interface
- Multiple providers (Mock, OpenAI, Anthropic)
- Token tracking
- Response standardization

## Data Flow Patterns

### 1. Task Execution Flow
```
WorkflowDefinition → WorkflowEngine → AgentCoordinator → MessageBus → Agent
Agent → LLM Provider → LLMResponse
Agent → Artifact Store → Artifact
Agent → MessageBus → TaskResult → StateManager
```

### 2. State Persistence Flow
```
Agent updates → AgentState → StateManager → Redis/Memory
Workflow progress → WorkflowState → StateManager → Redis/Memory
Task completion → TaskResult → StateManager → Redis/Memory
```

### 3. Feedback Loop Flow
```
MonitorAgent → analyzes deployment → FeedbackPayload → MessageBus
→ WorkflowEngine → loops back to DEVELOPMENT phase
→ CodingAgent → fixes issues → new code
```

### 4. Error Handling Flow
```
Agent error → ErrorHandler → check CircuitBreaker
→ is_open? → DEAD_LETTER
→ is_retryable? → RETRY with backoff
→ max_retries? → ESCALATE
```

## Key Design Principles

### 1. Separation of Concerns
Each layer has a single, well-defined responsibility:
- **Facade**: User interface
- **Orchestration**: Workflow coordination
- **Agents**: Domain-specific execution
- **Infrastructure**: Persistence
- **Integration**: External services

### 2. Dependency Inversion
High-level modules depend on abstractions:
- Agents depend on `BaseLLMProvider`, not OpenAI
- Coordinator depends on `MessageBus`, not Redis
- All components use abstract interfaces

### 3. Open/Closed Principle
- Add new agents without modifying orchestration
- Add new LLM providers without changing agents
- Add new policies without changing coordinator

### 4. Pub/Sub Decoupling
- Agents never call each other directly
- All communication through MessageBus
- Enables independent scaling and testing

### 5. Template Method Pattern
- BaseAgent defines execution skeleton
- Subclasses implement specific logic
- Consistent behavior across all agents

## Scalability Considerations

### Horizontal Scaling
- Multiple agent instances per type
- Load balancing via coordinator
- Shared state through Redis

### Vertical Scaling
- Configurable concurrency limits
- Policy-based resource management
- Circuit breakers prevent overload

### Performance Optimization
- Artifact caching
- LLM response caching
- Batch task processing
- Async I/O throughout

## Security & Reliability

### Security
- API key management via config
- Artifact access control (future)
- Message authentication (future)

### Reliability
- Retry with exponential backoff
- Circuit breakers per agent
- Dead letter queue
- State persistence
- Graceful degradation

## Configuration & Deployment

### Configuration Hierarchy
```
ConductorConfig
  ├─ LLMConfig (provider, model, API keys)
  ├─ RedisConfig (URL, connection pool)
  └─ Runtime settings (log level, timeouts)
```

### Deployment Options
1. **Development**: InMemory everything, Mock LLM
2. **Testing**: InMemory with real LLM providers
3. **Production**: Redis backend, OpenAI/Anthropic

This architecture provides a flexible, scalable, and maintainable foundation for multi-agent workflows!
