# ConductorAI Architecture Overview

## Table of Contents
1. [System Purpose](#system-purpose)
2. [Architecture Diagram (ASCII)](#architecture-diagram)
3. [Layer 1: Orchestration Layer](#layer-1-orchestration-layer)
4. [Layer 2: Agent Layer](#layer-2-agent-layer)
5. [Layer 3: Data & Infrastructure Layer](#layer-3-data--infrastructure-layer)
6. [Layer 4: Integration & External Services Layer](#layer-4-integration--external-services-layer)
7. [Data Flows](#data-flows)
8. [Key Design Decisions](#key-design-decisions)
9. [Technology Choices](#technology-choices)

---

## System Purpose

ConductorAI is a **Multi-Agent AI Framework** that orchestrates specialized AI agents
through a software development lifecycle pipeline:

```
Code → Test → Deploy → Review → Monitor
```

The framework automates the development-to-production pipeline by coordinating
AI agents that each specialize in one task (coding, reviewing, testing, deploying,
monitoring). A central orchestration layer manages the flow, and a feedback loop
from monitoring back to development enables self-healing and continuous improvement.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-AGENT AI FRAMEWORK ARCHITECTURE                    │
│                    Code → Test → Deploy → Review → Monitor                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────── ORCHESTRATION LAYER ──────────────────────────┐    │
│  │                                                                     │    │
│  │  ┌──────────┐ ┌─────────────┐ ┌───────────┐ ┌──────────────┐     │    │
│  │  │ Workflow  │ │    Agent    │ │  Message   │ │    State     │     │    │
│  │  │  Engine   │ │ Coordinator │ │    Bus     │ │   Manager    │     │    │
│  │  └──────────┘ └─────────────┘ └───────────┘ └──────────────┘     │    │
│  │  ┌──────────────┐  ┌──────────────┐                               │    │
│  │  │ Policy Engine │  │ Error Handler │                               │    │
│  │  └──────────────┘  └──────────────┘                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │ (orange: orchestration control)                                  │
│           ▼                                                                  │
│  ┌───────────────────── AGENT LAYER ──────────────────────────────────┐    │
│  │                  Specialized AI Agents                              │    │
│  │                                                                     │    │
│  │  ┌─── DEVELOPMENT PHASE ──┐  ┌── DEVOPS ──┐  ┌── MONITORING ──┐  │    │
│  │  │                         │  │             │  │                │  │    │
│  │  │  ┌────────┐ ┌────────┐ │  │ ┌─────────┐│  │  ┌───────────┐│  │    │
│  │  │  │Coding  │→│Review  │ │  │ │ DevOps  ││  │  │  Monitor  ││  │    │
│  │  │  │Agent   │ │Agent   │ │──│ │ Agent   ││──│  │  Agent    ││  │    │
│  │  │  └────────┘ └────────┘ │  │ └─────────┘│  │  └───────────┘│  │    │
│  │  │  ┌────────┐ ┌────────┐ │  │ ┌─────────┐│  │       │       │  │    │
│  │  │  │TestData│→│ Test   │ │  │ │Deploying││  │       │       │  │    │
│  │  │  │Agent   │ │Agent   │ │  │ │Agent    ││  │  feedback     │  │    │
│  │  │  └────────┘ └────────┘ │  │ └─────────┘│  │  loop (red)   │  │    │
│  │  └─────────────────────────┘  └─────────────┘  └───────│───────┘  │    │
│  │          ▲                                              │          │    │
│  │          └──────────────────────────────────────────────┘          │    │
│  │                      (red dashed: feedback)                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │ (dotted: data flows)                                            │
│           ▼                                                                  │
│  ┌───────────────── DATA & INFRASTRUCTURE LAYER ─────────────────────┐    │
│  │                                                                     │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ ┌───────────┐│    │
│  │  │   Code   │ │ Metadata │ │ Test Data│ │Logs &  │ │ Knowledge ││    │
│  │  │Repository│ │  Store   │ │  Store   │ │Metrics │ │   Base    ││    │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ └───────────┘│    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────── INTEGRATION & EXTERNAL SERVICES LAYER ─────────────────┐    │
│  │                                                                     │    │
│  │  ┌───────┐ ┌────────────┐ ┌───────┐ ┌─────────────┐ ┌──────────┐│    │
│  │  │ Cloud │ │ Containers │ │ CI/CD │ │Observability│ │   LLMs   ││    │
│  │  └───────┘ └────────────┘ └───────┘ └─────────────┘ └──────────┘│    │
│  │  ┌───────────────┐                                               │    │
│  │  │ Notifications │                                               │    │
│  │  └───────────────┘                                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

Legend:
  ────→  Sequential workflow (solid arrows)
  - - →  Feedback loop (red dashed - Monitor → Development)
  ·····  Data flows (agents persist to storage)
  █████  Orchestration control (orange - coordinator manages all agents)
```

---

## Layer 1: Orchestration Layer

The Orchestration Layer is the "brain" of ConductorAI. It controls what happens,
when, and in what order. No agent communicates directly with another — all
coordination flows through this layer.

### Components

| Component | Responsibility | Key Pattern |
|-----------|---------------|-------------|
| **Workflow Engine** | Defines and executes multi-phase pipelines (DAG) | DAG execution, dependency resolution |
| **Agent Coordinator** | Manages agent lifecycle, dispatches tasks | Registry pattern, task routing |
| **Message Bus** | Asynchronous agent communication | Pub/Sub, request-response |
| **State Manager** | Persists workflow and agent state | Repository pattern, Redis-backed |
| **Policy Engine** | Enforces rules before actions execute | Chain of responsibility |
| **Error Handler** | Retries, circuit breaking, dead letter queue | Retry with backoff, circuit breaker |

### Why Centralized Orchestration?

We chose centralized orchestration (coordinator controls everything) over
decentralized (agents communicate directly) because:

1. **Visibility**: One place to see entire workflow state
2. **Debugging**: Single point of control simplifies troubleshooting
3. **Policy enforcement**: Rules checked in one place, not scattered
4. **Feedback loops**: Centralized coordinator can re-route workflows
5. **Error handling**: Consistent retry/circuit-breaker behavior

---

## Layer 2: Agent Layer

The Agent Layer contains 7 specialized AI agents organized into 3 phases.
All agents inherit from `BaseAgent`, which provides the lifecycle template.

### Phase 1: Development

```
Coding Agent  ──→  Review Agent
                       │
                       ▼
Test Data Agent ──→  Test Agent
```

- **Coding Agent**: Generates or modifies source code using LLM
- **Review Agent**: Reviews code for quality, bugs, best practices
- **Test Data Agent**: Generates test data and fixtures
- **Test Agent**: Creates and runs test suites

### Phase 2: DevOps

```
DevOps Agent  ──→  Deploying Agent
```

- **DevOps Agent**: Creates CI/CD pipelines, Dockerfiles, infrastructure configs
- **Deploying Agent**: Handles deployment to target environments

### Phase 3: Monitoring & Feedback

```
Monitor Agent  ──→  (feedback) ──→  Development Phase
```

- **Monitor Agent**: Analyzes metrics, detects anomalies, generates feedback
- When issues are found, triggers the feedback loop back to Development

### Agent Lifecycle (Template Method Pattern)

Every agent follows the same lifecycle, enforced by `BaseAgent`:

```
1. start()           → Initialize agent, set IDLE status
2. execute_task()    → Template method:
   a. _validate_task()  → Check task is valid for this agent
   b. Set status RUNNING
   c. _execute()        → Agent-specific logic (abstract method)
   d. Set status COMPLETED or FAILED
   e. Return TaskResult
3. stop()            → Graceful shutdown
```

---

## Layer 3: Data & Infrastructure Layer

This layer provides persistent storage for all data flowing through the system.

| Store | Purpose | Data Examples |
|-------|---------|---------------|
| **Code Repository** | Stores generated/modified code | Source files, versions, diffs |
| **Metadata Store** | Stores execution metadata | Agent history, workflow configs |
| **Test Data Store** | Stores test fixtures and data | Generated test datasets |
| **Logs & Metrics** | Observability data | Agent logs, execution metrics, traces |
| **Knowledge Base** | Historical knowledge for learning | Past successes/failures, patterns |

All stores implement a common `StorageBackend` interface with InMemory and Redis
implementations, allowing easy swapping between development and production.

---

## Layer 4: Integration & External Services Layer

This layer provides abstracted interfaces to external services:

| Service | Purpose | Implementations |
|---------|---------|-----------------|
| **LLMs** | AI model access (GPT-4, Claude, etc.) | OpenAI, Anthropic, Mock |
| **Cloud** | Cloud provider APIs | AWS, GCP, Azure, Mock |
| **Containers** | Container orchestration | Docker, Kubernetes, Mock |
| **CI/CD** | Pipeline automation | GitHub Actions, GitLab CI, Mock |
| **Observability** | External monitoring | Prometheus, Jaeger, Mock |
| **Notifications** | Alert delivery | Console, Webhook, Slack |

Every integration has an Abstract Base Class and a Mock implementation for
testing without external dependencies.

---

## Data Flows

### 1. Sequential Workflow (Solid Arrows)

The primary flow moves left to right through all three phases:

```
Development          DevOps            Monitoring
┌───────────┐    ┌──────────┐    ┌──────────────┐
│ Code      │    │ Build    │    │ Monitor      │
│ Review    │ ──→│ Deploy   │ ──→│ Analyze      │
│ Test      │    │          │    │ Report       │
└───────────┘    └──────────┘    └──────────────┘
```

### 2. Feedback Loop (Red Dashed)

When the Monitor Agent detects issues, it sends feedback back to Development:

```
Monitor Agent
    │
    │ FeedbackPayload (findings, severity, recommendations)
    │
    ▼
Workflow Engine._handle_feedback()
    │
    │ Re-trigger Development Phase
    │
    ▼
Coding Agent (fix based on feedback)
```

### 3. Data Flows (Dotted Lines)

Every agent persists its work to the infrastructure layer:

```
Coding Agent    → Code Repository (stores generated code)
Review Agent    → Metadata Store (stores review findings)
Test Agent      → Test Data Store (stores test results)
DevOps Agent    → Metadata Store (stores pipeline configs)
Monitor Agent   → Logs & Metrics (stores monitoring data)
All Agents      → Knowledge Base (stores lessons learned)
```

### 4. Orchestration Control (Orange)

The Coordinator controls all agents through the Message Bus:

```
Agent Coordinator
    │
    ├──→ Message Bus ──→ Coding Agent
    ├──→ Message Bus ──→ Review Agent
    ├──→ Message Bus ──→ Test Agent
    ├──→ Message Bus ──→ DevOps Agent
    ├──→ Message Bus ──→ Deploying Agent
    └──→ Message Bus ──→ Monitor Agent
```

---

## Key Design Decisions

### 1. Abstract Base Classes Everywhere

Every major component has an ABC with at least two implementations:
- **InMemory**: For development and testing (no external dependencies)
- **Redis/Real**: For staging and production

This means the entire system can run without Redis, Docker, or any cloud service.

### 2. Pydantic Models at All Boundaries

All data flowing between components uses Pydantic models:
- Automatic validation catches bugs early
- JSON serialization for Redis storage and API responses
- IDE auto-completion from type hints
- Self-documenting field descriptions

### 3. Async-First Design

All agents, the message bus, and the workflow engine use `async/await`:
- Non-blocking I/O for LLM API calls (which are slow)
- Concurrent agent execution within a phase
- Efficient resource usage under load

### 4. Configuration-Driven Behavior

The `ConductorConfig` controls everything:
- Which backends to use (InMemory vs Redis)
- Which LLM provider to use
- Retry counts, timeouts, log levels
- Environment-specific defaults

---

## Technology Choices

| Technology | Purpose | Why This Choice |
|-----------|---------|-----------------|
| **Python 3.11+** | Language | Modern typing (str \| None), asyncio maturity |
| **Pydantic v2** | Data validation | Fast, type-safe, great serialization |
| **Redis** | Message bus + state | Proven pub/sub, fast key-value store |
| **httpx** | HTTP client | Async support, modern API, type hints |
| **structlog** | Logging | Structured JSON logs, context binding |
| **pytest** | Testing | De facto standard, excellent async support |
