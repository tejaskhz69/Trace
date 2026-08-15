# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pillow needs these; asyncpg ships wheels so no build toolchain required.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        libwebp7 \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user.
RUN useradd -m -u 10001 trace && chown -R trace:trace /app
USER trace

# Railway injects PORT at runtime. Do NOT hardcode 8000, and DO bind 0.0.0.0 --
# binding 127.0.0.1 makes the container unreachable from Railway's proxy and
# produces an endless "Application failed to respond".
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
