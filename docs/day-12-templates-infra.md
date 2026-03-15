# Day 12: Business Requirement Templates & Infrastructure Dictionaries

## Overview

Day 12 adds two input layers that bridge business users and ConductorAI:

- **Business Requirement Templates** (`templates/requirements/`) — Simplified
  YAML intake forms that non-technical stakeholders can fill in 15-20 minutes
- **Infrastructure Dictionaries** (`templates/infrastructure/`) — Structured
  inventories of available infrastructure per pipeline type

Together, these provide the two inputs that feed the pipeline generation engine:
what the business needs (requirements) and what IT provides (infrastructure).

```
Business Team                       IT / Platform Team
     │                                    │
     ▼                                    ▼
┌────────────────────┐        ┌────────────────────────┐
│ requirements.yaml  │        │ infrastructure.yaml     │
│ (from templates/   │        │ (from templates/        │
│  requirements/)    │        │  infrastructure/)       │
└────────┬───────────┘        └───────────┬────────────┘
         │                                │
         └──────────┬─────────────────────┘
                    ▼
         ┌──────────────────┐
         │ YAML Generation  │
         │ Engine (Day 13)  │
         └──────────────────┘
```

## Business Requirement Templates

Located in `templates/requirements/`. Six templates covering every pipeline type:

| Template File | Pipeline Type | Sections |
|--------------|---------------|----------|
| `data-pipeline-requirements.yaml` | Data/ETL | project, sources, destination, transformations, quality, access, scale |
| `ml-pipeline-requirements.yaml` | ML/AI | project, problem_type, training_data, model_requirements, deployment, monitoring |
| `rag-llm-requirements.yaml` | RAG/LLM | project, project_type, knowledge_sources, quality, security |
| `agentic-ops-requirements.yaml` | Agentic Ops | project, agent_architecture, agents, autonomy_rules, safety |
| `integration-requirements.yaml` | Integration | project, integration_type, existing_systems, target, strategy |
| `general-project-requirements.yaml` | General | project, functional_requirements, technical_requirements, testing |

### Design Principles

**Plain English, no jargon.** Every field has an inline comment with an example:
```yaml
project:
  name: ""                # e.g., "Customer Analytics Pipeline"
  owner: ""               # team or person responsible
  priority: ""            # high / medium / low
  target_go_live: ""      # e.g., "2026-Q2"
```

**Closed-choice where possible.** Fields use enumerated options to reduce ambiguity:
```yaml
frequency: ""             # real-time / hourly / daily / weekly
complexity: ""            # simple / moderate / complex
```

**TBD is acceptable.** Instructions tell users to use "TBD" for unknown fields
rather than leaving them blank. The generation engine can flag these for follow-up.

### Relationship to Full Templates

The full templates in `templates/` (800-2300 lines each) are the complete
technical specification format that ConductorAI agents consume. The simplified
requirement templates extract only the business-relevant subset — typically
30-60 lines that a business stakeholder can fill without engineering context.

```
templates/requirements/data-pipeline-requirements.yaml     (30 lines, business input)
        ↓ (fed to YAML generation engine)
templates/data-pipeline-requirements-template.yaml         (800+ lines, full spec)
```

## Infrastructure Dictionaries

Located in `templates/infrastructure/`. Six dictionaries, one per pipeline type:

| Dictionary File | Pipeline Type | Key Sections |
|----------------|---------------|-------------|
| `data-pipeline-infra.yaml` | Data/ETL | compute, storage, streaming, data_processing, data_governance, networking, ci_cd, monitoring, constraints |
| `ml-pipeline-infra.yaml` | ML/AI | compute (training + inference), storage, model_registry, feature_store, experiment_tracking, model_serving, networking, ci_cd, monitoring, constraints |
| `rag-llm-infra.yaml` | RAG/LLM | compute, storage, llm_providers, vector_databases, embedding, document_processing, networking, ci_cd, monitoring, security, constraints |
| `agentic-ops-infra.yaml` | Agentic Ops | compute, storage, agent_infrastructure, tool_integrations, safety_infrastructure, networking, ci_cd, monitoring, constraints |
| `integration-infra.yaml` | Integration | legacy (source env), target (dest env), migration_tools, networking, ci_cd, monitoring, constraints |
| `general-project-infra.yaml` | General | compute, storage, networking, ci_cd, monitoring, security, messaging, constraints |

### Structure Pattern

Every infrastructure dictionary follows the registry pattern from
[pipeline-yaml-to-zip.md](./pipeline-yaml-to-zip.md):

```yaml
registry_version: "1.0"
organization: ""
last_updated: ""

compute:
  kubernetes: { ... }
  lambda: { ... }

storage:
  s3: { ... }
  rds: { ... }

# ... type-specific sections ...

constraints:
  cloud_provider: ""
  region: ""
  compliance: []
  banned_services: []
```

### Type-Specific Sections

Each dictionary includes sections tailored to its pipeline type:

- **Data Pipeline** adds `streaming` (Kinesis, Kafka, SQS), `data_processing`
  (Glue, EMR, Spark, dbt, Flink), and `data_governance` (catalog, quality, lineage)
- **ML Pipeline** adds `model_registry`, `feature_store`, `experiment_tracking`
  (MLflow, W&B), `model_serving`, and `accelerators` (GPU types)
- **RAG/LLM** adds `llm_providers` (OpenAI, Anthropic, Bedrock),
  `vector_databases` (pgvector, Pinecone, OpenSearch), and `document_processing`
- **Agentic Ops** adds `agent_infrastructure` (message_bus, state_store, event_bus),
  `tool_integrations` (K8s, Datadog, PagerDuty, GitHub, Jira, Slack), and
  `safety_infrastructure` (kill_switch, approval_gateway, audit_log)
- **Integration** has a unique dual-environment structure with `legacy` (source)
  and `target` (destination) side by side, plus `migration_tools`
- **General** uses the standard pattern without domain-specific extensions

### How IT Teams Use Infrastructure Dictionaries

1. **Fork the template** for your pipeline type
2. **Fill in actual values** — cluster names, service versions, capacity limits
3. **Version control it** — infrastructure changes are tracked via Git
4. **Feed to the generation engine** — the YAML engine reads infrastructure
   capabilities directly, no AI interpretation needed

## Package Structure

```
templates/
├── requirements/                          ← NEW (6 files)
│   ├── data-pipeline-requirements.yaml
│   ├── ml-pipeline-requirements.yaml
│   ├── rag-llm-requirements.yaml
│   ├── agentic-ops-requirements.yaml
│   ├── integration-requirements.yaml
│   └── general-project-requirements.yaml
└── infrastructure/                        ← NEW (6 files)
    ├── data-pipeline-infra.yaml
    ├── ml-pipeline-infra.yaml
    ├── rag-llm-infra.yaml
    ├── agentic-ops-infra.yaml
    ├── integration-infra.yaml
    └── general-project-infra.yaml
```
