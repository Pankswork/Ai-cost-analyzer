# AI Cloud Cost Detective

A full-stack DevOps project: scan AWS resources and get AI-powered cost optimization recommendations.

## Architecture

```
GitHub Repo (source of truth)
    │
    ├── GitHub Actions (CI/CD)
    │   ├── CI: lint, test, build, scan (on PR)
    │   ├── CD: build images → push to ECR + DockerHub → update k8s manifests (on merge)
    │   └── Terraform: plan on PR, apply on merge
    │
    └── ArgoCD (GitOps on EKS)
        └── Auto-syncs k8s manifests from Git to the cluster
```

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (Python 3.12) — REST + WebSocket |
| **Frontend** | React 19 + TypeScript + Tailwind CSS |
| **AI** | opencode Zen API (cloud LLM) — no local model needed |
| **Database** | RDS PostgreSQL 16 |
| **Infrastructure** | Terraform (VPC, EKS, RDS, ArgoCD) |
| **Container** | Docker (multi-stage builds) |
| **Orchestration** | EKS (Kubernetes 1.30) |
| **GitOps** | ArgoCD (App of Apps pattern) |
| **CI/CD** | GitHub Actions |
| **Monitoring** | Prometheus + Grafana |
| **Registry** | ECR (primary) + DockerHub (public) |

## Project Structure

```
├── backend/          # FastAPI application
├── frontend/         # React application
├── terraform/        # Infrastructure as Code
├── k8s/              # Kubernetes manifests
├── gitops/           # ArgoCD Application configs
├── .github/          # GitHub Actions workflows
├── scripts/          # Bootstrap & cleanup scripts
└── tests/            # Load tests (Locust)
```

## Prerequisites

- AWS account with admin permissions
- Terraform 1.9+
- Docker
- kubectl
- Node.js 22+
- Python 3.12+

## Deployment

### 1. Infrastructure

```bash
cd terraform/environments/dev
terraform init
terraform plan
terraform apply
```

### 2. Bootstrap Cluster

```bash
./scripts/bootstrap-cluster.sh cost-detective-dev us-east-1
```

### 3. CI/CD

Push to the `main` branch. GitHub Actions will:
1. Build and push Docker images to ECR + DockerHub
2. Update k8s manifest image tags
3. ArgoCD auto-syncs the changes to EKS

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Monitoring

- **Grafana**: https://monitoring.bestfreeaifor.com
- **Prometheus**: Scrapes metrics from the backend every 15s
- **Logs**: Structured JSON logged to stdout (Loki/CloudWatch)

## Security

- opencode Zen API for AI analysis (no local model, no GPU needed)
- IRSA (IAM Roles for Service Accounts) — no static AWS keys
- RDS in private subnet — no public access
- Containers run as non-root with read-only filesystems
- Secrets in AWS Secrets Manager (not in Git)
- ALB terminates HTTPS with ACM certificate
- Dropped all kernel capabilities in containers

## Cost Breakdown

| Service | Estimated Monthly Cost |
|---|---|
| EKS (1 m7i-flex.large) | ~$30 |
| RDS (1 db.t3.micro) | ~$15 |
| NAT Gateway | ~$32 |
| VPC Endpoints | ~$15 |
| **Total** | **~$92/month** |

*With $130 AWS credit, you can run the full stack for ~15 days.*
