# ConductorAI Grafana Dashboards

Pre-built Grafana dashboards for monitoring ConductorAI workflows, tasks, agents, and LLM usage.

## Dashboards

| File | UID | Description |
|------|-----|-------------|
| `conductorai-overview.json` | `conductorai-overview` | Workflow throughput, task throughput and latency percentiles, active agents, error rates |
| `conductorai-llm.json` | `conductorai-llm` | LLM request rates by provider/model, token usage (prompt vs completion) |

## Prerequisites

- Grafana 10.0+
- A Prometheus datasource configured in Grafana that scrapes ConductorAI metrics
- ConductorAI running with `prometheus_client` installed (`pip install prometheus-client`)

## Import via Grafana UI

1. Open Grafana and navigate to **Dashboards > Import** (or visit `/dashboard/import`).
2. Click **Upload JSON file** and select one of the dashboard JSON files from this directory.
3. On the import screen, select the Prometheus datasource that scrapes your ConductorAI instance.
4. Click **Import**.
5. Repeat for each dashboard file.

## Import via Grafana Provisioning

To auto-load dashboards on Grafana startup, add a provisioning configuration.

Create or edit `/etc/grafana/provisioning/dashboards/conductorai.yml`:

```yaml
apiVersion: 1

providers:
  - name: conductorai
    orgId: 1
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards/conductorai
      foldersFromFilesStructure: false
```

Then copy the JSON files into that directory:

```bash
cp conductorai-overview.json conductorai-llm.json /var/lib/grafana/dashboards/conductorai/
```

Restart Grafana or wait for the update interval to pick up the new dashboards.

## Import via Grafana API

```bash
# Set your Grafana URL and API key
GRAFANA_URL="http://localhost:3000"
GRAFANA_API_KEY="your-api-key"

for dashboard in conductorai-overview.json conductorai-llm.json; do
  curl -X POST "${GRAFANA_URL}/api/dashboards/import" \
    -H "Authorization: Bearer ${GRAFANA_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
      \"dashboard\": $(cat "${dashboard}"),
      \"overwrite\": true,
      \"inputs\": [{
        \"name\": \"DS_PROMETHEUS\",
        \"type\": \"datasource\",
        \"pluginId\": \"prometheus\",
        \"value\": \"Prometheus\"
      }]
    }"
done
```

## Import in Kubernetes (Sidecar)

If you use the Grafana Helm chart with the sidecar enabled, create a ConfigMap:

```bash
kubectl create configmap conductorai-grafana-dashboards \
  --from-file=conductorai-overview.json \
  --from-file=conductorai-llm.json \
  -n monitoring

kubectl label configmap conductorai-grafana-dashboards \
  grafana_dashboard=1 \
  -n monitoring
```

The Grafana sidecar will detect the label and load the dashboards automatically.

## Metrics Reference

These dashboards visualize the following Prometheus metrics exposed by ConductorAI:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `conductorai_workflows_total` | Counter | `status` | Total workflows executed |
| `conductorai_tasks_total` | Counter | `agent_type`, `status` | Total tasks executed |
| `conductorai_task_duration_seconds` | Histogram | `agent_type` | Task execution duration (buckets: 0.1s - 300s) |
| `conductorai_active_agents` | Gauge | `agent_type` | Currently active agents |
| `conductorai_errors_total` | Counter | `error_code` | Errors by error code |
| `conductorai_llm_requests_total` | Counter | `provider`, `model` | LLM API requests |
| `conductorai_llm_tokens_total` | Counter | `provider`, `token_type` | LLM tokens consumed |
