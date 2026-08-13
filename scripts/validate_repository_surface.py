#!/usr/bin/env python3
"""Validate the repository review surface.

The check is intentionally dependency-free so active and archived repositories can
run the same guard in CI. It verifies public-facing docs, local links, architecture
blueprint hooks, and neutral technical positioning.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn, cast

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ARCH_DOC = ROOT / "docs" / "cloud-ai-architecture.md"
ARCH_MANIFEST = ROOT / "docs" / "architecture" / "blueprint.json"
ARCH_VALIDATOR = ROOT / "scripts" / "validate_architecture_blueprint.py"
ARCH_WORKFLOW = ROOT / ".github" / "workflows" / "architecture-blueprint.yml"
K8S_DEPLOYMENT = ROOT / "infra" / "k8s" / "deployment.yaml"
K8S_CONFIGMAP = ROOT / "infra" / "k8s" / "configmap.yaml"
K8S_PVC = ROOT / "infra" / "k8s" / "pvc.yaml"
K8S_HPA = ROOT / "infra" / "k8s" / "hpa.yaml"
K8S_GUIDE = ROOT / "infra" / "k8s" / "README.md"
DOCKERFILE = ROOT / "Dockerfile"

REQUIRED_FILES = (
    README,
    DOCKERFILE,
    ROOT / ".editorconfig",
    ROOT / "CONTRIBUTING.md",
    ARCH_DOC,
    ARCH_MANIFEST,
    ARCH_VALIDATOR,
    ARCH_WORKFLOW,
    K8S_DEPLOYMENT,
    K8S_CONFIGMAP,
    K8S_PVC,
    K8S_GUIDE,
)

BANNED_TERMS = {
    "hir" + "ing",
    "recr" + "uiter",
    "job" + " seeker",
    "job" + "-seeker",
    "inter" + "view prep",
    "career" + " signal",
    "best" + " fit roles",
    "role" + "-fit",
    "role" + "_fit",
    "cover" + " letter",
    "job" + " description",
    "required" + " qualifications",
    "preferred" + " qualifications",
    "채" + "용",
    "취" + "업",
    "구" + "직",
    "입" + "사",
}

LOCAL_PATH_MARKERS = (
    "/Users/",
    "/home/",
    "C:/Users/",
    "C:\\Users\\",
    "file://",
    "vscode://",
)

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def fail(message: str) -> NoReturn:
    print(f"repository surface validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def require_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        fail(f"missing required file: {path.relative_to(ROOT)}")


def markdown_files() -> list[Path]:
    files = sorted(ROOT.glob("*.md"))
    docs = ROOT / "docs"
    if docs.exists():
        files.extend(sorted(docs.rglob("*.md")))
    return files


TEXT_SUFFIXES = {
    ".css",
    ".go",
    ".js",
    ".json",
    ".html",
    ".jsonl",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yml",
    ".yaml",
}

SKIP_FILENAMES = {
    "Cargo.lock",
    "Pipfile.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}

SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}


def is_skipped(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    has_skipped_name = path.name in SKIP_FILENAMES
    has_skipped_part = any(part in SKIP_PARTS for part in relative.parts)
    return has_skipped_name or has_skipped_part


def code_and_generated_files() -> list[Path]:
    candidates: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        is_text_file = path.is_file() and path.suffix in TEXT_SUFFIXES
        if is_text_file and not is_skipped(path):
            candidates.append(path)
    return candidates


def is_external_or_route(target: str) -> bool:
    lowered = target.lower()
    is_external = lowered.startswith(("http://", "https://", "mailto:", "tel:"))
    is_anchor = target.startswith("#")
    has_local_path_marker = False
    for marker in LOCAL_PATH_MARKERS:
        if target.startswith(marker):
            has_local_path_marker = True
            break
    is_absolute_route = target.startswith("/") and not has_local_path_marker
    return is_external or is_anchor or is_absolute_route


def check_local_link(source: Path, target: str, line: int) -> None:
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    for marker in LOCAL_PATH_MARKERS:
        if marker in target:
            fail(f"local machine path in {source.relative_to(ROOT)}:{line}: {target}")
    if is_external_or_route(target):
        return
    path_part = target.split("#", 1)[0]
    if not path_part:
        return
    candidate = (source.parent / path_part).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        fail(f"link escapes repository in {source.relative_to(ROOT)}:{line}: {target}")
    if not candidate.exists():
        fail(f"broken local link in {source.relative_to(ROOT)}:{line}: {target}")


def check_markdown_links() -> None:
    for path in markdown_files():
        text = read_text(path)
        for match in MARKDOWN_LINK_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            check_local_link(path, match.group(1).strip(), line)


def scan_positioning_terms() -> None:
    paths = markdown_files() + code_and_generated_files()
    for path in paths:
        text = read_text(path).lower()
        for term in BANNED_TERMS:
            if term.lower() in text:
                fail(f"non-neutral positioning term in {path.relative_to(ROOT)}")


def load_manifest() -> dict[str, Any]:
    try:
        loaded = json.loads(ARCH_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid architecture manifest JSON: {exc}")
    if not isinstance(loaded, dict):
        fail("architecture manifest root must be an object")
    return cast(dict[str, Any], loaded)


def check_architecture_surface() -> None:
    manifest = load_manifest()
    required = {
        "schema_version",
        "repository",
        "neutrality",
        "focus",
        "cloud_architecture",
        "ai_engineering",
        "validation",
        "research_grounding",
    }
    missing = required - set(manifest)
    if missing:
        fail(f"architecture manifest missing keys: {', '.join(sorted(missing))}")

    readme = read_text(README)
    for expected in (
        "docs/cloud-ai-architecture.md",
        "docs/architecture/blueprint.json",
        "scripts/validate_architecture_blueprint.py",
    ):
        if expected not in readme:
            fail(f"README missing architecture reference: {expected}")


def check_kubernetes_surface() -> None:
    """Require production Secret references and configuration-aware readiness."""
    deployment = read_text(K8S_DEPLOYMENT)
    configmap = read_text(K8S_CONFIGMAP)
    pvc = read_text(K8S_PVC)
    guide = read_text(K8S_GUIDE)
    makefile = read_text(ROOT / "Makefile")
    required_secret_keys = (
        "FAB_OPS_OPERATOR_TOKEN",
        "FAB_OPS_HANDOFF_SIGNING_KEY",
        "SCANNER_OPERATOR_TOKEN",
        "SCANNER_RESPONSE_SIGNING_KEY",
    )
    if 'SEMICONDUCTOR_OPS_MODE: "production"' not in configmap:
        fail("Kubernetes ConfigMap must select the production runtime profile")
    if "path: /ready" not in deployment:
        fail("Kubernetes readiness probe must use /ready")
    if "name: semiconductor-ops-secrets" not in deployment:
        fail("Kubernetes Deployment is missing the external Secret reference")
    if deployment.count("replicas: 1") != 1 or "type: Recreate" not in deployment:
        fail("file-backed SQLite deployment must enforce one replica with Recreate updates")
    if "emptyDir" in deployment or "persistentVolumeClaim:" not in deployment:
        fail("file-backed SQLite deployment must use durable PVC storage, not emptyDir")
    if "claimName: semiconductor-ops-data" not in deployment:
        fail("SQLite deployment does not reference semiconductor-ops-data")
    if "kind: PersistentVolumeClaim" not in pvc or "ReadWriteOnce" not in pvc:
        fail("SQLite PVC must be a ReadWriteOnce PersistentVolumeClaim")
    if K8S_HPA.exists() or "infra/k8s/hpa.yaml" in makefile:
        fail("HPA must remain absent for the single-writer SQLite deployment")
    if "kubectl apply -f infra/k8s/pvc.yaml" not in makefile:
        fail("make deploy must apply the durable SQLite PVC")
    for token in ("single replica", "single writer", "no HPA", "shared database"):
        if token not in guide:
            fail(f"Kubernetes scaling boundary is not documented: {token}")
    for key in required_secret_keys:
        if deployment.count(f"key: {key}") != 1 or key not in guide:
            fail(f"Kubernetes Secret key is not referenced/documented: {key}")
    for path in (ROOT / "infra" / "k8s").glob("*.yaml"):
        if re.search(r"(?m)^kind:\s*Secret\s*$", read_text(path)):
            fail(f"deployable Secret manifest must not be checked in: {path.relative_to(ROOT)}")


def check_container_contract() -> None:
    dockerfile = read_text(DOCKERFILE)
    first_line = dockerfile.splitlines()[0] if dockerfile.splitlines() else ""
    if not re.fullmatch(r"FROM python:3\.11-slim@sha256:[0-9a-f]{64}", first_line):
        fail("Docker base image must retain an immutable Python 3.11 slim digest")
    copy_index = dockerfile.find("COPY app /app/app")
    install_index = dockerfile.find("pip install --no-cache-dir -e /app")
    if copy_index < 0 or install_index < 0 or copy_index > install_index:
        fail("Docker editable install must run after application source is copied")
    if "HEALTHCHECK" not in dockerfile or "/health" not in dockerfile:
        fail("Dockerfile must retain the runtime health check")


def main() -> None:
    for path in REQUIRED_FILES:
        require_file(path)
    if not read_text(README).strip():
        fail("README.md is empty")
    check_architecture_surface()
    check_container_contract()
    check_kubernetes_surface()
    check_markdown_links()
    scan_positioning_terms()
    print("repository surface validation ok")


if __name__ == "__main__":
    main()
