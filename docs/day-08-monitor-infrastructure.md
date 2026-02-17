# Day 8: Monitor Agent & Infrastructure Layer

## Overview

Day 8 completes the agent layer with the final specialized agent and adds
the infrastructure layer for artifact persistence:

- **MonitorAgent** — The sole agent in the MONITORING phase, analyzing
  deployments and generating feedback for the development phase
- **ArtifactStore** — Infrastructure for persisting workflow artifacts
  (code, tests, configs, reports)

With the MonitorAgent, all 7 agent types are implemented and the full
feedback loop is functional:

```
┌──────────┐   ┌──────────┐   ┌────────────┐   ┌──────────┐
│ Coding   │──→│ Review   │──→│ TestData   │──→│ Test     │
│ Agent    │   │ Agent    │   │ Agent      │   │ Agent    │
└──────────┘   └──────────┘   └────────────┘   └──────────┘
                                                     │
                                                     ▼
┌───────────┐   ┌────────────┐                 ┌──────────┐
│ Deploying │←──│ DevOps     │←────────────────│ (next)   │
│ Agent     │   │ Agent      │                 └──────────┘
└─────┬─────┘   └────────────┘
      │
      ▼
┌───────────┐         ┌──────────────────────┐
│ Monitor   │────────→│ Feedback Loop        │
│ Agent     │ issues? │ (re-trigger Coding)  │
└───────────┘         └──────────────────────┘
```

## Components Built

### 1. MonitorAgent (`agents/monitoring/monitor_agent.py`)

Analyzes deployment results and generates structured feedback.

**Role in Pipeline:** The final agent in the workflow. When it detects
issues, the WorkflowEngine triggers the feedback loop back to DEVELOPMENT.

**Input Requirements:**
| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `deployment_result` | Yes | — | Deployment outcome to analyze |
| `metrics` | No | — | Performance metrics data |
| `logs` | No | — | Application logs |
| `previous_feedback` | No | — | Earlier feedback from previous loop |

**Output Structure:**
```python
{
    "analysis": "...",                    # Full LLM analysis text
    "has_issues": True/False,             # Triggers feedback loop
    "severity": "none|low|medium|high|critical",
    "issues": ["issue1", "issue2"],       # Parsed issue list
    "recommendations": ["rec1", "rec2"],  # Parsed recommendations
    "feedback_for_development": "...",    # Summary for dev team
    "llm_model": "mock-model",
    "llm_usage": {...},
}
```

**Response Parsing:** The MonitorAgent includes a `_parse_monitor_response()`
static method that extracts structured data from the LLM's text response:
- **Severity** — extracted via regex from "Severity: [level]" pattern
- **Issues** — extracted from numbered list under "Issues Found" section
- **Recommendations** — extracted from numbered list under "Recommendations"
- **Feedback** — extracted from "Feedback for Development" section
- **has_issues** — True if severity != "none" OR issues list is non-empty

**Feedback Loop Trigger:** The key field is `has_issues`. When True, the
WorkflowEngine's feedback loop mechanism (built in Day 5) re-triggers the
DEVELOPMENT phase with the feedback data.

### 2. ArtifactStore (`infrastructure/artifact_store.py`)

Persistence layer for workflow artifacts.

**What Are Artifacts?** Artifacts are the tangible work products that flow
between agents: generated code, test suites, CI/CD configs, deployment
manifests, monitoring reports, etc.

**Artifact Model:**
```python
class Artifact(BaseModel):
    artifact_id: str     # Auto-generated "art-{uuid4}"
    workflow_id: str     # Which workflow produced it
    task_id: str         # Which task produced it
    agent_id: str        # Which agent produced it
    artifact_type: str   # "code", "test", "config", "deployment", etc.
    content: str         # The actual content
    metadata: dict       # Additional metadata (language, framework, etc.)
    created_at: datetime # UTC timestamp
```

**ArtifactStore ABC:**
| Method | Description |
|--------|-------------|
| `save(artifact)` | Persist an artifact |
| `get(artifact_id)` | Retrieve by ID |
| `list_by_workflow(workflow_id)` | All artifacts for a workflow |
| `list_by_task(task_id)` | All artifacts for a task |
| `list_by_agent(agent_id)` | All artifacts by an agent |
| `list_by_type(artifact_type)` | All artifacts of a type |
| `delete(artifact_id)` | Remove an artifact |
| `count()` | Total artifact count |

**InMemoryArtifactStore:** Dict-based implementation for development/testing.
Not suitable for production (no persistence). Future implementations:
- `RedisArtifactStore` — Redis-backed, for production
- `S3ArtifactStore` — S3-backed, for large artifacts

## Design Decisions

### 1. MonitorAgent Response Parsing
The MonitorAgent uses regex-based parsing to extract structured data from
the LLM's text response. This approach was chosen over JSON parsing because:
- LLMs produce more reliable structured text than valid JSON
- Regex parsing is more forgiving of formatting variations
- The system prompt specifies a clear response format that's easy to parse
- Fallback defaults ensure safe behavior even with unparseable responses

### 2. has_issues as Feedback Trigger
The `has_issues` boolean is the key signal for the feedback loop. It's
determined by two conditions (OR logic):
- severity != "none"
- issues list is non-empty

This dual check ensures issues are caught even if the severity parsing
fails or the LLM uses an unexpected format.

### 3. ArtifactStore as ABC
The ArtifactStore uses the same ABC + InMemory pattern as StateManager
and MessageBus. This ensures:
- All store implementations share the same API
- Tests can use InMemoryArtifactStore (no external deps)
- Production can swap to Redis/S3 without code changes

### 4. Artifact IDs with "art-" Prefix
Artifact IDs are prefixed with "art-" to distinguish them from task IDs,
agent IDs, and workflow IDs. This makes debugging easier when inspecting
logs or storage.

## Package Structure

```
src/conductor/
├── agents/
│   ├── __init__.py              # Exports all 8 agents (BaseAgent + 7 specialized)
│   ├── base.py
│   ├── development/             # 4 agents
│   ├── devops/                  # 2 agents
│   └── monitoring/
│       ├── __init__.py          # Day 8 ← NEW
│       └── monitor_agent.py     # Day 8 ← NEW
└── infrastructure/
    ├── __init__.py              # Day 8 ← NEW
    └── artifact_store.py        # Day 8 ← NEW (Artifact, ArtifactStore, InMemoryArtifactStore)
```

## Test Coverage

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_monitor_agent.py` | 40 | Init, validation, execution, parsing, LLM, errors, prompts |
| `test_artifact_store.py` | 25 | Model, save/get, list queries, delete, count |
| **Day 8 Total** | **65** | |
| **Cumulative** | **569** | |

## All 7 Agent Types — Complete!

| AgentType | Agent Class | Phase | Day |
|-----------|-------------|-------|-----|
| `CODING` | CodingAgent | Development | 6 |
| `REVIEW` | ReviewAgent | Development | 6 |
| `TEST_DATA` | TestDataAgent | Development | 7 |
| `TEST` | TestAgent | Development | 7 |
| `DEVOPS` | DevOpsAgent | DevOps | 7 |
| `DEPLOYING` | DeployingAgent | DevOps | 7 |
| `MONITOR` | MonitorAgent | Monitoring | 8 |

## What's Next (Day 9)

Day 9 will add:
- **ConductorAI Facade** — the top-level entry point that ties everything together
- **Notification Integration** — webhook/email notifications for workflow events
- **End-to-end workflow test** — a complete workflow using all agents
