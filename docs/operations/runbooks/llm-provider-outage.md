# Runbook: LLM Provider Outage

**Severity:** High
**Components Affected:** LLM Providers (OpenAI, Anthropic), All Agents, WorkflowEngine
**Last Updated:** 2026-03-14

---

## Alert / Symptoms

### How This Is Detected

- Prometheus alert `ConductorAIHighLLMErrorRate` fires
- Structlog entries from `openai_provider` or `anthropic_provider` showing API failures:
  ```
  event="task_execution_failed" error="LLMProviderError: OpenAI rate limit exceeded" agent_id="coding-01" agent_type="coding"
  event="task_execution_failed" error="LLMProviderError: Anthropic connection error" agent_id="review-01" agent_type="review"
  ```
- Health check endpoint returns `unhealthy` for `llm_provider` component

### Observable Symptoms

1. **Task execution failures**: Agents raise `LLMProviderError` with error codes:
   - `LLM_AUTH_ERROR` (HTTP 401) -- Invalid or expired API key
   - `LLM_RATE_LIMIT` (HTTP 429) -- Rate limit exceeded
   - `LLM_CONNECTION_ERROR` -- Network/DNS failure reaching provider API
   - `LLM_API_ERROR` (HTTP 5xx) -- Provider-side server error
   - `LLM_MISSING_DEPENDENCY` -- SDK package not installed (`openai` or `anthropic`)
2. **Empty or missing responses**: LLM returns empty `content` field, causing agents to produce `TaskResult` with `status=FAILED`
3. **Workflow failures cascade**: Multiple tasks fail in sequence since all agents (CODING, REVIEW, TEST, TEST_DATA, DEVOPS, DEPLOYING, MONITOR) depend on LLM calls
4. **Circuit breakers open**: ErrorHandler's per-agent `CircuitBreaker` transitions from `CLOSED` to `OPEN` after consecutive failures reach `failure_threshold` (default 5), blocking further task dispatch to affected agents
5. **Error metrics spike**: `conductorai_errors_total{error_code="TASK_EXECUTION_FAILED"}` increases rapidly

---

## Impact

| Impact Area | Description |
|---|---|
| **All Agent Types** | Every agent (CodingAgent, ReviewAgent, TestAgent, TestDataAgent, DevOpsAgent, DeployingAgent, MonitorAgent) calls the LLM via `generate()` or `generate_with_system()`. All agents stop producing useful output. |
| **Workflow Progress** | WorkflowEngine records `TaskStatus.FAILED` results. If enough tasks fail, the workflow status is set to `FAILED` with errors in `WorkflowState.error_log`. |
| **Circuit Breakers** | After `failure_threshold` consecutive failures, ErrorHandler circuit breakers open per-agent. New task dispatches to those agents are immediately rejected with `ErrorAction.DEAD_LETTER`. |
| **Dead Letter Queue** | Failed tasks accumulate in the ErrorHandler's DLQ, requiring manual reprocessing after recovery. |
| **Cost** | If the issue is rate limiting (429), retries with exponential backoff (RetryPolicy: `initial_delay=1.0s`, `backoff_multiplier=2.0`) consume additional API quota when the limit resets. |

---

## Diagnosis Steps

### Step 1: Identify the Failing Provider

Check which provider is configured:
```bash
# Check environment variable
echo $CONDUCTOR_LLM__PROVIDER
# Values: "openai", "anthropic", "mock"

# Or check conductor.yaml
cat conductor.yaml | grep -A5 "llm:"
```

Check structlog for provider-specific errors:
```bash
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -E "LLMProviderError|LLM_AUTH_ERROR|LLM_RATE_LIMIT|LLM_CONNECTION_ERROR|LLM_API_ERROR"
```

### Step 2: Check Provider Status Pages

- **OpenAI Status:** https://status.openai.com
- **Anthropic Status:** https://status.anthropic.com

Check for active incidents affecting the Chat Completions API (OpenAI) or Messages API (Anthropic).

### Step 3: Test Provider Connectivity Directly

