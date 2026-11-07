# EKS Production Stack

A three-tier application (frontend, backend, PostgreSQL) on EKS. Every service is a Helm chart, and one
`helmfile.yaml` deploys the whole stack, in dependency order, with one command.

```
                       Route53  <--  ExternalDNS (policy: sync)
                          |
                  AWS Load Balancer Controller (ALB, one per Ingress)
                    |                    |
   ┌─ app-nodes (role=app, Karpenter: spot + on-demand) ──┐   ┌─ db-nodes (role=db, taint workload=database) ─┐
   │  frontend (HPA+VPA)   backend (HPA+VPA)  ───────────────────────►  PostgreSQL (Bitnami chart, gp3 PVC, VPA)  │
   │  Prometheus + Grafana                               │   │  backup CronJob -> S3     ExternalSecret          │
   └──────────────────────────────────────────────────────┘   └────────────────────────────────────────────────┘
   Karpenter (NodePools app + database)    External Secrets Operator <- AWS Secrets Manager
```

| Part | Where |
|---|---|
| Applications (Flask, `/metrics`, `/health`) and their tests | `apps/` |
| Helm charts, one per service | `charts/frontend`, `charts/backend`, `charts/database` (wrapper around the Bitnami PostgreSQL chart) |
| Karpenter NodePools and EC2NodeClass | `charts/karpenter-config` |
| Helmfile: all releases, order, environments | `helmfile.yaml`, `values/`, `environments/` |
| AWS: eksctl config, IAM roles (IRSA), S3 bucket, Karpenter IAM | `aws/` |
| Grafana dashboards (generated) and checks | `scripts/` |

## How the requirements are met

| Section | Where / how |
|---|---|
| 2 Charts | `frontend` and `backend`: Deployment, Service (ClusterIP), Ingress (ALB annotations), HPA, ServiceMonitor, probes, configurable resources. `backend` adds a ConfigMap and reads credentials with `secretKeyRef`. `database` is a wrapper chart: Bitnami `postgresql` pinned to `16.x.x`, `metrics.enabled`, `gp3` persistence, resources, tolerations and nodeAffinity, plus the backup CronJob |
| 3 Helmfile | `helmfile.yaml`: repositories, releases, `needs`, namespaces, `values/` overrides, environments (`helmfile -e staging ...`) |
| 4 Node separation | `aws/cluster.yaml`: `app-nodes` (`role=app`) and `db-nodes` (`role=db`, on-demand, taint `workload=database:NoSchedule`). Apps: `preferred` nodeAffinity for `role=app`. Database: `required` nodeAffinity for `role=db` and the toleration. All configurable in `values.yaml` |
| 5 Monitoring | `kube-prometheus-stack` in `monitoring`: 20Gi storage, 7 days retention, Grafana password from a Secret, `serviceMonitorSelectorNilUsesHelmValues: false`. A ServiceMonitor per service, a dashboard per service (ConfigMap, survives restarts), a PrometheusRule (5xx above 5% for 5 minutes) |
| 6 Autoscaling | metrics-server, HPA (2 to 10, CPU 70%, memory 80%, scale-up 60s, scale-down 300s), VPA in `Off` mode for frontend, backend and the database |
| 7 Backups | CronJob every 6 hours: `pg_dump`, gzip, `aws s3 cp` to `s3://<bucket>/backups/db-<timestamp>.sql.gz`, IRSA, `concurrencyPolicy: Forbid`, `successfulJobsHistoryLimit: 3`. Bucket: versioning, encryption, lifecycle 30/60/90 days |
| 8 ExternalDNS | `policy: sync`, `txtOwnerId`, `domainFilters`, IRSA, hostname annotation on both Ingresses |
| 9 ExternalSecrets | operator in `external-secrets`, ClusterSecretStore, ExternalSecret `db-credentials` (`refreshInterval: 1h`), the backend reads `DB_HOST/PORT/USER/PASSWORD` with `secretKeyRef`. No secret is stored in Git or in values files |
| 10 Karpenter | release `karpenter`, `charts/karpenter-config`: NodePool for apps (c, m, r; spot and on-demand; 20 CPU and 80Gi; `WhenEmptyOrUnderutilized`), NodePool for databases (r; on-demand; taint), EC2NodeClass |
| 11 Integration | `helmfile sync` deploys the seven releases of the table in order, plus a few add-ons (below) |

