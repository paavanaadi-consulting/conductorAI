# ConductorAI Security Audit Checklist

**Last Updated:** 2026-03-14
**Scope:** Full security audit of ConductorAI multi-agent orchestration framework
**Frequency:** Quarterly (minimum), plus ad-hoc after any security incident

---

## 1. Dependency Scanning

### 1.1 pip-audit (Python Dependencies)

- [ ] Run `pip-audit` against the locked dependency set
- [ ] Resolve all CRITICAL and HIGH severity CVEs before release
- [ ] Document accepted risks for MEDIUM/LOW findings with justification

```bash
# Install pip-audit
pip install pip-audit

# Audit current environment
pip-audit --strict --desc

# Audit from requirements file
pip-audit -r requirements.txt --output json > audit-report.json

# Audit with fix suggestions
pip-audit --fix --dry-run
```

### 1.2 Safety (Alternative Scanner)

- [ ] Run `safety` scan as a second-opinion scanner
- [ ] Cross-reference findings with pip-audit results

```bash
# Install safety
pip install safety

# Scan installed packages
safety scan

# Scan from requirements
safety scan -r requirements.txt --output json > safety-report.json
```

### 1.3 CI/CD Integration

- [ ] Dependency scanning runs on every PR (blocking on CRITICAL/HIGH)
- [ ] Weekly scheduled scan of `main` branch dependencies
- [ ] Automated issue creation for newly discovered CVEs

```yaml
# .github/workflows/security-scan.yml
name: Security Scan
on:
  pull_request:
  schedule:
    - cron: '0 6 * * 1'  # Weekly Monday 6AM UTC

jobs:
  dependency-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pip-audit --strict --desc
      - run: safety scan
```

### 1.4 Key Dependencies to Monitor

| Package | Purpose in ConductorAI | Risk Level |
|---------|----------------------|------------|
| `redis` / `redis[hiredis]` | MessageBus + StateManager backend | HIGH - network-facing |
| `openai` | LLM provider (OpenAIProvider) | HIGH - handles API keys |
| `anthropic` | LLM provider (AnthropicProvider) | HIGH - handles API keys |
| `pydantic` / `pydantic-settings` | Config validation (ConductorConfig, RedisConfig) | MEDIUM |
| `structlog` | Structured logging throughout | LOW |
| `prometheus_client` | MetricsCollector telemetry | LOW |
| `opentelemetry-*` | TracingProvider distributed tracing | LOW |
| `pyyaml` | Config loading via `load_config()` | MEDIUM - deserialization |
| `hvac` | VaultSecretsProvider (optional) | HIGH - secrets access |
| `boto3` | AWSSecretsProvider (optional) | HIGH - cloud access |

---

## 2. Secret Management

### 2.1 Environment Variable Secrets (EnvSecretsProvider)

- [ ] All secrets use the `CONDUCTOR_SECRET_` prefix (configurable via `ConductorConfig.secrets_prefix`)
- [ ] No secrets are hardcoded in source code
- [ ] No secrets appear in configuration YAML files committed to git
- [ ] `.env` files are in `.gitignore`

```python
# CORRECT: Using EnvSecretsProvider from conductor.infrastructure.secrets
from conductor.infrastructure.secrets import EnvSecretsProvider

provider = EnvSecretsProvider(prefix="CONDUCTOR_SECRET_")
api_key = await provider.get_secret("llm_api_key")
# Reads from CONDUCTOR_SECRET_LLM_API_KEY environment variable
```

- [ ] Verify `LLMConfig.api_key` is loaded from env, not from YAML:
```bash
# Correct approach
export CONDUCTOR_LLM__API_KEY="sk-..."

# NEVER commit this in conductor.yaml
# llm:
#   api_key: sk-...   # <-- AUDIT FAILURE
```

### 2.2 HashiCorp Vault (VaultSecretsProvider)

- [ ] Vault token rotation policy is enforced (max TTL: 24h for service tokens)
- [ ] AppRole or Kubernetes auth method used (not static tokens in production)
- [ ] Secret paths follow convention: `secret/conductorai/{environment}/{key}`
- [ ] Audit logging enabled on Vault mount point

```python
from conductor.infrastructure.secrets import VaultSecretsProvider

vault = VaultSecretsProvider(
    vault_addr="https://vault.internal:8200",
    vault_token=os.environ["VAULT_TOKEN"],  # Short-lived, rotated
    mount_point="secret",
    path_prefix="conductorai",
)
redis_password = await vault.get_secret("redis_password")
```

### 2.3 AWS Secrets Manager (AWSSecretsProvider)

