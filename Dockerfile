# InvoiceLoop → Cloud Run / 本地 Docker
#
# 一个镜像,装 [gemini](google-genai + google-adk),入口是只读工作台。
# 两条分支各有过一个 Dockerfile,这是合并后的唯一一个。
FROM python:3.12-slim

# pdftotext / pdftoppm / pdfinfo;curl 供 HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY invoiceloop ./invoiceloop
COPY scripts/cloud_entrypoint.sh /cloud_entrypoint.sh

# demo workspace 在构建时烤进镜像 —— 运行期不取任何外部数据,
# 于是没有「拉取失败了怎么办」这个问题(见 docs/CLOUD_RUN.md)
RUN pip install --no-cache-dir -e ".[gemini]" \
    && chmod +x /cloud_entrypoint.sh \
    && python3 -m invoiceloop demo --out /data/demo-ws

ENV PYTHONUNBUFFERED=1
ENV INVOICELOOP_WORKSPACE=/data/demo-ws
# 不设 ENV PORT —— Cloud Run 注入的值必须赢;入口自己 ${PORT:-8080}
EXPOSE 8080

# 不跑 doctor(它会查研究语料);探针打工作台本身,且先于 Host 闸
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/healthz" || exit 1

ENTRYPOINT ["/cloud_entrypoint.sh"]
