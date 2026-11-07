#!/usr/bin/env bash
# Section 10.1: node IAM role, controller policy, SQS interruption queue and the EventBridge rules for Karpenter.
# The official CloudFormation template creates all of them (the IAM setup has many moving parts).
#   export CLUSTER_NAME=eks-production KARPENTER_VERSION=1.6.3 ; ./aws/karpenter-cloudformation.sh
set -euo pipefail
: "${CLUSTER_NAME:?}" "${KARPENTER_VERSION:?}"
curl -fsSL "https://raw.githubusercontent.com/aws/karpenter-provider-aws/v${KARPENTER_VERSION}/website/content/en/preview/getting-started/getting-started-with-karpenter/cloudformation.yaml" \
  -o /tmp/karpenter-cloudformation.yaml
aws cloudformation deploy \
  --stack-name "Karpenter-${CLUSTER_NAME}" \
  --template-file /tmp/karpenter-cloudformation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "ClusterName=${CLUSTER_NAME}"
echo "created: role KarpenterNodeRole-${CLUSTER_NAME}, policy KarpenterControllerPolicy-${CLUSTER_NAME}, SQS queue ${CLUSTER_NAME}"
