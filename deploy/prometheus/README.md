# ConductorAI Prometheus Alerting Rules

Prometheus alerting rules for ConductorAI operational monitoring.

## File

| File | Description |
|------|-------------|
| `conductorai-alerts.yml` | PrometheusRule custom resource with five alerting rules |

## Alerts

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `ConductorAIHighWorkflowFailureRate` | warning | 5m | Workflow failure rate > 10% |
| `ConductorAITaskDurationHigh` | warning | 5m | P95 task duration > 60s |
| `ConductorAINoActiveAgents` | critical | 5m | Zero active agents |
| `ConductorAILLMErrorRateHigh` | warning | 5m | LLM error rate > 5% |
| `ConductorAIRedisConnectionFailed` | critical | 2m | Redis health check failing |

## Prerequisites

- Prometheus Operator (kube-prometheus-stack) installed in your cluster
- ConductorAI exposing a `/metrics` endpoint scraped by Prometheus
- ConductorAI running with `prometheus_client` installed (`pip install prometheus-client`)

## Installation

### Kubernetes (Prometheus Operator)

The alerts file is a `PrometheusRule` custom resource. Apply it directly:

```bash
kubectl apply -f conductorai-alerts.yml -n monitoring
```

Verify the rules were loaded:

```bash
kubectl get prometheusrules -n monitoring conductorai-alerts
```

### Standalone Prometheus

If you run Prometheus without the Operator, extract the rule groups from the `spec.groups` field and place them in a standard Prometheus rules file.

Create `conductorai-alerts-standalone.yml`:

```yaml
groups:
  - name: conductorai.workflows
    rules:
      - alert: ConductorAIHighWorkflowFailureRate
        expr: |
          (
            sum(rate(conductorai_workflows_total{status="failure"}[5m]))
            /
            clamp_min(sum(rate(conductorai_workflows_total[5m])), 1)
          ) > 0.10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "ConductorAI workflow failure rate exceeds 10%"
      # ... (copy remaining rules from spec.groups)
```

Then reference it in your `prometheus.yml`:

```yaml
rule_files:
  - "/etc/prometheus/rules/conductorai-alerts-standalone.yml"
```

Reload Prometheus:

```bash
curl -X POST http://localhost:9090/-/reload
```

### Helm (kube-prometheus-stack values)

Add the rules directly in your Helm values file:

```yaml
additionalPrometheusRulesMap:
  conductorai-alerts:
    groups:
      - name: conductorai.workflows
        rules:
          - alert: ConductorAIHighWorkflowFailureRate
            # ... paste rule content here
```

## Configuring the Scrape Target

Ensure Prometheus scrapes the ConductorAI metrics endpoint. For Kubernetes, add a `ServiceMonitor`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: conductorai
  labels:
    app: conductorai
spec:
  selector:
    matchLabels:
      app: conductorai
  endpoints:
    - port: http-metrics
      path: /metrics
      interval: 15s
```

For standalone Prometheus, add a scrape config:

```yaml
scrape_configs:
  - job_name: conductorai
    scrape_interval: 15s
    static_configs:
      - targets: ["conductorai:8000"]
    metrics_path: /metrics
```

## Alertmanager Routing

Route ConductorAI alerts to the appropriate notification channel. Example Alertmanager config:

```yaml
route:
  routes:
    - match:
        severity: critical
      receiver: pagerduty-conductorai
    - match_re:
        alertname: "ConductorAI.*"
      receiver: slack-conductorai

receivers:
  - name: slack-conductorai
    slack_configs:
      - channel: "#conductorai-alerts"
        send_resolved: true
  - name: pagerduty-conductorai
    pagerduty_configs:
      - service_key: "<your-pagerduty-key>"
```

## Customization

To adjust thresholds, edit the `expr` field in `conductorai-alerts.yml`. For example, to change the workflow failure rate threshold from 10% to 5%:

```yaml
expr: |
  (
    sum(rate(conductorai_workflows_total{status="failure"}[5m]))
    /
    clamp_min(sum(rate(conductorai_workflows_total[5m])), 1)
  ) > 0.05
```

To change the evaluation window, modify the `[5m]` range selector in the `expr` and the `for` duration.
