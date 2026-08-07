# InvoiceLoop workbench → Cloud Run / 本地 Docker(零 Gemini/ADK 依赖)
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY invoiceloop ./invoiceloop
COPY scripts/cloud_entrypoint.sh /cloud_entrypoint.sh

RUN pip install --no-cache-dir -e ".[cloud]" \
    && chmod +x /cloud_entrypoint.sh \
    && python3 -m invoiceloop demo --out /data/demo-ws

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV INVOICELOOP_WORKSPACE=/data/demo-ws

EXPOSE 8080

# 不跑 doctor(会查研究语料);探针打工作台本身
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/healthz" || exit 1

ENTRYPOINT ["/cloud_entrypoint.sh"]
