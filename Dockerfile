FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend

COPY requirements.txt pyproject.toml .env.example ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY backend ./backend
# CI helper scripts (pip-audit severity gate) are exercised by backend/tests.
COPY scripts ./scripts

RUN chown -R appuser:appuser /app

USER appuser

# Bagian A liveness (API §3.1). Compose api overrides CMD with uvicorn.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# Default target is the test suite. The api service in docker-compose.yml
# overrides this with uvicorn.
CMD ["pytest"]
