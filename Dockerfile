# InvoiceLoop - Cloud Run & GKE Agent Runtime Container
FROM python:3.12-slim

# System dependencies: poppler-utils (pdftotext, pdftoppm, pdfinfo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install InvoiceLoop package & runtime dependencies
COPY pyproject.toml .
COPY invoiceloop ./invoiceloop
COPY README.md .

RUN pip install --no-cache-dir -e .

# Environment Defaults
ENV PYTHONUNBUFFERED=1
ENV PORT=8765

EXPOSE 8765

# Self-check health and default startup command
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -m invoiceloop doctor || exit 1

CMD ["python3", "-m", "invoiceloop", "workbench", "--workspace", "demo-ws"]
