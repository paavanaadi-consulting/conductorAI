# ConductorAI - AWS Terraform Deployment

Terraform templates for deploying ConductorAI on AWS using EKS and ElastiCache Redis.

## Architecture

- **VPC** with 3 public and 3 private subnets across availability zones
- **EKS** managed Kubernetes cluster with autoscaling node group
- **ElastiCache Redis** replication group with cluster mode, encryption, and automatic failover
- **IRSA** (IAM Roles for Service Accounts) for secure Secrets Manager access from pods

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials
- [kubectl](https://kubernetes.io/docs/tasks/tools/) for interacting with the cluster after deployment

## Quick Start

1. **Initialize Terraform:**

   ```bash
   cd deploy/terraform
   terraform init
   ```

2. **Review the plan:**

   ```bash
   terraform plan
   ```

3. **Apply the configuration:**

   ```bash
   terraform apply
   ```

4. **Configure kubectl:**

   ```bash
   aws eks update-kubeconfig \
     --region us-west-2 \
     --name $(terraform output -raw eks_cluster_name)
   ```

5. **Verify connectivity:**

   ```bash
   kubectl get nodes
   ```

## Configuration

Override default values by creating a `terraform.tfvars` file:

```hcl
project_name            = "conductorai"
environment             = "staging"
aws_region              = "us-east-1"
vpc_cidr                = "10.0.0.0/16"
eks_cluster_version     = "1.28"
eks_node_instance_types = ["t3.large"]
eks_min_nodes           = 3
eks_max_nodes           = 15
redis_node_type         = "cache.r6g.large"
redis_num_cache_nodes   = 3

tags = {
  Team    = "platform"
  CostCenter = "engineering"
}
```

## Remote State (Recommended for Teams)

Uncomment the backend block in `versions.tf` and create the S3 bucket and DynamoDB table:

```bash
aws s3 mb s3://conductorai-terraform-state --region us-west-2

aws dynamodb create-table \
  --table-name conductorai-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2
```

Then reinitialize:

```bash
terraform init -migrate-state
```

## Outputs

After `terraform apply`, the following outputs are available:

| Output                    | Description                                      |
| ------------------------- | ------------------------------------------------ |
| `eks_cluster_endpoint`    | EKS API server endpoint URL                      |
| `eks_cluster_name`        | Name of the EKS cluster                          |
| `redis_primary_endpoint`  | Redis configuration endpoint (cluster mode)      |
| `redis_port`              | Redis port number                                |
| `vpc_id`                  | VPC identifier                                   |

## Connecting ConductorAI to Redis

ConductorAI uses Redis for its message bus and state persistence. After deployment, configure the application with the Redis endpoint:

```bash
export CONDUCTOR_REDIS_URL="rediss://$(terraform output -raw redis_primary_endpoint):$(terraform output -raw redis_port)"
```

Note: The `rediss://` scheme (with double s) indicates TLS-encrypted connections, which is required since transit encryption is enabled.

## Kubernetes Service Account Setup

Create the namespace and annotate the service account with the IRSA role:

```bash
kubectl create namespace conductorai

kubectl create serviceaccount conductorai \
  --namespace conductorai

kubectl annotate serviceaccount conductorai \
  --namespace conductorai \
  eks.amazonaws.com/role-arn=$(terraform output -raw conductorai_irsa_role_arn)
```

## Teardown

```bash
terraform destroy
```

## File Structure

```
deploy/terraform/
  versions.tf      - Terraform and provider version constraints
  variables.tf     - Input variables with defaults
  main.tf          - Provider config and common locals
  vpc.tf           - VPC with public/private subnets
  eks.tf           - EKS cluster and managed node group
  elasticache.tf   - Redis replication group
  iam.tf           - IRSA role for Secrets Manager access
  outputs.tf       - Exported values for downstream use
  README.md        - This file
```