**For OpenAI:**
```bash
# Test API connectivity (requires OPENAI_API_KEY or CONDUCTOR_LLM__API_KEY)
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer ${OPENAI_API_KEY}" \
  https://api.openai.com/v1/models

# Expected: 200
# 401 = invalid API key
# 429 = rate limited
# 5xx = provider issue
```

**For Anthropic:**
```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "x-api-key: ${ANTHROPIC_API_KEY}" \
  -H "anthropic-version: 2023-06-01" \
  https://api.anthropic.com/v1/messages \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'

# Expected: 200
# 401 = invalid API key
# 429 = rate limited
# 5xx = provider issue
```

### Step 4: Check Rate Limits

```bash
# Look for rate limit errors in logs
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep "LLM_RATE_LIMIT"
```

Check Prometheus for LLM request volume:
```promql
# Total LLM requests by provider
rate(conductorai_llm_requests_total[5m])

# LLM requests by provider and model
sum by (provider, model) (rate(conductorai_llm_requests_total[5m]))

# Token consumption rate
rate(conductorai_llm_tokens_total{token_type="prompt"}[5m])
rate(conductorai_llm_tokens_total{token_type="completion"}[5m])
```

### Step 5: Check Circuit Breaker Status

Look for circuit breaker state changes in logs:
```bash
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep -E "circuit_breaker|CircuitBreaker|OPEN|HALF_OPEN"
```

Check which agents have open circuit breakers:
```bash
kubectl logs -l app=conductorai -n conductorai --tail=200 | \
  grep "error_action=dead_letter"
```

### Step 6: Verify API Key Validity

```bash
# Check if API key environment variable is set
kubectl exec -it deployment/conductorai -n conductorai -- \
  env | grep -E "CONDUCTOR_LLM__API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY"

# Check key prefix (should match expected format)
# OpenAI: sk-...
# Anthropic: sk-ant-...
```

---

## Resolution Steps

### Option A: Switch to Alternate LLM Provider

If one provider is down, switch to the other. ConductorAI supports hot-switching via configuration.

**Switch from OpenAI to Anthropic:**
```bash
export CONDUCTOR_LLM__PROVIDER=anthropic
export CONDUCTOR_LLM__MODEL=claude-sonnet-4-20250514
export CONDUCTOR_LLM__API_KEY=sk-ant-your-key-here

# Restart to pick up new config
kubectl rollout restart deployment/conductorai -n conductorai
```

**Switch from Anthropic to OpenAI:**
```bash
export CONDUCTOR_LLM__PROVIDER=openai
export CONDUCTOR_LLM__MODEL=gpt-4o
export CONDUCTOR_LLM__API_KEY=sk-your-key-here

kubectl rollout restart deployment/conductorai -n conductorai
```

**Via conductor.yaml:**
```yaml
llm:
  provider: "anthropic"       # was "openai"
  model: "claude-sonnet-4-20250514"
  api_key: "sk-ant-..."
  temperature: 0.7
  max_tokens: 4096
```

### Option B: Switch to Mock Provider (Emergency Degraded Mode)

If both providers are down, the mock provider returns configurable canned responses. This keeps workflows moving (with placeholder output) while the provider recovers.

```bash
export CONDUCTOR_LLM__PROVIDER=mock
kubectl rollout restart deployment/conductorai -n conductorai
```

**Important:** Mock provider output is not meaningful. Use only to unblock non-LLM-dependent workflow steps or for system health verification.

### Option C: Handle Rate Limiting

If the issue is `LLM_RATE_LIMIT` (429):

1. **Reduce concurrency**: Lower the number of concurrent agents to reduce API call volume:
   ```yaml
   max_agent_retries: 2  # Reduce from default 3 to limit retry-induced load
   ```

2. **The ErrorHandler RetryPolicy already handles rate limits**: The default `retryable_errors` list includes `LLM_RATE_LIMIT`. The exponential backoff (`initial_delay=1.0s`, `backoff_multiplier=2.0`, `max_delay=60.0s`) will automatically space out retries:
   - Attempt 0: ~1s delay
   - Attempt 1: ~2s delay
   - Attempt 2: ~4s delay

