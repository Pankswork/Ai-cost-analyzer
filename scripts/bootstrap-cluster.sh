#!/bin/bash
# Bootstrap script — one-time setup for the EKS cluster
#
# Steps:
# 1. Configure kubectl for the EKS cluster
# 2. Create the cost-detective namespace
# 3. Create the backend IAM service account (IRSA)
# 4. Annotate External Secrets Operator service account with IRSA
# 5. Apply the root ArgoCD Application
#
# Usage: ./scripts/bootstrap-cluster.sh <cluster-name> <region>

set -euo pipefail

CLUSTER_NAME="${1:-cost-detective-dev}"
REGION="${2:-us-east-1}"

echo "Bootstrapping cluster: $CLUSTER_NAME"

# Step 1: Configure kubectl
echo "-> Configuring kubectl..."
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION"

# Step 2: Create namespaces
echo "-> Creating namespaces..."
kubectl create namespace cost-detective --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Step 3: Create backend service account for IRSA
echo "-> Creating backend service account..."
kubectl create serviceaccount backend \
  -n cost-detective \
  --dry-run=client -o yaml | kubectl apply -f -

# Step 4: Annotate External Secrets Operator service account with IRSA
echo "-> Annotating ESO service account..."
ESO_ROLE_ARN=$(aws iam list-roles --query "Roles[?contains(RoleName, 'cost-detective-${CLUSTER_NAME##*-}-external-secrets')].Arn" --output text)
if [ -n "$ESO_ROLE_ARN" ] && [ "$ESO_ROLE_ARN" != "None" ]; then
  kubectl annotate sa external-secrets -n external-secrets \
    "eks.amazonaws.com/role-arn=$ESO_ROLE_ARN" --overwrite 2>/dev/null || true
  echo "  -> Annotated with $ESO_ROLE_ARN"
else
  echo "  -> ESO IRSA role not found - apply terraform first. Skipping."
fi

# Step 5: Apply ArgoCD root application
echo "-> Applying GitOps root application..."
kubectl apply -f gitops/projects/cost-detective.yaml
kubectl apply -f gitops/root.yaml

echo "Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  1. Verify ArgoCD is running: kubectl get pods -n argocd"
echo "  2. Get ArgoCD admin password: kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath='{.data.password}' | base64 -d"
echo "  3. Frontend: http://$(kubectl get ingress cost-detective -n cost-detective -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
