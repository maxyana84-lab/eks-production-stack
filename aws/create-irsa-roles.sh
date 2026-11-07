#!/usr/bin/env bash
# IAM roles for service accounts (IRSA). No AWS keys are stored anywhere: every role trusts one
# Kubernetes service account through the cluster's OIDC provider.
#
#   export CLUSTER_NAME=eks-production REGION=us-east-1 HOSTED_ZONE_ID=Z0123456789ABC \
#          BACKUP_BUCKET=eks-production-db-backups SECRET_PREFIX=my-app/
#   ./aws/create-irsa-roles.sh
#
# Role names are <cluster>-<component>: they are exactly the ARNs used by the helmfile values.
set -euo pipefail
: "${CLUSTER_NAME:?}" "${REGION:?}" "${HOSTED_ZONE_ID:?}" "${BACKUP_BUCKET:?}" "${SECRET_PREFIX:?}"
cd "$(dirname "$0")"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
OIDC=$(aws eks describe-cluster --name "$CLUSTER_NAME" --region "$REGION" --query 'cluster.identity.oidc.issuer' --output text | sed 's|^https://||')
export REGION ACCOUNT_ID HOSTED_ZONE_ID BACKUP_BUCKET SECRET_PREFIX

# create_role <component> <namespace> <service account> <policy arn>
create_role() {
  local component=$1 namespace=$2 sa=$3 policy_arn=$4 role="${CLUSTER_NAME}-$1"
  cat > "/tmp/trust-${component}.json" <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Federated":"arn:aws:iam::${ACCOUNT_ID}:oidc-provider/${OIDC}"},
  "Action":"sts:AssumeRoleWithWebIdentity",
  "Condition":{"StringEquals":{"${OIDC}:sub":"system:serviceaccount:${namespace}:${sa}","${OIDC}:aud":"sts.amazonaws.com"}}}]}
JSON
  aws iam create-role --role-name "$role" --assume-role-policy-document "file:///tmp/trust-${component}.json" >/dev/null
  aws iam attach-role-policy --role-name "$role" --policy-arn "$policy_arn"
  echo "role $role  <-  system:serviceaccount:${namespace}:${sa}"
}

# create_policy <name> <json file>   (variables in the file are filled in with envsubst)
create_policy() {
  envsubst < "$2" > "/tmp/policy-$1.json"
  aws iam create-policy --policy-name "${CLUSTER_NAME}-$1" --policy-document "file:///tmp/policy-$1.json" --query Policy.Arn --output text
}

create_role external-dns     external-dns     external-dns                  "$(create_policy external-dns policies/external-dns.json)"
create_role external-secrets external-secrets external-secrets              "$(create_policy external-secrets policies/external-secrets.json)"
create_role db-backup        production       database-postgresql-backup    "$(create_policy db-backup policies/db-backup.json)"

# the controller policy of Karpenter comes from the CloudFormation stack (aws/karpenter-cloudformation.sh)
create_role karpenter        karpenter        karpenter                     "arn:aws:iam::${ACCOUNT_ID}:policy/KarpenterControllerPolicy-${CLUSTER_NAME}"

# the AWS Load Balancer Controller publishes its official policy
LBC_VERSION=${LBC_VERSION:-v2.13.4}
curl -fsSL "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/${LBC_VERSION}/docs/install/iam_policy.json" -o /tmp/policy-aws-lb-controller.json
LBC_ARN=$(aws iam create-policy --policy-name "${CLUSTER_NAME}-aws-lb-controller" --policy-document file:///tmp/policy-aws-lb-controller.json --query Policy.Arn --output text)
create_role aws-lb-controller kube-system aws-load-balancer-controller "$LBC_ARN"
