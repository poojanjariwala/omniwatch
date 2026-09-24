# OmniWatch API — non-root, minimal runtime.
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10

WORKDIR /srv/omniwatch

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

RUN adduser --system --group --home /srv/omniwatch ow && \
    mkdir -p /srv/omniwatch/data/uploads /srv/omniwatch/data/reports && \
    chown -R ow /srv/omniwatch

USER ow
EXPOSE 8000
# --proxy-headers: nginx is the only ingress (internal network), so the real
# client IP from X-Forwarded-For reaches the app — per-IP rate limits and audit
# logs would otherwise collapse onto the proxy address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
