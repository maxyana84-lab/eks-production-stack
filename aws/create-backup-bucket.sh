#!/usr/bin/env bash
# Section 7.2: S3 bucket for the database dumps: versioning, encryption (SSE-S3), no public access, lifecycle policy.
#   export BACKUP_BUCKET=eks-production-db-backups REGION=us-east-1 ; ./aws/create-backup-bucket.sh
set -euo pipefail
: "${BACKUP_BUCKET:?}" "${REGION:?}"
cd "$(dirname "$0")/.."

if [ "$REGION" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "$BACKUP_BUCKET" --region "$REGION"
else
  aws s3api create-bucket --bucket "$BACKUP_BUCKET" --region "$REGION" --create-bucket-configuration "LocationConstraint=$REGION"
fi
aws s3api put-bucket-versioning --bucket "$BACKUP_BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$BACKUP_BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
aws s3api put-public-access-block --bucket "$BACKUP_BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
python3 scripts/gen_s3_lifecycle.py > /tmp/s3-lifecycle.json      # reads the retention from charts/database/values.yaml
aws s3api put-bucket-lifecycle-configuration --bucket "$BACKUP_BUCKET" --lifecycle-configuration file:///tmp/s3-lifecycle.json
echo "bucket $BACKUP_BUCKET is ready"
