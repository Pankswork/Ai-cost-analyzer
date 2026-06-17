#!/bin/bash
cd /home/panks/Ai-cost-analyzer/website/backend
export APP_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bestfreeaifor
export APP_JWT_SECRET_KEY=dev-secret-key
export APP_ENVIRONMENT=development
export APP_CORS_ORIGINS=["http://localhost:4321","http://localhost:8000"]
nohup /home/panks/Ai-cost-analyzer/website/backend/.venv/bin/uvicorn app.main:app --port 8000 --host 0.0.0.0 > /tmp/backend.log 2>&1 &
echo $!
