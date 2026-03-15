# ConductorAI Data Governance Policy

**Last Updated:** 2026-03-14
**Policy Owner:** Engineering Lead
**Review Cadence:** Semi-annually
**Applies To:** All data processed, stored, and transmitted by ConductorAI

---

## 1. Data Classification

All data within the ConductorAI ecosystem is classified into four levels. Each level determines the handling, storage, access, and retention requirements.

### 1.1 Classification Levels

| Level | Label | Description | Examples in ConductorAI |
|-------|-------|-------------|------------------------|
| L1 | **Public** | Non-sensitive, may be freely shared | Open-source code, documentation, public metrics dashboards |
| L2 | **Internal** | Internal use only, low impact if disclosed | Workflow definitions, agent type configurations, non-sensitive task names |
| L3 | **Confidential** | Business-sensitive, restricted access | LLM-generated source code, review findings, deployment configurations, pipeline YAML |
| L4 | **Restricted** | Highest sensitivity, strict controls | API keys, Redis passwords, LLM API keys, PII, credentials |

### 1.2 Classification by ConductorAI Component

| Component | Data Type | Classification | Justification |
|-----------|----------|---------------|---------------|
| `ConductorConfig` | Framework settings | L2 - Internal | Contains operational settings, no secrets by design |
| `RedisConfig.password` | Redis credential | L4 - Restricted | Database authentication credential |
| `RedisConfig.url` | Connection string | L3 - Confidential | May contain embedded credentials |
| `LLMConfig.api_key` | API credential | L4 - Restricted | LLM provider authentication |
| `LLMConfig.api_base_url` | Endpoint URL | L2 - Internal | May reveal infrastructure topology |
| `TaskDefinition.input_data` | Task payload | L3 - Confidential | May contain proprietary specifications |
| `TaskResult.output_data` | Agent output | L3 - Confidential | Contains LLM-generated code, reviews, configs |
| `AgentState` | Runtime state | L2 - Internal | Operational data, no business content |
| `WorkflowState` | Execution state | L2 - Internal | References to tasks and phases |
| `WorkflowState.task_results` | Aggregated results | L3 - Confidential | Contains all agent outputs for a workflow |
| `ErrorHandler` dead-letter queue | Failed task data | L3 - Confidential | May contain partial outputs and error details |
| `MetricsCollector` output | Prometheus metrics | L1 - Public | Aggregated, no PII or business data |
| `TracingProvider` spans | Distributed traces | L2 - Internal | Contains timing and correlation data |
| `HealthChecker` output | Health status | L1 - Public | System operational status only |
| `ArtifactStore` contents | Workflow artifacts | L3 - Confidential | Generated code, context files, configs |
| `SecretsProvider` values | Secrets | L4 - Restricted | All secrets regardless of type |
| `structlog` output | Application logs | L2 - Internal | Must not contain L3/L4 data |

---

## 2. Retention Policies

### 2.1 Retention Schedule

| Data Type | Classification | Retention Period | Storage | Disposal Method |
|-----------|---------------|-----------------|---------|-----------------|
| Workflow state | L2 | 90 days | Redis (StateManager) | Redis key expiry (TTL) |
| Task results | L3 | 90 days | Redis (StateManager) | Redis key expiry (TTL) |
| Agent state | L2 | 7 days (after workflow completion) | Redis (StateManager) | `delete_agent_state()` |
| Artifacts | L3 | 180 days | ArtifactStore (Redis/S3) | Automated cleanup job |
| Application logs | L2 | 365 days | Log aggregation system | Automated rotation |
| Prometheus metrics | L1 | 365 days | Prometheus TSDB | TSDB compaction |
| Distributed traces | L2 | 30 days | Trace backend (Jaeger/Tempo) | Backend retention policy |
| Dead-letter queue entries | L3 | 30 days | Redis (ErrorHandler) | Redis key expiry |
| LLM API keys | L4 | Until rotated | SecretsProvider | Rotation + revocation |
| Redis passwords | L4 | Until rotated | SecretsProvider | Rotation + revocation |
| Audit logs | L2 | 3 years (SOC 2 requirement) | Immutable log store | No early deletion |

### 2.2 Redis Key Expiry Configuration