- [ ] IAM role has least-privilege access to `conductorai/*` secrets only
- [ ] Secret rotation enabled (Lambda rotation function deployed)
- [ ] Resource policies restrict cross-account access
- [ ] CloudTrail logging enabled for `secretsmanager:GetSecretValue`

```python
from conductor.infrastructure.secrets import AWSSecretsProvider

aws_secrets = AWSSecretsProvider(
    region_name="us-east-1",
    secret_prefix="conductorai/",
)
db_password = await aws_secrets.get_secret("redis_password")
# Reads from AWS Secrets Manager: conductorai/redis_password
```

### 2.4 Secret Audit Checklist

- [ ] `grep -r "sk-" src/` returns zero results (no OpenAI keys in code)
- [ ] `grep -r "password" src/conductor/core/config.py` only references field definitions, not values
- [ ] `git log --all -p -S "api_key" -- "*.yaml" "*.yml" "*.json"` returns no committed secrets
- [ ] `EnvSecretsProvider.list_keys()` output reviewed -- no unexpected secrets present
- [ ] Secret values are never logged (verify `structlog` output does not contain `api_key` values)

---

## 3. Network Security

### 3.1 Redis TLS Configuration

- [ ] Redis connections use TLS in staging and production (`RedisConfig.ssl = True`)
- [ ] Redis password is set (`RedisConfig.password` or in URL)
- [ ] Redis is not exposed to public internet (bind to private subnet)
- [ ] Redis `protected-mode` is enabled

```python
# Production RedisConfig
from conductor.core.config import RedisConfig

redis_config = RedisConfig(
    url="rediss://redis.internal:6380/0",  # rediss:// = TLS
    ssl=True,
    password="${REDIS_PASSWORD}",  # Loaded from SecretsProvider
    max_connections=20,
    socket_timeout=5.0,
    key_prefix="conductor:",
)
```

```ini
# redis.conf hardening
bind 10.0.0.0/8
protected-mode yes
requirepass ${REDIS_PASSWORD}
tls-port 6380
port 0
tls-cert-file /etc/redis/tls/redis.crt
tls-key-file /etc/redis/tls/redis.key
tls-ca-cert-file /etc/redis/tls/ca.crt
tls-auth-clients optional
rename-command FLUSHALL ""
rename-command FLUSHDB ""
rename-command CONFIG ""
rename-command DEBUG ""
```

### 3.2 Redis Sentinel / Cluster TLS

- [ ] Sentinel nodes communicate over TLS
- [ ] Cluster bus uses TLS (`tls-cluster yes` in Redis 7+)
- [ ] All `RedisConfig.sentinel_nodes` and `cluster_nodes` use TLS-enabled ports

```python
# Sentinel with TLS
redis_config = RedisConfig(
    sentinel_mode=True,
    sentinel_master="conductorai-master",
    sentinel_nodes=["sentinel-0.internal:26380", "sentinel-1.internal:26380"],
    ssl=True,
    password="${REDIS_PASSWORD}",
)
```

### 3.3 LLM Provider API Security

- [ ] All LLM API calls use HTTPS (enforced by `openai` and `anthropic` SDKs)
- [ ] API keys are transmitted only in headers, never in query strings
- [ ] Custom `api_base_url` (if set in LLMConfig) uses HTTPS
- [ ] Network egress rules allow only necessary LLM API endpoints

```python
# If using a proxy/gateway for LLM calls
from conductor.core.config import LLMConfig

llm_config = LLMConfig(
    provider="openai",
    model="gpt-4",
    api_base_url="https://llm-gateway.internal/v1",  # Must be HTTPS
    api_key=None,  # Loaded via SecretsProvider, not config
)
```

### 3.4 Firewall Rules

