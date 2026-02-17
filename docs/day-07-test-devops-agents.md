# Day 7: Test & DevOps Agents

## Overview

Day 7 completes the remaining four specialized agents across two workflow phases:

- **Development Phase** (final 2 agents): TestDataAgent, TestAgent
- **DevOps Phase** (both agents): DevOpsAgent, DeployingAgent

After Day 7, all agent types except MonitorAgent are implemented. The full
Development → DevOps pipeline is functional.

```
DEVELOPMENT PHASE (complete)         DEVOPS PHASE (complete)
┌──────────┐   ┌──────────┐   ┌────────────┐   ┌──────────┐   ┌───────────┐   ┌────────────┐
│ Coding   │──→│ Review   │──→│ TestData   │──→│ Test     │──→│ DevOps    │──→│ Deploying  │
│ Agent    │   │ Agent    │   │ Agent      │   │ Agent    │   │ Agent     │   │ Agent      │
│ (Day 6)  │   │ (Day 6)  │   │ (Day 7)   │   │ (Day 7)  │   │ (Day 7)   │   │ (Day 7)    │
└──────────┘   └──────────┘   └────────────┘   └──────────┘   └───────────┘   └────────────┘
```

## Components Built

### 1. TestDataAgent (`agents/development/test_data_agent.py`)

Generates test data, fixtures, and edge-case values for source code.

**Role in Pipeline:** Sits between ReviewAgent and TestAgent. Takes reviewed code
and produces realistic test data that TestAgent can incorporate into its tests.

**Input Requirements:**
| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `code` | Yes | — | Source code to generate test data for |
| `language` | No | `"python"` | Target programming language |
| `data_format` | No | `"fixtures"` | Output format (fixtures, factories, json, csv, parametrize) |

**Output Structure:**
```python
{
    "test_data": "...",        # Generated fixtures / test data
    "format": "fixtures",      # Data format used
    "language": "python",      # Language of the test data
    "llm_model": "mock-model", # Which LLM was used
    "llm_usage": {...},        # Token usage stats
}
```

**System Prompt Strategy:** Uses `TEST_DATA_SYSTEM_PROMPT` which instructs the LLM
to act as a test data engineer, producing comprehensive data covering normal cases,
edge cases, boundary values, and error cases.

### 2. TestAgent (`agents/development/test_agent.py`)

Creates comprehensive test suites for source code.

**Role in Pipeline:** Final agent in the DEVELOPMENT phase. Takes code (and
optionally test data from TestDataAgent) and produces a complete test suite.

**Input Requirements:**
| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `code` | Yes | — | Source code to write tests for |
| `language` | No | `"python"` | Target programming language |
| `test_framework` | No | `"pytest"` | Test framework (pytest, unittest, jest, mocha, junit) |
| `test_data` | No | — | Pre-generated test data from TestDataAgent |

**Output Structure:**
```python
{
    "tests": "...",               # Generated test suite code
    "test_framework": "pytest",   # Framework used
    "language": "python",         # Language of tests
    "llm_model": "mock-model",
    "llm_usage": {...},
}
```

**Test Data Integration:** When `test_data` is provided in the input, the TestAgent
includes it in the LLM prompt under a "Test Data / Fixtures" section, allowing the
LLM to incorporate the pre-generated data into the test suite.

### 3. DevOpsAgent (`agents/devops/devops_agent.py`)

Generates CI/CD configurations, Dockerfiles, and infrastructure configs.

**Role in Pipeline:** Entry point of the DEVOPS phase. Receives code or a project
description and produces CI/CD pipeline configurations.

**Input Requirements:**
| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `code` | At least one | — | Source code to create CI/CD for |
| `project_description` | At least one | — | Project description |
| `platform` | No | `"github_actions"` | Target CI/CD platform |
| `language` | No | `"python"` | Project language |
| `additional_requirements` | No | — | Extra constraints |

**Platform-to-Filename Mapping:**
```python
PLATFORM_FILENAMES = {
    "github_actions": ".github/workflows/ci.yml",
    "docker": "Dockerfile",
    "gitlab_ci": ".gitlab-ci.yml",
    "jenkins": "Jenkinsfile",
}
```

**Flexible Validation:** Unlike other agents, DevOpsAgent accepts either `code`
OR `project_description` — at least one must be provided. This allows it to
generate configs from code analysis or from a high-level description.

### 4. DeployingAgent (`agents/devops/deploying_agent.py`)

Generates deployment configurations and scripts for target environments.

