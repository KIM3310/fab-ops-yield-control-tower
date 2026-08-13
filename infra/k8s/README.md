# Kubernetes production configuration

`deployment.yaml` runs the non-demo `production` profile. That profile fails closed until both domains have operator tokens and HMAC signing keys. The Deployment references a Kubernetes Secret named `semiconductor-ops-secrets`; no Secret values or deployable Secret manifest are stored in this repository.

Create or rotate the Secret out of band before `make deploy` (shell history and CI log handling are the operator's responsibility):

```bash
kubectl create secret generic semiconductor-ops-secrets \
  --from-literal=FAB_OPS_OPERATOR_TOKEN="$FAB_OPS_OPERATOR_TOKEN" \
  --from-literal=FAB_OPS_HANDOFF_SIGNING_KEY="$FAB_OPS_HANDOFF_SIGNING_KEY" \
  --from-literal=SCANNER_OPERATOR_TOKEN="$SCANNER_OPERATOR_TOKEN" \
  --from-literal=SCANNER_RESPONSE_SIGNING_KEY="$SCANNER_RESPONSE_SIGNING_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Use an external-secret controller or sealed-secret workflow in a managed environment rather than literals. Optional AWS credentials/targets can be injected by the same external secret mechanism; do not add them to `configmap.yaml`.

The liveness probe uses `/health` to distinguish a running process. The readiness probe uses `/ready`, which returns HTTP 503 unless persistence, packaged static assets, operator authentication, and both signing configurations are ready. In explicit `demo` mode only, built-in non-production demo credentials satisfy the auth/signing readiness checks; the checked-in Kubernetes ConfigMap deliberately selects `production`.


## SQLite durability and scaling boundary

The checked-in configuration is deliberately **single replica and single writer**:

- `deployment.yaml` sets `replicas: 1` and `strategy.type: Recreate`, preventing a rolling update from starting two SQLite writers;
- `pvc.yaml` provides a `ReadWriteOnce` persistent volume for `/app/data`, so restarts retain the SQLite runtime/audit ledger; and
- no HPA manifest is deployed or stored in this repository. Horizontal pod autoscaling would split or contend for a file-backed ledger and is incompatible with this topology.

This is a durability improvement over per-pod ephemeral storage, not a highly available database design. Backup/snapshot policy, storage-class selection, restore drills, and maintenance downtime remain deployment-owner responsibilities. Before raising replicas above one or adding an HPA, migrate `DATABASE_URL` and the persistence implementation to a reviewed shared database with concurrency, migrations, backup, and failover controls; then update the validator and these manifests together.
