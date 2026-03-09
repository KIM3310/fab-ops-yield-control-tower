FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md requirements.txt requirements-dev.txt /app/
COPY app /app/app

RUN pip install --no-cache-dir -r /app/requirements.txt && pip install --no-cache-dir -e /app

ENV PYTHONPATH=/app
ENV FAB_OPS_RUNTIME_STORE_PATH=/app/.runtime/fab-ops-events.jsonl

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
