Architecture Layers:

Orchestration Layer - Workflow Engine, Agent Coordinator, Message Bus, State Manager, Policy Engine, Error Handler
Agent Layer - Three phases:

Development: Coding Agent → Review Agent, Test Data Agent → Test Agent
DevOps: DevOps Agent (handles all CI/CD, testing) + Deploying Agent
Monitoring: Monitor Agent with feedback loops back to development


Data & Infrastructure - Code repos, metadata, test data, logs/metrics, knowledge base
Integration Layer - Cloud, containers, CI/CD tools, observability, LLMs, notifications

Key Flows:

Sequential workflow (solid arrows): Dev → DevOps → Monitor
Feedback loop (red dashed): Monitor findings flow back to Dev phase
Data flows (dotted): Agents persist to storage layers
Orchestration control (orange): Coordinating all agents