```python
"""Configure Redis key TTLs for data retention compliance."""

# Key patterns and their recommended TTLs
RETENTION_TTLS = {
    # Workflow state: 90 days
    "conductor:workflow:*": 90 * 24 * 3600,  # 7,776,000 seconds

    # Task results: 90 days
    "conductor:task_result:*": 90 * 24 * 3600,

    # Agent state: 7 days (transient)
    "conductor:agent:*": 7 * 24 * 3600,  # 604,800 seconds

    # Dead-letter queue: 30 days
    "conductor:dlq:*": 30 * 24 * 3600,  # 2,592,000 seconds

    # Message bus channels: No TTL (pub/sub is ephemeral)
    # Artifacts: 180 days
    "conductor:artifact:*": 180 * 24 * 3600,
}
```

```bash
# Redis key expiry verification script
#!/bin/bash
# Check that all conductor: keys have TTLs set

redis-cli --tls -h redis.internal -p 6380 -a "${REDIS_PASSWORD}" \
  --scan --pattern "conductor:*" | while read key; do
    ttl=$(redis-cli --tls -h redis.internal -p 6380 -a "${REDIS_PASSWORD}" TTL "$key")
    if [ "$ttl" -eq "-1" ]; then
        echo "WARNING: Key without TTL: $key"
    fi
done
```

### 2.3 Data Disposal Procedures

- **Redis data**: Key expiry handles automatic disposal. Verify with `TTL` command.
- **Application logs**: Log rotation configured at the infrastructure level (logrotate/Datadog).
- **Secrets**: Rotated via SecretsProvider; old secrets revoked at the provider level.
- **Backups**: Redis RDB/AOF snapshots follow the same retention as primary data.

---

## 3. Encryption Requirements

### 3.1 Encryption at Rest

| Data Store | Encryption Method | Key Management | Status |
|-----------|-------------------|---------------|--------|
| Redis (StateManager) | Redis TLS (`RedisConfig.ssl=True`) | TLS certificates via PKI | Required in staging/prod |
| Redis (MessageBus) | Redis TLS | Same as above | Required in staging/prod |
| Redis RDB snapshots | Filesystem encryption (dm-crypt/LUKS or EBS encryption) | Cloud KMS or LUKS keys | Required |
| Artifact storage (S3) | S3 server-side encryption (SSE-S3 or SSE-KMS) | AWS KMS | Required |
| Application logs | Encrypted volume or encrypted log service | Cloud KMS | Required |

```python
# Enforce TLS for Redis in production
from conductor.core.config import RedisConfig, ConductorConfig

config = ConductorConfig(
    environment="prod",
    redis=RedisConfig(
        url="rediss://redis.internal:6380/0",  # rediss:// = TLS
        ssl=True,
        password=None,  # Loaded via SecretsProvider at runtime
    ),
)
```

### 3.2 Encryption in Transit

| Connection | Protocol | Minimum TLS Version | Status |
|-----------|----------|-------------------|--------|
| Application <-> Redis | TLS | TLS 1.2 | Required |
| Application <-> OpenAI API | HTTPS | TLS 1.2 | Enforced by SDK |
| Application <-> Anthropic API | HTTPS | TLS 1.2 | Enforced by SDK |
| Redis <-> Redis Sentinel | TLS | TLS 1.2 | Required |
| Redis <-> Redis Cluster nodes | TLS | TLS 1.2 | Required |
| Application <-> Vault | HTTPS | TLS 1.2 | Required |
| Application <-> AWS Secrets Manager | HTTPS | TLS 1.2 | Enforced by SDK |
| Prometheus scrape | HTTPS | TLS 1.2 | Recommended |
| HealthChecker endpoint | HTTPS | TLS 1.2 | Required in production |

```ini
# Redis TLS configuration (redis.conf)
tls-port 6380
port 0
tls-cert-file /etc/redis/tls/redis.crt
tls-key-file /etc/redis/tls/redis.key
tls-ca-cert-file /etc/redis/tls/ca.crt
tls-protocols "TLSv1.2 TLSv1.3"
tls-ciphersuites "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"
```

---

## 4. Access Matrix by Role

### 4.1 Data Access by RBAC Role

| Data Category | ADMIN | OPERATOR | VIEWER | System (Agents) |
|--------------|-------|----------|--------|-----------------|
| **L4 - Restricted** | | | | |
| API keys / secrets | Read (via SecretsProvider) | No | No | Read (at runtime) |
| Redis password | Infrastructure only | No | No | Connection only |
| **L3 - Confidential** | | | | |
| Task input data | Read/Write | Read/Write | Read | Read/Write |
| Task output data | Read/Write | Read/Write | Read | Write |
| Generated code | Read/Delete | Read | Read | Write |
| Workflow artifacts | Read/Delete | Read | Read | Write |
| Dead-letter queue | Read/Purge | Read | No | Write |
| **L2 - Internal** | | | | |
| Agent state | Read/Modify | Read | Read | Read/Write |
| Workflow state | Read/Modify | Read | Read | Read/Write |
| Configuration | Read/Modify | Read | Read | Read |
| Application logs | Read | Read | Read | Write |
| **L1 - Public** | | | | |
| Metrics | Read | Read | Read | Write |
| Health status | Read | Read | Read | Write |

