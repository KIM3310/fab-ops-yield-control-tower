FROM python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7

WORKDIR /app

COPY pyproject.toml README.md requirements.txt requirements-dev.txt /app/
COPY app /app/app

RUN python -m pip install --no-cache-dir --upgrade "pip>=26.1.2" "setuptools>=83.0.0" && \
    python -m pip install --no-cache-dir -r /app/requirements.txt && \
    python -m pip install --no-cache-dir -e /app && \
    python -m pip check

ENV PYTHONPATH=/app
ENV SEMICONDUCTOR_OPS_MODE=locked
ENV FAB_OPS_RUNTIME_STORE_PATH=/app/.runtime/fab-ops-events.jsonl
ENV SCANNER_RUNTIME_STORE_PATH=/app/.runtime/scanner-response-events.jsonl

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
