# Fab Ops Yield Control Tower Terraform

Minimal Cloud Run deployment skeleton for `fab-ops-yield-control-tower`.

## Apply

```bash
terraform init
terraform apply \
  -var="project_id=your-project" \
  -var="image=asia-northeast3-docker.pkg.dev/your-project/apps/fab-ops-yield-control-tower:latest"
```

Use `env` to inject `FAB_OPS_OPERATOR_TOKEN` and runtime store configuration.
