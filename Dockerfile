# ---------- build stage: compile wheels ----------
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---------- runtime stage ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    # Cloud Run's writable area is in-memory; keep SQLite files under /tmp/data.
    RETAIL_DB_PATH=/tmp/data/retail.db \
    SESSION_DB_URL=sqlite+aiosqlite:////tmp/data/sessions.db

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* && rm -rf /wheels
COPY app ./app

USER appuser
EXPOSE 8080
# One worker per container: Cloud Run scales by containers, and the async app handles
# many concurrent requests in one process. Shell form so $PORT expands.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips="*" --timeout-keep-alive 75
