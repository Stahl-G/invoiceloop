# InvoiceLoop — Cloud Run & Container Runtime
FROM python:3.12-slim

# System dependencies: poppler-utils (pdftotext, pdftoppm, pdfinfo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install InvoiceLoop package with Gemini/ADK dependencies
COPY pyproject.toml README.md ./
COPY invoiceloop ./invoiceloop

RUN pip install --no-cache-dir -e ".[gemini]"

ENV PYTHONUNBUFFERED=1

# Cloud Run injects PORT; workbench reads it (default 8765).
# Do NOT hardcode ENV PORT — Cloud Run's value must win.
EXPOSE 8080

# Workspace path passed via environment; no demo-ws baked in.
CMD ["sh", "-c", "python3 -m invoiceloop workbench --workspace ${WORKSPACE:-/data/workspace}"]
