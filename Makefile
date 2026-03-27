.PHONY: install test lint typecheck smoke docker-build docker-run deploy clean coverage verify verify-strict

PYTHON_BIN ?= python3
VENV ?= .venv
PYTHON := $(VENV)/bin/python
VENV_STAMP := $(VENV)/.installed-dev
IMAGE  ?= semiconductor-ops-platform
TAG    ?= latest

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

install: $(VENV_STAMP)

$(VENV_STAMP): pyproject.toml requirements.txt
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

test: install
	PERSISTENCE_BACKEND=jsonl $(PYTHON) -m pytest -q

coverage: install
	PERSISTENCE_BACKEND=jsonl $(PYTHON) -m pytest --cov=app --cov-report=term-missing --cov-report=html -q

lint: install
	$(PYTHON) -m ruff check app tests

typecheck: install
	$(PYTHON) -m mypy app --ignore-missing-imports

smoke: install
	@set -eu; \
	PORT=8099; \
	LOG=/tmp/fab-ops-platform-smoke.log; \
	$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port $$PORT >$$LOG 2>&1 & \
	pid=$$!; \
	trap 'kill $$pid >/dev/null 2>&1 || true' EXIT INT TERM; \
	for _ in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS "http://127.0.0.1:$$PORT/health" >/dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done; \
	curl -fsS "http://127.0.0.1:$$PORT/health" >/dev/null; \
	curl -fsS "http://127.0.0.1:$$PORT/api/resource-pack" >/dev/null; \
	curl -fsS "http://127.0.0.1:$$PORT/api/fab-ops/review-pack" >/dev/null; \
	curl -fsS "http://127.0.0.1:$$PORT/api/scanner/review-pack" >/dev/null; \
	echo "smoke ok: http://127.0.0.1:$$PORT"

verify: lint test smoke

verify-strict: lint typecheck test smoke

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

docker-build:
	docker build -t $(IMAGE):$(TAG) .

docker-run:
	docker run --rm -p 8000:8000 \
		-e PERSISTENCE_BACKEND=sqlite \
		-e LOG_FORMAT=json \
		$(IMAGE):$(TAG)

# ---------------------------------------------------------------------------
# Kubernetes deploy (requires kubectl context)
# ---------------------------------------------------------------------------

deploy:
	kubectl apply -f infra/k8s/configmap.yaml
	kubectl apply -f infra/k8s/deployment.yaml
	kubectl apply -f infra/k8s/service.yaml
	kubectl apply -f infra/k8s/hpa.yaml

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage coverage.xml *.egg-info data/