### 4.2 Permission Enforcement Points

```python
"""Access control enforcement points in ConductorAI."""

# 1. Workflow execution (facade.py)
async def run_workflow(self, definition: WorkflowDefinition) -> WorkflowState:
    # ENFORCE: user must have WORKFLOW_RUN permission
    rbac.require_permission(user_id, Permission.WORKFLOW_RUN)
    return await self._workflow_engine.run_workflow(definition)

# 2. Agent registration (facade.py)
async def register_agent(self, agent: BaseAgent) -> None:
    # ENFORCE: user must have AGENT_REGISTER permission
    rbac.require_permission(user_id, Permission.AGENT_REGISTER)
    await self._coordinator.register_agent(agent)

# 3. Configuration modification
def modify_config(self, updates: dict) -> None:
    # ENFORCE: user must have CONFIG_MODIFY permission (ADMIN only)
    rbac.require_permission(user_id, Permission.CONFIG_MODIFY)

# 4. Artifact deletion
async def delete_artifact(self, artifact_id: str) -> None:
    # ENFORCE: user must have ARTIFACT_DELETE permission (ADMIN only)
    rbac.require_permission(user_id, Permission.ARTIFACT_DELETE)
```

---

## 5. GDPR / CCPA Considerations for AI-Generated Content

### 5.1 Applicability

ConductorAI itself is an orchestration framework, not a data controller. However, organizations deploying ConductorAI must consider privacy regulations when:

- Task input data (`TaskDefinition.input_data`) contains personal data
- LLM-generated output (`TaskResult.output_data`) references identifiable individuals
- Application logs contain user identifiers or IP addresses

### 5.2 Data Subject Rights Mapping

| Right | GDPR Article | ConductorAI Implementation |
|-------|-------------|---------------------------|
| Right to Access | Art. 15 | Query `StateManager.get_workflow_state()` and `get_task_result()` for data associated with a subject |
| Right to Rectification | Art. 16 | Update task results via `StateManager.save_task_result()` with corrected data |
| Right to Erasure | Art. 17 | `StateManager.delete_agent_state()`, Redis key deletion, artifact purge |
| Right to Portability | Art. 20 | Export via `WorkflowState.model_dump_json()` and `TaskResult.model_dump_json()` |
| Right to Restrict Processing | Art. 18 | Pause workflow via `WorkflowEngine`; revoke user permissions via `RBACManager.revoke_role()` |
| Right to Object | Art. 21 | Application-level: Reject task definitions containing subject data |

### 5.3 GDPR-Specific Controls

```python
"""GDPR compliance utilities for ConductorAI deployments."""

async def handle_erasure_request(
    state_manager: StateManager,
    artifact_store: ArtifactStore,
    subject_identifier: str,
) -> dict:
    """Process a GDPR Art. 17 erasure request.

    Searches all stored data for references to the data subject
    and removes them.

    Args:
        state_manager: Active StateManager instance.
        artifact_store: Active ArtifactStore instance.
        subject_identifier: The data subject's identifier to erase.

    Returns:
        Summary of erasure actions taken.
    """
    actions = []

    # 1. Search and delete agent states referencing the subject
    agent_states = await state_manager.list_agent_states()
    for state in agent_states:
        if subject_identifier in str(state.model_dump()):
            await state_manager.delete_agent_state(state.agent_id)
            actions.append(f"Deleted agent state: {state.agent_id}")

    # 2. Search workflow states and task results
    # (Requires application-level iteration over known workflow IDs)

    # 3. Delete artifacts containing subject data
    # (Requires application-level search through artifact content)

    return {"subject": subject_identifier, "actions": actions}
```

### 5.4 CCPA-Specific Controls

| CCPA Requirement | ConductorAI Implementation |
|-----------------|---------------------------|
| Right to Know | `StateManager` queries to enumerate data associated with a consumer |
| Right to Delete | `StateManager.delete_agent_state()`, Redis key deletion |
| Right to Opt-Out of Sale | N/A -- ConductorAI does not sell personal data |
| Non-Discrimination | N/A -- ConductorAI is a backend framework |

