# Day 13: PipelineYamlGeneratorAgent

## Overview

Day 13 implements the YAML Generation Engine from [pipeline-yaml-to-zip.md](./pipeline-yaml-to-zip.md)
Step 3 — the component that takes a filled-in requirements YAML and an infrastructure
dictionary, auto-detects the pipeline type, and generates a complete pipeline
specification YAML matching the full template format.

This is the bridge between business inputs (Day 12) and ConductorAI's code
generation agents:

```
┌────────────────────┐    ┌──────────────────────┐
│ requirements.yaml  │    │ infrastructure.yaml   │
│ (30-60 lines)      │    │ (available infra)     │
└────────┬───────────┘    └───────────┬──────────┘
         │                            │
         └──────────┬─────────────────┘
                    ▼
    ┌───────────────────────────────┐
    │  PipelineYamlGeneratorAgent   │
    │                               │
    │  1. Parse inputs              │
    │  2. Auto-detect pipeline type │
    │  3. Load schema skeleton      │
    │  4. LLM generation            │
    │  5. Validate + repair         │
    └───────────────┬───────────────┘
                    ▼
         ┌──────────────────┐
         │ pipeline.yaml     │
         │ (500-2300 lines)  │
         │ + decisions.md    │
         │ + confidence.md   │
         └──────────────────┘
```

## Components Built

### 1. PipelineYamlGeneratorAgent (`agents/pipeline/pipeline_yaml_generator.py`)

The main agent, following the exact same `BaseAgent` template method pattern as
CodingAgent, ReviewAgent, and all other agents.

**Agent Type:** `AgentType.PIPELINE_GENERATOR`

**Constructor:**
```python
PipelineYamlGeneratorAgent(
    agent_id="pipeline-gen-001",
    config=config,
    llm_provider=provider,
    templates_dir=Path("templates/"),  # optional, auto-detected
    name="PipelineYamlGenerator",
    description="Generates pipeline YAML from requirements + infra",
)
```

**Task Input:**
| Field | Required | Description |
|-------|----------|-------------|
| `requirements_yaml` | Yes | Raw YAML string from `templates/requirements/` |
| `infra_yaml` | Yes | Raw YAML string from `templates/infrastructure/` |
| `pipeline_type` | No | Override auto-detection (default: `"auto"`) |

**Task Output:**
| Field | Description |
|-------|-------------|
| `pipeline_yaml` | Complete pipeline YAML string (500-2300 lines) |
| `pipeline_type` | Detected or specified type |
| `detection_confidence` | Auto-detection confidence score (0.0-1.0) |
| `validation_result` | Validation report (valid, errors, warnings, sections) |
| `sections_generated` | List of top-level sections in the output |
| `llm_model` | Model used for generation |
| `llm_usage` | Token usage statistics |

### 2. Pipeline Type Auto-Detection

The agent scores each pipeline type by counting indicator key matches in the
requirements YAML. Each type has a set of indicator keys and bonus value matches.

**Indicator Keys:**

| Type | Indicator Keys |
|------|---------------|
| `data_pipeline` | `pipeline_type`, `sources`, `destination`, `schedule`, `data_sources`, `transformations` |
| `ml_pipeline` | `problem_type`, `ml_type`, `training_data`, `model_requirements`, `deployment`, `retraining` |
| `rag_llm` | `project_type`, `knowledge_sources`, `quality` (with `hallucination_tolerance`), `retrieval`, `llm` |
| `agentic_ops` | `agent_architecture`, `agents`, `autonomy_rules`, `safety`, `orchestration_pattern` |
| `integration` | `integration_type`, `existing_systems`, `target`, `strategy`, `rollback`, `migration` |

**Scoring:**
- Each present indicator key: +1 point
- Bonus value matches (e.g., `pipeline_type: "etl"` for data_pipeline): +0.5 points
- Highest score wins; ties fall back to `"general"`
- If no type scores > 0, defaults to `"general"` with 0.5 confidence

**Override:** Pass `pipeline_type="ml_pipeline"` in task input to skip detection.

### 3. Schema Skeleton Extraction (`agents/pipeline/schema_extractor.py`)

Full templates are 800-2300 lines — too large for an LLM prompt. The schema
extractor programmatically reduces them to compact type-hint skeletons:

```python
# Full template (800+ lines):
project:
  name: "Acme Data Pipeline"
  version: "1.0.0"
  description: "ETL pipeline for customer analytics"
  owner:
    team: "Data Engineering"
    lead: "jane.doe@acme.com"
  ...

# Schema skeleton (~150 lines):
project:
  name: str
  version: str
  description: str
  owner:
    team: str
    lead: str
```

**Functions:**

| Function | Description |
|----------|-------------|
| `infer_type_hint(value)` | Maps YAML values to type hints: `str`, `int`, `float`, `bool`, `list[str]`, `list[dict]`, `dict` |
| `extract_schema_skeleton(data, max_depth)` | Recursively traverses parsed YAML, replaces values with type hints |
| `load_template_schema(pipeline_type, templates_dir)` | Loads template file, handles invalid YAML gracefully, returns skeleton |

**Constants:**

| Constant | Description |
|----------|-------------|
| `TEMPLATE_FILES` | Maps pipeline type to template filename (6 entries) |
| `REQUIRED_SECTIONS` | Maps pipeline type to required top-level keys |

### 4. YAML Validation (`agents/pipeline/validators.py`)

Three-layer validation of generated pipeline YAML:

**Layer 1: Parsability** — `yaml.safe_load()` succeeds

**Layer 2: Required Sections** — All required top-level keys present for the type

