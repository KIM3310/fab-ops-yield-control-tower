.PHONY: install test lint typecheck docker-build docker-run deploy clean coverage

PYTHON ?= python3
IMAGE  ?= semiconductor-ops-platform
TAG    ?= latest

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

test:
	PERSISTENCE_BACKEND=jsonl $(PYTHON) -m pytest -q

coverage:
	PERSISTENCE_BACKEND=jsonl $(PYTHON) -m pytest --cov=app --cov-report=term-missing --cov-report=html -q

lint:
	$(PYTHON) -m ruff check app tests

typecheck:
	$(PYTHON) -m mypy app --ignore-missing-imports

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