- [ ] Inbound: Only health check endpoints exposed (HealthChecker via user's web framework)
- [ ] Outbound: Allowlist for LLM API endpoints:
  - `api.openai.com:443`
  - `api.anthropic.com:443`
- [ ] Outbound: Redis traffic restricted to internal subnet
- [ ] No unnecessary ports open on container or host

---

## 4. OWASP Top 10 for AI Systems

### 4.1 LLM01 - Prompt Injection

- [ ] System prompts are separated from user input in all agent `_execute()` implementations
- [ ] Input data from `TaskDefinition.input_data` is treated as untrusted
- [ ] Agent output is validated before being used as input to downstream agents
- [ ] Review all agent prompt templates for injection vectors

```python
# VULNERABLE: Direct interpolation of user input into system prompt
prompt = f"You are a coding agent. Generate code for: {task.input_data['specification']}"

# SAFER: Structured message format with role separation
messages = [
    {"role": "system", "content": "You are a coding agent. Generate Python code based on the user specification."},
    {"role": "user", "content": task.input_data["specification"]},
]
```

### 4.2 LLM02 - Insecure Output Handling

- [ ] LLM-generated code is not executed without sandboxing
- [ ] Agent output (`TaskResult.output_data`) is validated via Pydantic models before persistence
- [ ] No `eval()` or `exec()` on LLM output anywhere in the codebase
- [ ] HTML/script content in LLM output is sanitized before display

### 4.3 LLM03 - Training Data Poisoning

- [ ] N/A for ConductorAI (uses third-party LLMs, does not train models)
- [ ] Document which LLM models are approved for use

### 4.4 LLM04 - Model Denial of Service

- [ ] `LLMConfig.max_tokens` is set to a reasonable limit (default: 4096)
- [ ] `ConductorConfig.workflow_timeout_seconds` prevents runaway workflows (default: 300s)
- [ ] `ConductorConfig.max_agent_retries` limits retry storms (default: 3)
- [ ] ErrorHandler circuit breaker prevents cascading LLM failures

### 4.5 LLM05 - Supply Chain Vulnerabilities

- [ ] LLM provider SDK versions are pinned in requirements
- [ ] Provider SDKs are scanned (see Section 1: Dependency Scanning)
- [ ] `LLMConfig.api_base_url` only points to verified endpoints

### 4.6 LLM06 - Sensitive Information Disclosure

- [ ] Prompts sent to LLMs do not contain API keys, passwords, or PII
- [ ] `structlog` filters sensitive fields from log output
- [ ] MetricsCollector does not label metrics with sensitive data
- [ ] TracingProvider span attributes do not include secret values

### 4.7 LLM07 - Insecure Plugin Design

- [ ] Agent `_validate_task()` enforces required fields in `input_data`
- [ ] PolicyEngine checks are enforced at phase gates
- [ ] RBACManager permissions are checked before workflow execution

### 4.8 LLM08 - Excessive Agency

- [ ] Agents cannot modify system configuration (`Permission.CONFIG_MODIFY` restricted to `Role.ADMIN`)
- [ ] Agents cannot self-register or self-unregister
- [ ] `max_feedback_loops` (default: 3) prevents infinite agent cycles
- [ ] WorkflowEngine enforces phase ordering (DEVELOPMENT -> DEVOPS -> MONITORING)

### 4.9 LLM09 - Overreliance

- [ ] All LLM output includes agent_id and agent_type for traceability
- [ ] TaskResult stores full metadata including model, tokens, and duration
- [ ] Review gates (ReviewAgent) exist between code generation and deployment

### 4.10 LLM10 - Model Theft

- [ ] N/A for ConductorAI (does not host models)
- [ ] API keys for model access are properly secured (see Section 2)

---

## 5. Container Security

### 5.1 Non-Root Container Execution

- [ ] Dockerfile uses non-root user
- [ ] Container runs with `runAsNonRoot: true` in Kubernetes

```dockerfile
# Dockerfile security hardening
FROM python:3.11-slim AS base

# Create non-root user
RUN groupadd -r conductor && useradd -r -g conductor -d /app -s /sbin/nologin conductor

WORKDIR /app
COPY --chown=conductor:conductor . .
RUN pip install --no-cache-dir -e ".[prod]"

# Drop all capabilities
USER conductor

# Health check using HealthChecker endpoint
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

ENTRYPOINT ["python", "-m", "conductor"]
```

### 5.2 Read-Only Root Filesystem

- [ ] Container uses read-only root filesystem
- [ ] Writable volumes mounted only where needed (`/tmp`, log directories)

```yaml
# Kubernetes security context
apiVersion: v1
kind: Pod
metadata:
  name: conductorai
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
  containers:
    - name: conductor
      image: conductorai:latest
      securityContext:
        readOnlyRootFilesystem: true
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: logs
          mountPath: /app/logs
      resources:
        limits:
          memory: "512Mi"
          cpu: "500m"
        requests:
          memory: "256Mi"
          cpu: "250m"
  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: 100Mi
    - name: logs
      emptyDir:
        sizeLimit: 200Mi
```

### 5.3 Image Scanning

- [ ] Container images scanned with Trivy before deployment
- [ ] Base image is pinned to a specific SHA digest
- [ ] No CRITICAL or HIGH vulnerabilities in the final image

```bash
# Scan container image with Trivy
trivy image conductorai:latest --severity CRITICAL,HIGH --exit-code 1

# Scan filesystem
trivy fs --security-checks vuln,config,secret .

# CI/CD integration
trivy image --format json --output trivy-report.json conductorai:latest
```

### 5.4 Runtime Security

- [ ] Seccomp profile applied (default or custom)
- [ ] AppArmor/SELinux profile applied
- [ ] Network policies restrict pod-to-pod communication
- [ ] Pod Security Standards enforced at namespace level (`restricted`)

---

## 6. LLM Prompt Injection Prevention

### 6.1 Input Validation in Agents

- [ ] All `BaseAgent._validate_task()` implementations check `input_data` structure
- [ ] Maximum input length enforced per agent type
- [ ] Input encoding validated (UTF-8 only, no control characters)

```python
# Example validation in a coding agent
class CodingAgent(BaseAgent):
    MAX_SPEC_LENGTH = 50_000  # characters

    async def _validate_task(self, task: TaskDefinition) -> bool:
        spec = task.input_data.get("specification", "")
        if not spec or len(spec) > self.MAX_SPEC_LENGTH:
            return False
        # Check for known injection patterns
        if self._contains_injection_markers(spec):
            self._logger.warning(
                "potential_prompt_injection",
                task_id=task.task_id,
                pattern="injection_marker_detected",
            )
            return False
        return True

    @staticmethod
    def _contains_injection_markers(text: str) -> bool:
        """Check for common prompt injection patterns."""
        markers = [
            "ignore previous instructions",
            "disregard above",
            "system prompt:",
            "you are now",
            "new instructions:",
        ]
        text_lower = text.lower()
        return any(m in text_lower for m in markers)
```

### 6.2 Output Validation Between Agents

- [ ] CodingAgent output validated before passing to ReviewAgent
- [ ] ReviewAgent output validated before passing to TestAgent
- [ ] Each agent's `TaskResult.output_data` conforms to expected schema
- [ ] Cross-agent data flow sanitized at the WorkflowEngine level

### 6.3 Monitoring for Injection Attempts

- [ ] MetricsCollector tracks rejected tasks: `conductorai_errors_total{error_code="TASK_VALIDATION_FAILED"}`
- [ ] Structured logs include injection detection events
- [ ] Alerting configured for spikes in validation failures

```python
# In MetricsCollector, track injection attempts
metrics.record_error("PROMPT_INJECTION_DETECTED")
```

---

## 7. Audit Trail and Logging

### 7.1 Structured Logging Review

- [ ] All security-relevant events logged via `structlog`
- [ ] Log entries include: timestamp, user_id, action, resource, result
- [ ] Sensitive data is redacted from logs (API keys, passwords)
- [ ] Log retention meets compliance requirements (minimum 90 days)

### 7.2 RBAC Audit

- [ ] `RBACManager.require_permission()` raises `PermissionDeniedError` with full context
- [ ] Permission denial events logged with user_id, attempted permission, and role
- [ ] Role assignment changes (`assign_role`, `revoke_role`) logged
- [ ] ADMIN role assignments reviewed quarterly

```python
# RBACManager produces auditable denial events
from conductor.core.rbac import RBACManager, Role, Permission, PermissionDeniedError

rbac = RBACManager()
rbac.assign_role("alice", Role.ADMIN)
rbac.assign_role("bob", Role.VIEWER)

try:
    rbac.require_permission("bob", Permission.CONFIG_MODIFY)
except PermissionDeniedError as e:
    # PermissionDeniedError includes:
    #   e.user_id = "bob"
    #   e.permission = "config:modify"
    #   e.details = {"role": "viewer"}
    logger.warning("permission_denied", **e.details)
```

---

## 8. Audit Execution Checklist

| # | Audit Item | Frequency | Owner | Last Completed | Status |
|---|-----------|-----------|-------|----------------|--------|
| 1 | Dependency scan (pip-audit + safety) | Every PR + weekly | DevSecOps | | |
| 2 | Secret rotation verification | Monthly | Security | | |
| 3 | Redis TLS certificate expiry check | Monthly | Infrastructure | | |
| 4 | Container image scan (Trivy) | Every build | CI/CD | | |
| 5 | RBAC role assignment review | Quarterly | Security | | |
| 6 | LLM prompt injection test suite | Quarterly | AppSec | | |
| 7 | Network firewall rules review | Quarterly | Infrastructure | | |
| 8 | OWASP AI Top 10 assessment | Semi-annually | Security | | |
| 9 | Penetration test (see penetration-testing-guide.md) | Annually | External | | |
| 10 | Full security audit | Annually | External + Internal | | |
