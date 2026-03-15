# ConductorAI - Kubernetes Deployment

Kubernetes manifests for deploying ConductorAI to a cluster.

## Prerequisites

- Kubernetes cluster (v1.25+)
- `kubectl` configured with cluster access
- Docker image `conductorai:latest` built and available to the cluster
- [Metrics Server](https://github.com/kubernetes-sigs/metrics-server) installed (required for HPA)

## Build the Docker Image

```bash
# From the repository root
docker build -t conductorai:latest .
```

## Configure Secrets

Replace the placeholder values in `secret.yaml` before applying:

```bash
# Encode your real credentials
echo -n "sk-your-openai-api-key" | base64
echo -n "your-redis-password"    | base64
```

Edit `secret.yaml` and replace the base64-encoded placeholder values with your encoded credentials.

> **Production recommendation:** Use Sealed Secrets, External Secrets Operator, or HashiCorp Vault instead of storing secrets in plain YAML files.

## Deploy

Apply manifests in order (namespace first):

```bash
# 1. Create the namespace
kubectl apply -f namespace.yaml

# 2. Apply configuration and secrets
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml

# 3. Deploy the application
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# 4. Apply autoscaling and disruption budget
kubectl apply -f hpa.yaml
kubectl apply -f pdb.yaml
```

Or apply everything at once:

```bash
kubectl apply -f namespace.yaml
kubectl apply -f .
```

## Verify

```bash
# Check pods are running
kubectl get pods -n conductorai

# Check deployment status
kubectl rollout status deployment/conductorai -n conductorai

# Check service
kubectl get svc -n conductorai

# Check HPA status
kubectl get hpa -n conductorai

# View pod logs
kubectl logs -n conductorai -l app=conductorai --tail=50

# Describe a pod for troubleshooting
kubectl describe pod -n conductorai -l app=conductorai
```

## Manifest Overview

| File              | Resource                   | Purpose                                      |
|-------------------|----------------------------|----------------------------------------------|
| `namespace.yaml`  | Namespace                  | Isolates ConductorAI resources               |
| `configmap.yaml`  | ConfigMap                  | Non-sensitive configuration (env vars + YAML) |
| `secret.yaml`     | Secret                     | API keys and passwords (base64 placeholders) |
| `deployment.yaml` | Deployment                 | Pod spec with probes, security, resources    |
| `service.yaml`    | Service (ClusterIP)        | Internal networking on port 8080             |
| `hpa.yaml`        | HorizontalPodAutoscaler    | Autoscale 2-10 replicas at 70% CPU           |
| `pdb.yaml`        | PodDisruptionBudget        | Guarantees 1 pod available during disruptions |

## Architecture Notes

- **Replicas:** Starts with 2 pods, autoscales up to 10 based on CPU.
- **Security:** Runs as non-root (UID 1000), read-only root filesystem, no privilege escalation.
- **Probes:** Liveness and readiness probes verify the Python package imports correctly.
- **Volumes:** `conductor.yaml` is mounted from the ConfigMap; `/tmp` is an emptyDir for write access.
- **Redis:** Expects a Redis service at `conductorai-redis:6379` within the namespace. Deploy Redis separately (e.g., via Helm chart `bitnami/redis`).

## Tear Down

```bash
kubectl delete -f .
kubectl delete namespace conductorai
```
