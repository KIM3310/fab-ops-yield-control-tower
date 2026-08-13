#!/usr/bin/env python3
"""Validate wheel data and smoke the installed distribution, not the checkout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path

FIXTURE = "app/domains/fab_ops/fixtures/synthetic_shift.json"
STATIC_ASSETS = {
    "app/static/index.html",
    "app/static/app.js",
    "app/static/style.css",
}


def _wheel(wheel_dir: Path) -> Path:
    wheels = sorted(wheel_dir.glob("semiconductor_ops_platform-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one project wheel in {wheel_dir}, found {len(wheels)}")
    return wheels[0].resolve()


def _validate_archive(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        missing = {FIXTURE, *STATIC_ASSETS} - names
        if missing:
            raise SystemExit(f"wheel data missing from {wheel.name}: {', '.join(sorted(missing))}")
        payload = json.loads(archive.read(FIXTURE))
        index = archive.read("app/static/index.html").decode("utf-8")
    if payload.get("synthetic") is not True or not payload.get("spc_replay_cases"):
        raise SystemExit("packaged fixture lacks synthetic marker or replay cases")
    if "Synthetic fixture only" not in index:
        raise SystemExit("packaged UI is missing its synthetic-data boundary")


def _smoke_installed_wheel(wheel: Path) -> None:
    """Install into a clean target and prove import, fixture, static, and API use."""
    with tempfile.TemporaryDirectory(prefix="fab-ops-wheel-") as raw_tmp:
        tmp = Path(raw_tmp)
        target = tmp / "site-packages"
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--target", str(target), str(wheel)],
            check=True,
            cwd=tmp,
        )
        smoke_code = textwrap.dedent(
            f"""
            import json
            import sys
            from pathlib import Path

            install_root = Path({str(target)!r}).resolve()
            sys.path.insert(0, str(install_root))

            import app
            from app.domains.fab_ops.spc import load_synthetic_scenario
            from app.main import app as application
            from fastapi.testclient import TestClient

            imported_app = Path(app.__file__).resolve()
            if install_root not in imported_app.parents:
                raise SystemExit(f"app imported from checkout instead of wheel target: {{imported_app}}")
            if load_synthetic_scenario().get("synthetic") is not True:
                raise SystemExit("installed fixture smoke failed")

            client = TestClient(application)
            checks = {{
                "/": client.get("/"),
                "/app.js": client.get("/app.js"),
                "/health": client.get("/health"),
                "/ready": client.get("/ready"),
                "/api/fab-ops/v1/control-plan": client.get("/api/fab-ops/v1/control-plan"),
            }}
            failed = {{path: response.status_code for path, response in checks.items() if response.status_code != 200}}
            if failed:
                raise SystemExit(f"installed-wheel API/static smoke failed: {{json.dumps(failed, sort_keys=True)}}")
            if "Synthetic fixture only" not in checks["/"].text:
                raise SystemExit("installed wheel did not serve the packaged static UI")
            if checks["/health"].json().get("status") != "ok":
                raise SystemExit("installed wheel health smoke was not ready in explicit demo mode")
            """
        )
        env = os.environ.copy()
        env.update(
            {
                "SEMICONDUCTOR_OPS_MODE": "demo",
                "PERSISTENCE_BACKEND": "jsonl",
                "FAB_OPS_RUNTIME_STORE_PATH": str(tmp / "fab-events.jsonl"),
                "SCANNER_RUNTIME_STORE_PATH": str(tmp / "scanner-events.jsonl"),
            }
        )
        subprocess.run([sys.executable, "-c", smoke_code], check=True, cwd=tmp, env=env)


def main() -> None:
    wheel_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".tmp-verify/wheels")
    wheel = _wheel(wheel_dir)
    _validate_archive(wheel)
    _smoke_installed_wheel(wheel)
    print(f"installed-wheel validation ok: {wheel.name} (fixture + static UI + import/API smoke)")


if __name__ == "__main__":
    main()
