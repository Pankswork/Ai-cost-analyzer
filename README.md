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
| **Frontend** | Astro 6 + TypeScript + TailwindCSS 4 |
| **Backend** | FastAPI (Python 3.12) — REST API |
| **AI** | opencode Zen API (cloud LLM) — no local model needed |
| **Database** | RDS PostgreSQL 16.14 |
| **Infrastructure** | Terraform (VPC, EKS, RDS, ArgoCD) |
| **Container** | Docker (multi-stage builds) |
| **Orchestration** | EKS (Kubernetes 1.36) |
| **GitOps** | ArgoCD (App of Apps pattern) |
| **CI/CD** | GitHub Actions |
| **Monitoring** | Prometheus + Grafana |
| **Registry** | ECR (primary) + DockerHub (public) |
| **AWS Lambda** | Log anomaly detection + JWT secret rotation |

## Project Structure

```
├── website/          # Full application
│   ├── backend/      #   FastAPI app (app/main.py)
│   └── src/          #   Astro frontend (pages, components, styles)
├── terraform/        # Infrastructure as Code
├── k8s/              # Kubernetes manifests
├── gitops/           # ArgoCD Application configs
├── lambda/           # AWS Lambda functions
├── .github/          # GitHub Actions workflows
├── scripts/          # Bootstrap & cleanup scripts
└── tests/            # Load tests (Locust)
```

## Prerequisites

- AWS account with admin permissions
- Terraform 1.11+
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

### Quick start (Docker Compose)

```bash
cd website
docker compose up --build
```

Starts PostgreSQL, backend (FastAPI on `:8000`), and frontend (Nginx on `:80`).

### Backend (manual)

```bash
cd website/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API at `http://localhost:8000` — Swagger docs at `http://localhost:8000/docs`.

### Frontend (manual)

```bash
cd website
npm install
npm run dev
```

Astro dev server starts on `:4321` and proxies `/api` to the backend at `:8000`.

### Database (standalone)

```bash
docker run -d --name pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=bestfreeaifor \
  -p 5432:5432 \
  postgres:16-alpine
```

### Seed data

The backend auto-seeds admin users on first startup. To also load the AI tools catalog into the database:

```bash
cd website/backend
source .venv/bin/activate
python seed_data.py
```

Requires PostgreSQL to be running (via Docker Compose or standalone), venv activated, and `website/src/data/tools.ts` present.

## Monitoring

- **Prometheus** scrapes metrics from the backend every 15s
- **Grafana** dashboards via kube-prometheus-stack
- **Logs**: Structured JSON logged to stdout (Loki/CloudWatch)

## Security

- opencode Zen API for AI analysis (no local model, no GPU needed)
- IRSA (IAM Roles for Service Accounts) — no static AWS keys
- RDS in private subnet — no public access
- Containers run as non-root with read-only filesystems
- Secrets in AWS Secrets Manager (not in Git)
- ALB terminates HTTPS with ACM certificate
- WAF Web ACL (rate limiting, SQLi/XSS prevention)
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
