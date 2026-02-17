# ConductorAI Documentation

Welcome to the ConductorAI documentation. This folder contains comprehensive
documentation for every component in the framework, organized by build day.

## Documentation Index

### Architecture & Design
- **[Architecture Overview](./architecture-overview.md)** - Complete system architecture,
  layer descriptions, data flows, and design decisions

### Build Log (Day-by-Day)
Each build day adds new components with detailed documentation:

| Day | Topic | Components | Status |
|-----|-------|------------|--------|
| [Day 01](./day-01-foundations.md) | Foundations | Config, Enums, Models, Exceptions | ✅ Complete |
| [Day 02](./day-02-core-abstractions.md) | Core Abstractions | BaseAgent, Messages, State | ✅ Complete |
| [Day 03](./day-03-message-bus-state.md) | Communication | MessageBus, StateManager | ✅ Complete |
| [Day 04](./day-04-error-handler-policy-engine.md) | Resilience | ErrorHandler, PolicyEngine | ✅ Complete |
| [Day 05](./day-05-coordinator-workflow.md) | Orchestration | Coordinator, WorkflowEngine | ✅ Complete |
| [Day 06](./day-06-dev-agents-llm.md) | Dev Agents + LLM | CodingAgent, ReviewAgent, LLMProvider | ✅ Complete |
| [Day 07](./day-07-test-devops-agents.md) | Test & DevOps | TestDataAgent, TestAgent, DevOpsAgent, DeployingAgent | ✅ Complete |
| [Day 08](./day-08-monitor-infrastructure.md) | Monitor & Infra | MonitorAgent, ArtifactStore, Feedback Loop | ✅ Complete |
| [Day 09](./day-09-integrations-facade.md) | Facade | ConductorAI Facade, Public API | ✅ Complete |
| [Day 10](./day-10-end-to-end.md) | E2E & Polish | Examples, Full Docs, Integration Tests | 🔲 Pending |

### Reference Guides (Built in Day 10)
- **[Getting Started](./getting-started.md)** - Installation, quick start, first workflow
- **[API Reference](./api-reference.md)** - Complete API docs for all public classes
- **[Extending ConductorAI](./extending-conductorai.md)** - Custom agents, providers, policies

## How to Read This Documentation

**If you're new to ConductorAI**, start with:
1. [Architecture Overview](./architecture-overview.md) — understand the big picture
2. [Day 01](./day-01-foundations.md) — understand the foundation
3. [Getting Started](./getting-started.md) — run your first workflow (available after Day 10)

**If you're contributing**, read the day logs in order — each day builds on
the previous, explaining design decisions and tradeoffs.

**If you're extending ConductorAI**, jump to:
1. [Extending ConductorAI](./extending-conductorai.md) — add custom agents, providers, policies
2. The specific day log for the component you're modifying

## Documentation Conventions

- All code examples use Python 3.11+ syntax
- Async examples use `async/await` (ConductorAI is async-first)
- Architecture diagrams use ASCII art for portability
- Each day's doc explains WHAT was built, WHY, and HOW it connects