### 5.5 AI-Generated Content Considerations

| Concern | Policy | Implementation |
|---------|--------|---------------|
| PII in LLM prompts | **Prohibited** -- No PII in `TaskDefinition.input_data` sent to LLMs | Agent `_validate_task()` should reject PII patterns |
| PII in LLM responses | **Monitor** -- Scan `TaskResult.output_data` for PII before storage | Post-processing filter on agent output |
| Prompt/response logging | **Restricted** -- LLM prompts/responses must not be logged at DEBUG level in production | `structlog` configuration; log level >= INFO in prod |
| LLM data retention by providers | **Documented** -- Understand provider data retention policies | Provider agreements (OpenAI, Anthropic) |
| Training data opt-out | **Required** -- Opt out of provider training on API data | OpenAI: `"store": false` in API calls; Anthropic: API data not used for training |

---

## 6. Prompt and Response Data Handling

### 6.1 Data Flow Through LLM Providers

```
TaskDefinition.input_data
        │
        ▼
  Agent._execute()
        │
        ▼ (constructs prompt)
  LLMProvider.generate()  ──────►  LLM API (OpenAI/Anthropic)
        │                                    │
        │                          ◄─────────┘ (response)
        ▼
  TaskResult.output_data
        │
        ▼
  StateManager.save_task_result()
        │
        ▼
  Redis (encrypted at rest via TLS)
```

### 6.2 Prompt Data Controls

| Control | Description | Implementation |
|---------|-------------|---------------|
| Prompt sanitization | Strip PII, credentials, and sensitive data before LLM calls | Pre-processing in each agent's `_execute()` |
| Prompt size limits | Enforce `LLMConfig.max_tokens` and input length limits | Agent `_validate_task()` + LLM SDK limits |
| Prompt logging | Log prompt metadata (length, agent_type) but NOT content in production | `structlog` with redaction filters |
| Prompt retention | Prompts stored only in TaskResult metadata if needed; subject to retention policy | Redis TTL on task results |

### 6.3 Response Data Controls

| Control | Description | Implementation |
|---------|-------------|---------------|
| Response validation | Validate LLM response structure via Pydantic before storage | Agent `_execute()` output parsing |
| Response size limits | Enforce maximum output size per agent type | Agent-level configuration |
| Response scanning | Scan for inadvertent PII, credentials, or injection content | Post-processing filter |
| Response storage | Store in Redis with TTL; encrypt at rest via TLS | `StateManager.save_task_result()` |

### 6.4 LLM Token Usage Tracking

```python
# MetricsCollector tracks all LLM usage for governance
from conductor.infrastructure.metrics import MetricsCollector

metrics = MetricsCollector()

# Recorded per LLM call:
metrics.record_llm_request(provider="openai", model="gpt-4")
metrics.record_llm_tokens(
    provider="openai",
    prompt_tokens=1500,
    completion_tokens=2000,
)

# Prometheus metrics for governance reporting:
# conductorai_llm_requests_total{provider="openai", model="gpt-4"}
# conductorai_llm_tokens_total{provider="openai", token_type="prompt"}
# conductorai_llm_tokens_total{provider="openai", token_type="completion"}
```

---

## 7. Data Governance Roles and Responsibilities

| Role | Responsibilities |
|------|-----------------|
| **Data Owner** (Engineering Lead) | Classify data, approve access requests, review policy |
| **Data Steward** (Senior Engineer) | Implement controls, monitor compliance, handle erasure requests |
| **Data Custodian** (DevOps/SRE) | Manage storage infrastructure, encryption, backups, retention |
| **Data Users** (Developers) | Follow policy, classify data in their code, report incidents |
| **Auditor** (External) | Verify controls, review evidence, report findings |

---

## 8. Policy Compliance Checklist

| # | Requirement | Frequency | Owner | Status |
|---|------------|-----------|-------|--------|
| 1 | Data classification review for new features | Per release | Data Steward | |
| 2 | Redis key TTL audit | Monthly | Data Custodian | |
| 3 | Log retention verification | Quarterly | Data Custodian | |
| 4 | RBAC access review | Quarterly | Data Owner | |
| 5 | PII scan of LLM prompts/responses | Monthly | Data Steward | |
| 6 | Encryption configuration audit | Quarterly | Data Custodian | |
| 7 | GDPR/CCPA process test (mock erasure request) | Semi-annually | Data Steward | |
| 8 | LLM provider data retention review | Annually | Data Owner | |
| 9 | Full data governance policy review | Semi-annually | Data Owner | |