3. **If rate limit persists beyond retry budget**, increase the retry policy:
   ```python
   # In code, when constructing ErrorHandler:
   error_handler = ErrorHandler(
       message_bus=bus,
       state_manager=sm,
       default_retry_policy=RetryPolicy(
           max_retries=5,       # was 3
           initial_delay=2.0,    # was 1.0
           max_delay=120.0,      # was 60.0
       ),
   )
   ```

### Option D: Fix API Key Issues

If the error is `LLM_AUTH_ERROR` (401):

1. **Rotate the API key** at the provider's dashboard
2. **Update the secret:**
   ```bash
   # Update Kubernetes secret
   kubectl create secret generic conductorai-llm-key \
     --from-literal=api-key=sk-new-key-here \
     -n conductorai --dry-run=client -o yaml | kubectl apply -f -

   # Or update environment variable
   export CONDUCTOR_LLM__API_KEY=sk-new-key-here

   kubectl rollout restart deployment/conductorai -n conductorai
   ```

### Post-Recovery: Reprocess Dead Letter Queue

After the provider recovers, tasks parked in the DLQ need reprocessing:

1. **Check DLQ contents** in application logs:
   ```bash
   kubectl logs -l app=conductorai -n conductorai --tail=500 | \
     grep "dead_letter_added"
   ```

2. **Restart the application** to reset circuit breakers. Circuit breakers transition from `OPEN` to `HALF_OPEN` after `recovery_timeout` (default 60 seconds), then to `CLOSED` after `success_threshold` (default 2) consecutive successes.

3. **Re-run failed workflows** by submitting new `WorkflowDefinition` objects through the `ConductorAI.run_workflow()` facade.

---

## Prevention

### Monitoring

```yaml
groups:
  - name: conductorai-llm
    rules:
      - alert: ConductorAIHighLLMErrorRate
        expr: rate(conductorai_errors_total{error_code=~"LLM_.*"}[5m]) > 0.5
        for: 2m
        labels:
          severity: high
        annotations:
          summary: "High LLM provider error rate"
          description: "LLM-related errors at {{ $value }}/s. Check provider status and API keys."

      - alert: ConductorAILLMRateLimited
        expr: rate(conductorai_errors_total{error_code="LLM_RATE_LIMIT"}[5m]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "LLM provider rate limiting detected"
          description: "Rate limit errors from LLM provider. Consider reducing concurrency."

      - alert: ConductorAILLMAuthFailure
        expr: increase(conductorai_errors_total{error_code="LLM_AUTH_ERROR"}[5m]) > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "LLM API authentication failure"
          description: "API key may be invalid or expired. Rotate immediately."

      - alert: ConductorAIHighTokenConsumption
        expr: rate(conductorai_llm_tokens_total[1h]) > 100000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Unusually high LLM token consumption"
```

### Configuration Best Practices

1. **Always have a fallback provider configured**: Document both OpenAI and Anthropic API keys in your secrets management system so you can switch quickly.
2. **Set `max_tokens` conservatively**: Default `4096` is reasonable. Avoid `128000` unless necessary -- it increases cost and rate limit risk.
3. **Use `temperature: 0.3-0.5`** for code generation agents (CodingAgent, DevOpsAgent) to reduce variability and token consumption.
4. **Use a proxy or API gateway** (`api_base_url` config) if you need to add rate limiting, caching, or fallback logic at the network layer.

### API Key Management

- Store API keys in Kubernetes secrets, not in `conductor.yaml` or environment variables in plaintext
- Use the `CONDUCTOR_LLM__API_KEY` environment variable sourced from a secret
- Rotate keys on a regular schedule (quarterly minimum)
- Monitor key usage at the provider dashboard for anomalies

---

## Escalation

| Level | Condition | Action |
|---|---|---|
| **L1 - On-Call** | LLM error rate elevated, single provider affected | Switch to alternate provider via config, verify API key |
| **L2 - Platform** | Both providers down or rate limited across all keys | Switch to mock provider, engage provider support, review token consumption |
| **L3 - Engineering** | Persistent LLM failures after provider recovery, circuit breakers not closing | Investigate ErrorHandler circuit breaker configuration, review agent retry logic in `BaseAgent.execute_task()` |