**Role in Pipeline:** Second agent in the DEVOPS phase. Receives a target
environment and produces deployment configurations.

**Input Requirements:**
| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `target_environment` | Yes | — | Deploy target (staging, production, etc.) |
| `deployment_type` | No | `"kubernetes"` | Deployment technology |
| `code` | No | — | Source code for context |
| `config` | No | — | CI/CD config from DevOpsAgent |

**Deployment Type-to-Filename Mapping:**
```python
DEPLOYMENT_TYPE_FILENAMES = {
    "kubernetes": "deployment.yaml",
    "docker_compose": "docker-compose.yml",
    "terraform": "main.tf",
    "ansible": "playbook.yml",
}
```

## Design Decisions

### 1. Consistent Agent Pattern
All four agents follow the exact same pattern established by CodingAgent and
ReviewAgent in Day 6:
- Constructor takes `(agent_id, config, *, llm_provider, name?, description?)`
- `_validate_task()` checks for required input_data fields
- `_execute()` builds prompts → calls LLM → packages result
- `_on_start()` validates the LLM provider
- `_build_user_prompt()` is a `@staticmethod` for easy testing

This consistency makes the codebase predictable and easy to extend.

### 2. TestData → Test Pipeline
TestDataAgent and TestAgent are designed to work together but are also
independently usable. TestAgent can accept pre-generated `test_data` from
TestDataAgent, but it works perfectly fine without it (just generates tests
from the code alone). This loose coupling follows the pipeline pattern where
each agent adds value but doesn't create hard dependencies.

### 3. DevOpsAgent Accepts Either Code or Description
Unlike development agents that strictly require code, DevOpsAgent accepts
either `code` or `project_description`. This flexibility is important because:
- Early in a project, you might only have a description
- Later, the CI/CD config can be generated from actual code
- It supports both top-down and bottom-up workflows

### 4. Platform/Deployment Type Filename Mappings
Both DevOpsAgent and DeployingAgent use dictionaries to map platform/deployment
types to output filenames. Unknown types get sensible fallback filenames using
Python's `dict.get(key, default)` pattern.

## Package Structure

```
src/conductor/agents/
├── __init__.py              # Exports all 6 agents (BaseAgent + 5 specialized)
├── base.py                  # BaseAgent ABC
├── development/
│   ├── __init__.py          # Exports CodingAgent, ReviewAgent, TestDataAgent, TestAgent
│   ├── coding_agent.py      # Day 6
│   ├── review_agent.py      # Day 6
│   ├── test_data_agent.py   # Day 7 ← NEW
│   └── test_agent.py        # Day 7 ← NEW
└── devops/
    ├── __init__.py          # Day 7 ← NEW — Exports DevOpsAgent, DeployingAgent
    ├── devops_agent.py      # Day 7 ← NEW
    └── deploying_agent.py   # Day 7 ← NEW
```

## Test Coverage

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_test_data_agent.py` | 28 | Init, validation, execution, LLM interaction, errors, prompts |
| `test_test_agent.py` | 31 | Init, validation, execution, test data integration, LLM, errors, prompts |
| `test_devops_agent.py` | 33 | Init, validation, execution, platforms, LLM, errors, prompts |
| `test_deploying_agent.py` | 34 | Init, validation, execution, deployment types, LLM, errors, prompts |
| **Day 7 Total** | **126** | |
| **Cumulative** | **504** | |

### Pytest Warnings
Two cosmetic `PytestCollectionWarning` messages appear because `TestAgent` and
`TestDataAgent` class names start with "Test" — pytest tries to collect them as
test classes but skips them because they have `__init__` constructors. These are
harmless and expected.

## AgentType → Agent Class Mapping (Complete)

| AgentType | Agent Class | Phase | Day |
|-----------|-------------|-------|-----|
| `CODING` | CodingAgent | Development | 6 |
| `REVIEW` | ReviewAgent | Development | 6 |
| `TEST_DATA` | TestDataAgent | Development | 7 |
| `TEST` | TestAgent | Development | 7 |
| `DEVOPS` | DevOpsAgent | DevOps | 7 |
| `DEPLOYING` | DeployingAgent | DevOps | 7 |
| `MONITOR` | MonitorAgent | Monitoring | 8 (pending) |

## What's Next (Day 8)

Day 8 will add:
- **MonitorAgent** — the final specialized agent (monitoring phase)
- **Infrastructure Layer** — storage, repositories, observability
- **Feedback Loop** — MonitorAgent → Development phase re-trigger
