# Day 11: .context/ Directory Generation System

## Overview

Day 11 implements the `.context/` directory generation system described in
[pipeline-yaml-to-zip.md](./pipeline-yaml-to-zip.md). This system ensures every
generated code package ships with full traceability — architectural decisions,
confidence scores, infrastructure bindings, runbooks, and known gaps.

The key principle: **the agent that did the work explains the work.** There is no
separate documentation agent. Each agent contributes context entries for the
decisions it made, and the ContextBundler assembles them into the final directory.

```
┌─────────────┐                    ┌─────────────────┐
│ CodingAgent │ ── context ──→     │  ArtifactStore   │
│ DevOpsAgent │ ── context ──→     │  (type=context)  │
│ TestAgent   │ ── context ──→     └────────┬────────┘
└─────────────┘                             │
                                            ↓
                                ┌─────────────────────┐
                                │   ContextBundler     │
                                │  bundle(workflow_id) │
                                └──────────┬──────────┘
                                           │
                                           ↓
                                dict[str, str]
                                {
                                  "decisions.md": "# ...",
                                  "runbook.md": "# ...",
                                  ...
                                }
```

## Components Built

### 1. ContextEntry Model (`core/context_models.py`)

Pydantic model representing a single agent contribution to a `.context/` file.

| Field | Type | Description |
|-------|------|-------------|
| `context_file` | `str` | Target filename (e.g., `"decisions.md"`) |
| `section_heading` | `str` | Markdown heading for this section |
| `content` | `str` | Markdown body content |
| `agent_id` | `str` | Which agent produced this entry |
| `confidence` | `Optional[float]` | Agent confidence 0.0–1.0 |

**Context File Mapping:**

| File | Contributing Agents |
|------|-------------------|
| `decisions.md` | CodingAgent + DevOpsAgent |
| `traceability.md` | CodingAgent |
| `infra-bindings.md` | DevOpsAgent |
| `confidence-report.md` | CodingAgent + ReviewAgent |
| `runbook.md` | DevOpsAgent |
| `known-gaps.md` | CodingAgent + TestAgent |

### 2. ContextContribution (`core/context_models.py`)

Wrapper holding a list of `ContextEntry` objects produced by a single agent
during task execution. Returned from `BaseAgent._generate_context()`.

```python
class ContextContribution(BaseModel):
    entries: list[ContextEntry] = []
    agent_id: str
    task_id: str
```

### 3. ContextBundler (`infrastructure/context_bundler.py`)

Post-workflow assembly step that reads context artifacts from the ArtifactStore,
groups them by target file, and produces final markdown content.

**Usage:**
```python
bundler = ContextBundler(artifact_store)
context_files = await bundler.bundle("wf-001")

# context_files is:
# {
#   "decisions.md": "# Architectural Decision Record\n\n...",
#   "confidence-report.md": "# AI Confidence Report\n\n...",
# }
```

**How it works:**
1. Fetch all artifacts with `artifact_type="context"` for the workflow
2. Parse each artifact's content as a `ContextEntry` (JSON)
3. Group entries by `context_file`
4. For each canonical file that has contributions, assemble:
   - File header
   - Section heading
   - Agent attribution line
   - Section content
   - Confidence score (if present)
   - Separator

Only files with at least one contribution appear in the output.

### 4. BaseAgent Integration

The `BaseAgent._generate_context()` hook is called after `_execute()` completes
successfully. Each agent subclass can override it to produce context entries:

```python
async def _generate_context(self, task, result) -> ContextContribution:
    return ContextContribution(
        entries=[
            ContextEntry(
                context_file="decisions.md",
                section_heading="## Code Architecture",
                content="Chose repository pattern for...",
                agent_id=self._identity.agent_id,
                confidence=0.85,
            )
        ],
        agent_id=self._identity.agent_id,
        task_id=task.task_id,
    )
```

## Design Decisions

### Agent-Owned Context
Each agent writes context for its own domain. CodingAgent knows code decisions,
DevOpsAgent knows infrastructure choices, TestAgent knows coverage gaps. This
avoids a centralized documentation agent that would need to understand all domains.

### Artifact Store as Transport
Context entries are stored as regular artifacts with `artifact_type="context"`.
This reuses existing infrastructure — no new storage mechanism needed.

### Canonical File Set
The six `.context/` files are defined as constants in `CONTEXT_FILES`. Only
files that receive contributions appear in the output. This prevents empty
placeholder files while keeping a predictable structure.

### Confidence Scoring
Every context entry can carry a confidence score. The ContextBundler renders
these as blockquotes in the markdown. Teams can use confidence scores to
prioritize review effort.

## Package Structure

```
src/conductor/
├── core/
│   └── context_models.py         ← NEW (ContextEntry, ContextContribution)
└── infrastructure/
    └── context_bundler.py        ← NEW (ContextBundler, CONTEXT_FILES)
```

## Test Coverage

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_context_models.py` | 12 | ContextEntry, ContextContribution validation |
| `test_context_bundler.py` | 10 | Bundle assembly, grouping, empty workflows |
| `test_context_generation.py` | 10 | BaseAgent context hooks, integration flow |
| **Total** | **32** | |
