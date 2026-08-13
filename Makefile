.PHONY: check-python install run test lint typecheck smoke package-check validate docker-build docker-run deploy pages-deploy clean coverage verify verify-strict

PYTHON_BIN ?= python3
VENV ?= .venv
PYTHON := $(VENV)/bin/python
VENV_STAMP := $(VENV)/.installed-dev
IMAGE  ?= semiconductor-ops-platform
TAG    ?= latest

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

check-python:
	@$(PYTHON_BIN) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1 || { \
		echo "Python 3.11+ is required to create $(VENV)."; \
		echo "Set PYTHON_BIN=/path/to/python3.11, for example: make PYTHON_BIN=/opt/homebrew/bin/python3.11 verify"; \
		exit 1; \
	}

install: $(VENV_STAMP)

$(VENV_STAMP): pyproject.toml requirements.txt | check-python
	@if [ ! -x "$(PYTHON)" ] || ! $(PYTHON) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1; then \
		rm -rf $(VENV); \
		$(PYTHON_BIN) -m venv $(VENV); \
	fi
	@if ! $(PYTHON) -m pip --version >/dev/null 2>&1; then \
		$(PYTHON) -m ensurepip --upgrade; \
	fi
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"
	touch $(VENV_STAMP)

run: install
	SEMICONDUCTOR_OPS_MODE=$${SEMICONDUCTOR_OPS_MODE:-demo} $(PYTHON) -m uvicorn app.main:app --reload

test: install
	SEMICONDUCTOR_OPS_MODE=demo PERSISTENCE_BACKEND=jsonl $(PYTHON) -m pytest -q

coverage: install
	SEMICONDUCTOR_OPS_MODE=demo PERSISTENCE_BACKEND=jsonl $(PYTHON) -m pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml --cov-report=html --cov-fail-under=80 -q

lint: install
	$(PYTHON) -m ruff check app tests scripts

typecheck: install
	$(PYTHON) -m mypy app --ignore-missing-imports

smoke: install
	@set -eu; \
	PORT=8099; \
	LOG=/tmp/fab-ops-platform-smoke.log; \
	SEMICONDUCTOR_OPS_MODE=demo $(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port $$PORT >$$LOG 2>&1 & \
	pid=$$!; \
	trap 'kill $$pid >/dev/null 2>&1 || true' EXIT INT TERM; \
	for _ in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS "http://127.0.0.1:$$PORT/health" >/dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done; \
	curl -fsS "http://127.0.0.1:$$PORT/health" >/dev/null; \
	curl -fsS "http://127.0.0.1:$$PORT/ready" | grep -q '"ready":true'; \
	curl -fsS "http://127.0.0.1:$$PORT/api/resource-pack" >/dev/null; \
	curl -fsS "http://127.0.0.1:$$PORT/api/fab-ops/architecture-pack" >/dev/null; \
	curl -fsS "http://127.0.0.1:$$PORT/api/fab-ops/v1/control-plan" >/dev/null; \
	curl -fsS "http://127.0.0.1:$$PORT/api/fab-ops/v1/lots/lot-8812/disposition" | grep -q 'HOLD_FOR_CONTAINMENT'; \
	curl -fsS "http://127.0.0.1:$$PORT/api/fab-ops/v1/evals/replays" | grep -q '"failed_assertions":0'; \
	curl -fsS "http://127.0.0.1:$$PORT/api/scanner/architecture-pack" >/dev/null; \
	echo "smoke ok: http://127.0.0.1:$$PORT"

package-check: install
	rm -rf .tmp-verify/wheels
	mkdir -p .tmp-verify/wheels
	$(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir .tmp-verify/wheels .
	$(PYTHON) scripts/validate_package_fixture.py .tmp-verify/wheels
	rm -rf build

validate: install
	$(PYTHON) scripts/validate_architecture_blueprint.py
	$(PYTHON) scripts/validate_repository_surface.py

verify: lint test smoke validate

verify-strict: lint typecheck coverage package-check smoke validate

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

docker-build:
	docker build -t $(IMAGE):$(TAG) .

docker-run:
	docker run --rm -p 8000:8000 \
		-e SEMICONDUCTOR_OPS_MODE=demo \
		-e PERSISTENCE_BACKEND=sqlite \
		-e LOG_FORMAT=json \
		$(IMAGE):$(TAG)

# ---------------------------------------------------------------------------
# Kubernetes deploy (requires kubectl context)
# ---------------------------------------------------------------------------

deploy:
	@kubectl get secret semiconductor-ops-secrets >/dev/null 2>&1 || { \
		echo "Missing Kubernetes Secret semiconductor-ops-secrets; create it per infra/k8s/README.md."; \
		exit 1; \
	}
	kubectl apply -f infra/k8s/configmap.yaml
	kubectl apply -f infra/k8s/pvc.yaml
	kubectl apply -f infra/k8s/deployment.yaml
	kubectl apply -f infra/k8s/service.yaml

pages-deploy:
	npx --yes wrangler@latest pages deploy site --project-name=fab-ops-yield-control-tower --branch=main

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage coverage.xml *.egg-info build dist .tmp-verify data/