Releases that are not in the exercise table but are needed: **metrics-server** (EKS does not ship it), **vpa** (recommender only),
**aws-load-balancer-controller** (turns the Ingress objects into ALBs) and **karpenter-config** (the NodePools).
`database` also waits for the Prometheus and VPA CRDs, and `backend` for the load balancer controller.

> **Cost and safety.** This creates real AWS resources: the EKS control plane, 3 or more EC2 nodes, a NAT gateway, two ALBs,
> EBS volumes, a Route53 query load, S3 and Secrets Manager. Expect roughly half a dollar to one dollar per hour. Do it in one sitting and run
> the [clean-up](#clean-up) at the end. The nodes of the two Karpenter pools come on top while the load test runs.
>
> `eksctl` changes your kubeconfig. If it already contains other clusters, use a dedicated file in **every** terminal
> so that no command can reach them: `export KUBECONFIG=$HOME/.kube/eks-production.yaml`.

## 0. Prerequisites

`aws` (configured, with rights for EKS, IAM, EC2, S3, Route53, CloudFormation, SQS), `eksctl`, `kubectl`, `helm` 3.18+,
`helmfile` 1.1+, the plugin `helm plugin install https://github.com/databus23/helm-diff`, `envsubst`, `jq`, `openssl`, `dig`.
A Route53 **public hosted zone** for a domain you own.

The images are built by GitHub Actions (`.github/workflows/apps.yml`) and pushed to GHCR. Make the two packages public
(GitHub, Packages, `eks-stack-backend` / `eks-stack-frontend`, Package settings, Change visibility), otherwise the nodes cannot pull them.

## 1. Deploy (from a clean account)

```bash
export KUBECONFIG=$HOME/.kube/eks-production.yaml
export CLUSTER_NAME=eks-production REGION=us-east-1 KARPENTER_VERSION=1.6.3
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export HOSTED_ZONE_ID=Z0123456789ABC                 # your hosted zone
export BACKUP_BUCKET=${CLUSTER_NAME}-db-backups SECRET_PREFIX=my-app/

# 1. Karpenter IAM: node role, controller policy, SQS queue (before the cluster: the node role is mapped in aws/cluster.yaml)
./aws/karpenter-cloudformation.sh

# 2. The cluster with two managed node groups (about 15 minutes)
envsubst < aws/cluster.yaml | eksctl create cluster -f -
kubectl get nodes -L role                               # app-nodes: role=app, db-nodes: role=db
kubectl describe node -l role=db | grep -A2 Taints      # workload=database:NoSchedule
kubectl apply -f aws/storageclass-gp3.yaml

# 3. IAM roles for service accounts (IRSA), the S3 bucket
./aws/create-irsa-roles.sh
./aws/create-backup-bucket.sh

# 4. The database credentials live in AWS Secrets Manager, never in Git
DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')
aws secretsmanager create-secret --region $REGION --name ${SECRET_PREFIX}production/db-credentials --secret-string \
  "{\"username\":\"app\",\"password\":\"$DB_PASSWORD\",\"host\":\"database-postgresql.production.svc.cluster.local\",\"port\":\"5432\"}"
unset DB_PASSWORD

# 5. Fill in environments/default.yaml: accountId, domain, vpcId (aws eks describe-cluster ... resourcesVpcConfig.vpcId), backup.bucket

# 6. Everything else, one command
helmfile lint
helmfile sync          # the first run: no "diff" before it, the CRDs of the monitoring and secrets releases do not exist yet
helmfile diff          # from now on: preview every change, or `helmfile apply` (diff + sync)
```

`helmfile -e staging sync` uses `environments/staging.yaml` on top of `environments/default.yaml`.

## 2. Verification checklist (Exercise 11.2)

**Pods and scheduling**
```bash
kubectl get pods -A                                     # everything Running or Completed
kubectl get nodes -L role,karpenter.sh/capacity-type
kubectl get pods -n production -o wide                  # frontend and backend on role=app nodes, the database on a role=db node
```

**Networking and DNS**
```bash
kubectl get ingress -n production                       # ADDRESS = the ALB host names
aws route53 list-resource-record-sets --hosted-zone-id $HOSTED_ZONE_ID --query "ResourceRecordSets[?contains(Name,'app.') || contains(Name,'api.')]"
dig +short app.<domain>; dig +short api.<domain>
curl -s http://api.<domain>/health; curl -sI http://app.<domain>       # and the frontend in a browser
kubectl -n external-dns logs deploy/external-dns | tail
```

**Monitoring**
```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090 &     # Status -> Targets: frontend, backend, database
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80 &    # http://localhost:3000
kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d; echo   # user: admin
kubectl get prometheusrule -n production
```
Grafana, folder "General": dashboards Frontend, Backend and Database (they are ConfigMaps, so they survive restarts).

**Autoscaling**
```bash
kubectl get hpa -n production                           # targets and replica counts of frontend and backend
kubectl describe vpa -n production                      # recommendations appear after about 10 minutes
kubectl top nodes; kubectl top pods -n production
# load test: HPA scales up, then Karpenter adds nodes
kubectl -n production run load --image=busybox:1.36 --restart=Never -- /bin/sh -c 'while true; do wget -q -O- http://frontend.production.svc.cluster.local/ >/dev/null; done'
kubectl get hpa -n production -w
```

**Karpenter (Exercise 10.2): 20 frontend replicas.** The HPA owns the replica count, so pin it for the test and make the pods big enough to
need new nodes (20 x 500m CPU is more than the two app nodes can hold):
```bash
kubectl -n production set resources deploy/frontend --requests=cpu=500m
kubectl -n production patch hpa frontend --type merge -p '{"spec":{"minReplicas":20,"maxReplicas":20}}'
kubectl get nodeclaim -w; kubectl get nodes -L role
# undo: helmfile -l name=frontend sync     (and delete the load pod)
```

**Secrets**
```bash
kubectl get externalsecret -n production                # STATUS SecretSynced
kubectl get secret db-credentials -n production -o yaml
kubectl -n production exec deploy/backend -- wget -qO- localhost:8000/ready      # {"status":"ready"}: the backend reaches the database
git grep -iE 'password|secret' -- values charts environments     # nothing but references
```
Rotation: change the value in Secrets Manager (`aws secretsmanager put-secret-value ...`), wait up to `refreshInterval` (1h) or run
`kubectl -n production annotate externalsecret db-credentials force-sync=$(date +%s) --overwrite`, and read the Secret again.
(The PostgreSQL password itself only changes when the database is initialised: rotate the user inside PostgreSQL as well.)

## 3. Backups and restore (Exercise 7.3)

```bash
# manual backup
kubectl -n production create job --from=cronjob/database-postgresql-backup manual-backup-test
kubectl -n production logs job/manual-backup-test -c upload -f           # "uploaded s3://.../db-<timestamp>.sql.gz"
aws s3 ls s3://$BACKUP_BUCKET/backups/

# restore into a FRESH database (a temporary pod), never into the production one
aws s3 cp s3://$BACKUP_BUCKET/backups/db-<timestamp>.sql.gz /tmp/restore.sql.gz
kubectl -n production run restore-test --image=postgres:17-alpine --env POSTGRES_PASSWORD=$(openssl rand -hex 12)
kubectl -n production wait --for=condition=Ready pod/restore-test --timeout=120s
kubectl -n production cp /tmp/restore.sql.gz restore-test:/tmp/restore.sql.gz
kubectl -n production exec restore-test -- sh -c 'psql -U postgres -c "CREATE DATABASE appdb" && gunzip -c /tmp/restore.sql.gz | psql -U postgres -d appdb'

# verify the integrity: the row counts of the source and of the restored copy must match
PGPASS=$(kubectl -n production get secret db-credentials -o jsonpath='{.data.password}' | base64 -d)
kubectl -n production exec database-postgresql-0 -c postgresql -- env PGPASSWORD="$PGPASS" psql -U app -d appdb -tc 'SELECT count(*) FROM items'
kubectl -n production exec restore-test -- psql -U postgres -d appdb -tc 'SELECT count(*) FROM items'
kubectl -n production delete pod restore-test; kubectl -n production delete job manual-backup-test
```
The dump is made with `--clean --if-exists --no-owner`, so it can also be restored over an existing database. The backups are
moved to Standard-IA after 30 days, to Glacier after 60 and deleted after 90 (`aws/s3-lifecycle.json`; Glacier objects must be restored before they can be read).
*A backup that has never been restored is not a backup:* repeat this procedure regularly in a non-production environment.

## 4. Chaos testing (Exercise 11.3, bonus)

| Experiment | Command | Expected |
|---|---|---|
| Kill a frontend pod | `kubectl -n production delete pod -l app.kubernetes.io/name=frontend --field-selector=status.phase=Running --wait=false` (one pod) | The Deployment recreates it, the other replica serves traffic (`minReplicas: 2`) |
| Drain an app node | `kubectl drain <app node> --ignore-daemonsets --delete-emptydir-data` | Pods reschedule; Karpenter adds a node if the capacity is missing |
| Delete the Secret | `kubectl -n production delete secret db-credentials` | ExternalSecrets recreates it on the next sync (force-sync as above) |
| High load | the load test above | HPA scales up, Karpenter provisions nodes |
| Delete the database pod | `kubectl -n production delete pod database-postgresql-0` | The StatefulSet recreates it on a db node and reattaches the PVC: the data is intact |

## 5. Local development

```bash
cd apps/backend  && pip install -r requirements-dev.txt && pytest -q
cd apps/frontend && pip install -r requirements-dev.txt && pytest -q
helm lint charts/frontend charts/backend && helm template backend charts/backend
python3 scripts/gen_dashboards.py                       # regenerates the Grafana dashboards
helmfile --skip-deps -l name=frontend template          # one release, without downloading the other charts
```
CI (`.github/workflows`): `apps` (tests, images to GHCR), `charts`, `helmfile` (lint and template of every release for both environments, release graph),
`aws` (config and policy checks).

## Clean-up

```bash
helmfile destroy                                         # releases; ExternalDNS deletes its Route53 records (policy: sync)
kubectl delete nodeclaim --all                           # Karpenter nodes are removed before the cluster
eksctl delete cluster --name $CLUSTER_NAME --region $REGION --wait
aws cloudformation delete-stack --stack-name Karpenter-$CLUSTER_NAME
for r in external-dns external-secrets db-backup karpenter aws-lb-controller; do
  aws iam list-attached-role-policies --role-name $CLUSTER_NAME-$r --query 'AttachedPolicies[].PolicyArn' --output text | tr '\t' '\n' | while read -r p; do
    aws iam detach-role-policy --role-name $CLUSTER_NAME-$r --policy-arn "$p"
    case "$p" in *"/$CLUSTER_NAME-"*) aws iam delete-policy --policy-arn "$p" ;; esac    # only the policies created here
  done
  aws iam delete-role --role-name $CLUSTER_NAME-$r
done
aws s3 rb s3://$BACKUP_BUCKET --force                    # a versioned bucket: also delete the versions, see the note below
aws secretsmanager delete-secret --secret-id ${SECRET_PREFIX}production/db-credentials --force-delete-without-recovery
```
A versioned bucket keeps old versions and delete markers; `aws s3 rb --force` does not remove them. Empty it in the S3 console
("Empty bucket") or delete the versions with `aws s3api delete-objects`. Finally check that nothing is left (and billed):
`aws eks list-clusters`, `aws ec2 describe-instances --filters Name=tag-key,Values=karpenter.sh/nodepool`, `aws elbv2 describe-load-balancers`,
`aws ec2 describe-nat-gateways --filter Name=state,Values=available`, `aws ec2 describe-volumes --filters Name=status,Values=available`.
