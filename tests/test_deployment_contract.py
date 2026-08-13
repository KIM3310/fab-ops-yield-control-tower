from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "infra" / "k8s" / "deployment.yaml"
CONFIGMAP = ROOT / "infra" / "k8s" / "configmap.yaml"
PVC = ROOT / "infra" / "k8s" / "pvc.yaml"
HPA = ROOT / "infra" / "k8s" / "hpa.yaml"
K8S_GUIDE = ROOT / "infra" / "k8s" / "README.md"
MAKEFILE = ROOT / "Makefile"


def test_production_deployment_uses_external_secrets_and_configuration_readiness() -> None:
    deployment = DEPLOYMENT.read_text(encoding="utf-8")
    configmap = CONFIGMAP.read_text(encoding="utf-8")
    guide = K8S_GUIDE.read_text(encoding="utf-8")

    assert 'SEMICONDUCTOR_OPS_MODE: "production"' in configmap
    assert "path: /ready" in deployment
    assert "name: semiconductor-ops-secrets" in deployment
    for key in (
        "FAB_OPS_OPERATOR_TOKEN",
        "FAB_OPS_HANDOFF_SIGNING_KEY",
        "SCANNER_OPERATOR_TOKEN",
        "SCANNER_RESPONSE_SIGNING_KEY",
    ):
        assert f"key: {key}" in deployment
        assert key in guide

    assert "kind: Secret" not in deployment
    assert "kind: Secret" not in configmap
    assert "no Secret values" in guide


def test_sqlite_deployment_is_single_writer_durable_and_not_horizontally_scaled() -> None:
    deployment = DEPLOYMENT.read_text(encoding="utf-8")
    pvc = PVC.read_text(encoding="utf-8")
    guide = K8S_GUIDE.read_text(encoding="utf-8")
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert deployment.count("replicas: 1") == 1
    assert "type: Recreate" in deployment
    assert "persistentVolumeClaim:" in deployment
    assert "claimName: semiconductor-ops-data" in deployment
    assert "emptyDir" not in deployment
    assert "kind: PersistentVolumeClaim" in pvc
    assert "ReadWriteOnce" in pvc
    assert HPA.exists() is False
    assert "infra/k8s/hpa.yaml" not in makefile
    assert "kubectl apply -f infra/k8s/pvc.yaml" in makefile
    for token in ("single replica", "single writer", "no HPA", "shared database"):
        assert token in guide