**Layer 3: Field Types** — Basic type checks:
- `project.name` is non-empty string
- `project.version` is string (not int)
- `monitoring` is dict (not scalar)
- `success_criteria` is dict or list (not scalar)

**Functions:**

| Function | Description |
|----------|-------------|
| `validate_pipeline_yaml(yaml_str, pipeline_type)` | Full 3-layer validation |
| `strip_markdown_fences(text)` | Removes ` ```yaml ` wrappers from LLM output |
| `check_required_sections(data, pipeline_type)` | Returns `(found, missing)` lists |
| `check_field_types(data)` | Returns list of warning strings |

**Validation Result:**
```python
{
    "valid": True,
    "errors": [],
    "warnings": ["project.version should be a string"],
    "sections_found": ["project", "data_sources", ...],
    "sections_missing": [],
    "parsed_data": { ... },
}
```

### 5. Multi-Stage Generation Flow

The agent's `_execute()` method runs a multi-stage pipeline:

```
1. Parse requirements_yaml and infra_yaml
2. Detect pipeline type (or use override)
3. Load schema skeleton from full template
4. Build system prompt (base + type-specific addendum)
5. Build user prompt (skeleton + requirements + infra + required sections)
6. LLM call (temperature=0.1, max_tokens=8000)
7. Strip markdown fences from response
8. Validate output
9. If invalid but repairable → repair LLM call
10. Return TaskResult with pipeline_yaml + metadata
```

**Repair Stage:** If the generated YAML is parseable but missing required sections,
the agent makes a second LLM call with the original output plus a list of missing
sections. The repair prompt asks the LLM to add only the missing sections.

### 6. Context Generation

After successful execution, `_generate_context()` makes a second LLM call to
produce entries for the `.context/` directory:

- **`decisions.md`** — Why this pipeline type was chosen, key architectural
  decisions, infrastructure selections
- **`confidence-report.md`** — Per-section confidence scores, areas needing
  human review, assumptions made

### 7. Facade Integration

The `ConductorAI` facade exposes a convenience method:

```python
conductor = ConductorAI(config)
await conductor.initialize()

result = await conductor.generate_pipeline_yaml(
    requirements_yaml=open("templates/requirements/data-pipeline-requirements.yaml").read(),
    infra_yaml=open("templates/infrastructure/data-pipeline-infra.yaml").read(),
    pipeline_type="auto",  # or explicit: "data_pipeline"
)

print(result["pipeline_yaml"])       # Complete pipeline YAML
print(result["pipeline_type"])       # "data_pipeline"
print(result["validation_result"])   # {"valid": True, ...}
```

## Design Decisions

### Schema Skeleton vs. Full Template in Prompt
Full templates are 800-2300 lines — well beyond optimal LLM prompt size. The
schema skeleton preserves the hierarchical structure and key names (the
*structure* the LLM needs) while discarding concrete values (which the LLM
replaces anyway). This reduces prompt size by 80-90%.

### Temperature 0.1 for Generation
Pipeline YAML generation is a structured, deterministic task. Low temperature
minimizes creative variation while still allowing the LLM to adapt to the
specific requirements and infrastructure.

### Repair Stage Instead of Retry
When validation fails due to missing sections, a targeted repair call is cheaper
and more reliable than a full retry. The LLM sees its own output and the specific
gaps, making it easy to add only what's missing.

### Type Auto-Detection by Key Scoring
Pattern-matching on requirement keys is fast, deterministic, and transparent.
Each detection result includes a confidence score. Low confidence (< 0.5)
indicates ambiguous requirements — the user should consider specifying the type
explicitly.

### Graceful Handling of Invalid Templates
Some template files contain illustrative YAML with intentional syntax that
doesn't strictly parse (e.g., flow examples). `load_template_schema()` catches
`yaml.YAMLError` and returns an empty string rather than failing. The LLM can
still generate valid output from requirements + infra alone.

## Package Structure

```
src/conductor/
├── core/
│   └── enums.py                                    ← MODIFIED (+ PIPELINE_GENERATOR)
├── agents/
│   ├── __init__.py                                 ← MODIFIED (+ PipelineYamlGeneratorAgent)
│   └── pipeline/                                   ← NEW
│       ├── __init__.py
│       ├── schema_extractor.py                     (TEMPLATE_FILES, REQUIRED_SECTIONS, extraction)
│       ├── validators.py                           (3-layer validation, fence stripping)
│       └── pipeline_yaml_generator.py              (main agent, prompts, type detection)
└── facade.py                                       ← MODIFIED (+ generate_pipeline_yaml)
```

## Test Coverage

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_schema_extractor.py` | 24 | Type inference, skeleton extraction, template loading, required sections |
| `test_validators.py` | 21 | Fence stripping, section checking, type checking, full validation |
| `test_pipeline_yaml_generator.py` | 25 | Init, type detection, task validation, generation flow, context, errors |
| **Day 13 Total** | **70** | |

## All 8 Agent Types

| AgentType | Agent Class | Phase | Day |
|-----------|-------------|-------|-----|
| `CODING` | CodingAgent | Development | 6 |
| `REVIEW` | ReviewAgent | Development | 6 |
| `TEST_DATA` | TestDataAgent | Development | 7 |
| `TEST` | TestAgent | Development | 7 |
| `DEVOPS` | DevOpsAgent | DevOps | 7 |
| `DEPLOYING` | DeployingAgent | DevOps | 7 |
| `MONITOR` | MonitorAgent | Monitoring | 8 |
| `PIPELINE_GENERATOR` | PipelineYamlGeneratorAgent | Pre-Workflow | 13 |
