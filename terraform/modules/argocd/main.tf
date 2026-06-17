# ArgoCD Bootstrap Module
#
# Installs ArgoCD on the EKS cluster using the Helm chart.
# Also creates the root Application (App of Apps pattern) that
# manages all other Kubernetes resources via GitOps.
#
# The App of Apps pattern:
# - Root Application watches the gitops/ directory
# - That directory contains Application manifests for each component
# - Each component Application watches its k8s/ subdirectory
# - All changes flow through Git PRs

# Kubernetes provider configuration for this cluster
provider "kubernetes" {
  host                   = var.cluster_endpoint
  cluster_ca_certificate = base64decode(var.cluster_certificate_authority_data)
}

provider "helm" {
  kubernetes {
    host                   = var.cluster_endpoint
    cluster_ca_certificate = base64decode(var.cluster_certificate_authority_data)
  }
}

# Create the argocd namespace
resource "kubernetes_namespace" "argocd" {
  metadata {
    name = "argocd"
  }
}

# Install ArgoCD via Helm chart
resource "helm_release" "argocd" {
  name       = "argocd"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = "~> 7.0"
  namespace  = kubernetes_namespace.argocd.metadata[0].name

  values = [
    <<-YAML
    # ArgoCD configuration values
    configs:
      params:
        # Allow ArgoCD to manage itself
        application.resourceTrackingMethod: annotation
      cm:
        # Repository connection (SSH or HTTPS)
        repositories: |
          - url: https://github.com/Pankswork/Ai-cost-analyzer.git
            type: git
    server:
      service:
        type: ClusterIP
    YAML
  ]

  depends_on = [kubernetes_namespace.argocd]
}
