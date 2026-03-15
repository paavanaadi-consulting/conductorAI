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
| [Day 10](./day-10-end-to-end.md) | E2E & Polish | Examples, Integration Tests, Conftest | ✅ Complete |
| [Day 11](./day-11-context-generation.md) | Context Generation | ContextEntry, ContextContribution, ContextBundler | ✅ Complete |
| [Day 12](./day-12-templates-infra.md) | Templates & Infra | Business Requirement Templates, Infrastructure Dictionaries | ✅ Complete |
| [Day 13](./day-13-pipeline-yaml-generator.md) | Pipeline Generator | PipelineYamlGeneratorAgent, Schema Extractor, Validators | ✅ Complete |

### Pipeline & Strategy
- **[Pipeline: YAML to ZIP](./pipeline-yaml-to-zip.md)** - End-to-end pipeline from
  unstructured business requirements to production-ready code packages. Covers the
  infrastructure registry, business intake templates, `.context/` handoff package,
  agent ownership model, and developer workflow from ZIP to production.
- **[Business Requirement Templates & Infrastructure Dictionaries](./day-12-templates-infra.md)** -
  Simplified YAML intake forms for business stakeholders and structured infrastructure
  inventories for IT teams. The two inputs that feed pipeline generation.
- **[Pipeline YAML Generator](./day-13-pipeline-yaml-generator.md)** - The YAML
  generation engine that auto-detects pipeline type from requirements, loads schema
  skeletons, and produces complete pipeline specifications via LLM.

### Corporate Deployment & Operations
- **Security & Access Control**
  - [Security Audit Checklist](./operations/security-audit-checklist.md) - Dependency scanning, secret management, container security, LLM prompt injection
  - [Penetration Testing Guide](./operations/penetration-testing-guide.md) - Scope, test categories, tools, reporting template
  - [SOC2 Compliance Checklist](./operations/soc2-compliance-checklist.md) - Trust Service Criteria mapping, RBAC, change management
  - [Data Governance Policy](./operations/data-governance-policy.md) - Classification, retention, encryption, GDPR/CCPA for AI
- **Infrastructure & Deployment**
  - [Kubernetes Manifests](../deploy/k8s/README.md) - K8s deployment with namespace, configmap, secret, HPA, PDB
  - [Helm Chart](../deploy/helm/conductorai/README.md) - Templated K8s deployment with values.yaml
  - [Terraform Templates](../deploy/terraform/README.md) - AWS EKS + ElastiCache infrastructure-as-code
- **Observability**
  - [Grafana Dashboards](../deploy/grafana/README.md) - Overview and LLM metrics dashboards
  - [Prometheus Alerts](../deploy/prometheus/README.md) - Alerting rules for workflows, tasks, agents, LLM, Redis
- **Operations & Reliability**
  - [Disaster Recovery](./operations/disaster-recovery.md) - RPO/RTO, Redis backup, state reconstruction, failover
  - [Load Testing Guide](./operations/load-testing-guide.md) - Scenarios, tools, baseline metrics, sample scripts
  - [Performance Tuning](./operations/performance-tuning.md) - Redis, asyncio, LLM, memory profiling
- **Runbooks**
  - [Redis Connection Failure](./operations/runbooks/redis-connection-failure.md)
  - [LLM Provider Outage](./operations/runbooks/llm-provider-outage.md)
  - [Workflow Stuck In Progress](./operations/runbooks/workflow-stuck-in-progress.md)
  - [High Error Rate](./operations/runbooks/high-error-rate.md)
  - [Agent Registration Failure](./operations/runbooks/agent-registration-failure.md)

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
