# syntax=docker/dockerfile:1

# ---------- build: instala dependências Python num venv isolado ----------
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# ---------- runtime ----------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    UPLOAD_DIR=/app/uploads \
    PORT=8000

# libpq5: asyncpg/psycopg | tesseract: OCR | libzbar0: QR code de cupom fiscal
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 tesseract-ocr tesseract-ocr-por libzbar0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 koin

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=koin:koin . .
RUN chmod +x docker/entrypoint.sh && mkdir -p /app/uploads && chown koin:koin /app/uploads

USER koin
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4)" || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
# 1 worker de propósito: o APScheduler roda dentro do processo da API.
# Com mais workers os jobs agendados rodariam duplicados.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
