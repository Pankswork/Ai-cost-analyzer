#!/bin/bash
# Cleanup script — tears down all AWS resources
#
# WARNING: This will destroy all resources created by the project.
# - Deletes the EKS cluster, RDS database, VPC, and all associated resources
# - Does NOT delete S3 buckets with terraform state
#
# Usage: ./scripts/cleanup.sh

set -euo pipefail

echo "⚠️  WARNING: This will destroy all AWS resources for the AI Cost Detective project."
echo "   This action cannot be undone!"
read -p "   Type 'yes' to continue: " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

echo ""
echo "→ Destroying Terraform infrastructure..."
cd terraform/environments/dev
terraform destroy -auto-approve

echo ""
echo "✅ Cleanup complete! All resources have been destroyed."
echo ""
echo "Note: If you want to recreate, you'll need to:"
echo "  1. Re-run: terraform apply"
echo "  2. Re-bootstrap: ./scripts/bootstrap-cluster.sh"
