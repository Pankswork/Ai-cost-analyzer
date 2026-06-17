#!/bin/bash
set -euo pipefail

# Local cost analysis script — runs on-demand from your machine
# Usage: ZEN_API_KEY="zk-xxx" WEBSITE_URL="https://..." ./scripts/local-analysis.sh

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
ADMIN_API_KEY="${ADMIN_API_KEY:-}"

echo "Triggering cost analysis..."
curl -s -X POST "${BACKEND_URL}/api/analysis/run" \
  -H "Authorization: Bearer ${ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"triggered_by": "local"}'

echo ""
echo "Done! Check the admin panel for results."
