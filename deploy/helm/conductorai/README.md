# ConductorAI Helm Chart

A Helm chart for deploying [ConductorAI](https://github.com/conductorai/conductorai), a multi-agent AI framework for orchestrating specialized AI agents through Development, DevOps, and Monitoring pipelines.

## Prerequisites

- Kubernetes 1.25+
- Helm 3.x
- A Redis instance (for state persistence and message bus)
- An LLM API key (OpenAI, Anthropic, or compatible provider)

## Installing the Chart

```bash
helm install my-conductorai ./deploy/helm/conductorai \
  --set llm.apiKey=YOUR_API_KEY \
  --set redis.password=YOUR_REDIS_PASSWORD
```

Or with a custom values file:

```bash
helm install my-conductorai ./deploy/helm/conductorai -f my-values.yaml
```

## Uninstalling the Chart

```bash
helm uninstall my-conductorai
```

## Configuration

The following table lists the configurable parameters and their default values.

### Image

| Parameter          | Description              | Default          |
|--------------------|--------------------------|------------------|
| `image.repository` | Container image name     | `conductorai`    |
| `image.tag`        | Container image tag      | `latest`         |
| `image.pullPolicy` | Image pull policy        | `IfNotPresent`   |
| `imagePullSecrets` | Image pull secrets       | `[]`             |

### Application

| Parameter                             | Description                      | Default   |
|---------------------------------------|----------------------------------|-----------|
| `replicaCount`                        | Number of replicas               | `2`       |
| `conductor.environment`               | Runtime environment              | `prod`    |
| `conductor.logLevel`                  | Log level                        | `INFO`    |
| `conductor.maxAgentRetries`           | Max retries for failed agents    | `3`       |
| `conductor.workflowTimeoutSeconds`    | Workflow timeout in seconds      | `300`     |
| `conductor.enablePersistence`         | Enable Redis persistence         | `true`    |

### Redis

| Parameter              | Description              | Default                    |
|------------------------|--------------------------|----------------------------|
| `redis.url`            | Redis connection URL     | `redis://redis:6379/0`     |
| `redis.password`       | Redis password           | `""`                       |
| `redis.maxConnections` | Max connection pool size | `10`                       |
| `redis.keyPrefix`      | Key prefix in Redis      | `conductor:`               |
| `redis.socketTimeout`  | Socket timeout seconds   | `5.0`                      |

### LLM

| Parameter          | Description            | Default   |
|--------------------|------------------------|-----------|
| `llm.provider`     | LLM provider           | `openai`  |
| `llm.model`        | Model name             | `gpt-4`   |
| `llm.apiKey`       | API key (stored as Secret) | `""`  |
| `llm.temperature`  | Sampling temperature   | `0.7`     |
| `llm.maxTokens`    | Max tokens per response| `4096`    |

### Resources

| Parameter                | Description           | Default  |
|--------------------------|-----------------------|----------|
| `resources.limits.cpu`   | CPU limit             | `1`      |
| `resources.limits.memory`| Memory limit          | `512Mi`  |
| `resources.requests.cpu` | CPU request           | `250m`   |
| `resources.requests.memory`| Memory request      | `256Mi`  |

### Autoscaling

| Parameter                                    | Description                | Default |
|----------------------------------------------|----------------------------|---------|
| `autoscaling.enabled`                        | Enable HPA                 | `true`  |
| `autoscaling.minReplicas`                    | Minimum replicas           | `2`     |
| `autoscaling.maxReplicas`                    | Maximum replicas           | `10`    |
| `autoscaling.targetCPUUtilizationPercentage` | Target CPU utilization     | `70`    |

### Pod Disruption Budget

| Parameter          | Description               | Default |
|--------------------|---------------------------|---------|
| `pdb.enabled`      | Enable PDB                | `true`  |
| `pdb.minAvailable` | Minimum available pods    | `1`     |

### Service Account

| Parameter                      | Description                  | Default |
|--------------------------------|------------------------------|---------|
| `serviceAccount.create`        | Create a service account     | `true`  |
| `serviceAccount.annotations`   | Service account annotations  | `{}`    |
| `serviceAccount.name`          | Override service account name| `""`    |

### Service

| Parameter           | Description        | Default      |
|---------------------|--------------------|--------------|
| `service.type`      | Service type       | `ClusterIP`  |
| `service.port`      | Service port       | `8080`       |
| `service.targetPort` | Container port    | `8080`       |

## Security

This chart follows Kubernetes security best practices:

- Pods run as non-root user (UID 1000)
- Read-only root filesystem
- All Linux capabilities dropped
- Privilege escalation disabled
- Service account token auto-mount disabled
- Secrets used for sensitive data (API keys, passwords)

## Examples

### Minimal production deployment

```bash
helm install conductorai ./deploy/helm/conductorai \
  --set llm.apiKey=sk-your-openai-key \
  --set redis.url=redis://my-redis:6379/0 \
  --set redis.password=my-redis-password
```

### Using Anthropic as the LLM provider

```bash
helm install conductorai ./deploy/helm/conductorai \
  --set llm.provider=anthropic \
  --set llm.model=claude-3-opus-20240229 \
  --set llm.apiKey=sk-ant-your-key
```

### Disable autoscaling with fixed replicas

```bash
helm install conductorai ./deploy/helm/conductorai \
  --set autoscaling.enabled=false \
  --set replicaCount=3
```
