FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

LABEL org.opencontainers.image.title="AI Cost Analyzer - Backend"
LABEL org.opencontainers.image.description="Backend API for AI Cost Analyzer"
LABEL org.opencontainers.image.source="https://github.com/anomalyco/Ai-cost-analyzer"

RUN groupadd -r appuser \
    && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY app/ app/

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENV UVICORN_WORKERS=4

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS}"]
