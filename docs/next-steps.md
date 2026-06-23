# AI Cloud Cost Detective — Next Steps Roadmap

All pipelines (CI, CD, Terraform) are green. This document captures the prioritized gaps and improvements.

## Priority 1: Testing & Code Quality

- [ ] **Write unit/integration tests** — `tests/` has only a locustfile; `pytest` step in CI never runs.
- [ ] **Add Alembic migrations** — `Base.metadata.create_all` at startup is risky for production schema changes.
- [ ] **Fix docs vs reality** — README says "React 19", "backend/", "frontend/", "Ollama" — actual stack is Astro, `website/backend/`, `website/`, Zen API.

## Priority 2: Operational Completeness

- [ ] **Wire up Slack webhook & Admin API key** — CronJob references `admin-api-key` from `backend-secrets` but the ExternalSecret doesn't sync it.
- [ ] **Add VPC endpoints** — CloudWatch, Secrets Manager, SSM are missing; pods go through NAT Gateway (cost + latency).
- [ ] **Fix ExternalSecret name** — References `cost-detective-backend` but actual AWS secret is `cost-detective-dev-backend`.

## Priority 3: Feature Gaps

- [ ] **WebSocket scan endpoint** — Documented but not coded; would give real-time progress for cost analysis.
- [ ] **Non-admin cost analysis UI** — Reports only visible at `/admin/cost-reports`; no user-facing dashboard.
- [ ] **ServiceMonitor for Prometheus** — Scraping relies on pod annotations; official ServiceMonitor is more reliable.

## Priority 4: Infrastructure

- [ ] **Staging environment** — Only `dev/` exists in Terraform.
- [ ] **CloudFront CDN** — ALB is internet-facing directly; no CDN for static assets.
- [ ] **Cost alerting pipeline** — AWS Budget → SNS → SQS → Lambda → Slack is documented but not implemented.
- [ ] **Fix `local-analysis.sh`** — Currently a stub; doesn't do the full local scan documented in `deployment-plan.md`.

## Priority 5: Polish

- [ ] **Pydantic response models** — Admin API returns raw SQLAlchemy objects instead of Pydantic models.
- [ ] **Multi-env Terraform** — Only `terraform/environments/dev/` exists.
- [ ] **EKS version consistency** — Cluster uses 1.36; README says 1.30.
