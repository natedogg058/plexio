FROM --platform=$BUILDPLATFORM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json .
COPY frontend/package-lock.json .

RUN npm ci

COPY frontend .

RUN npm run build

FROM python:3.11.15-slim

WORKDIR /app

# Retain the image's historical port 80 contract while running the application
# as an unprivileged user with only the low-port bind capability.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libcap2-bin \
    && setcap 'cap_net_bind_service=+ep' "$(readlink -f "$(command -v python3)")" \
    && groupadd --gid 999 plexio \
    && useradd --uid 999 --gid 999 --no-create-home --shell /usr/sbin/nologin plexio \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock requirements.lock
COPY plexio plexio

RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY --from=build /app/dist frontend
ENV PLEXIO_FRONTEND_DIR=/app/frontend \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create writable state for the unprivileged runtime user. A named volume will
# inherit this ownership the first time it is mounted at /data.
RUN mkdir -p /data \
    && chown -R 999:999 /app /data

USER 999:999

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1/api/v1/health', timeout=3)"

CMD ["python", "-m", "uvicorn", "plexio.main:app", "--host", "0.0.0.0", "--port", "80", "--no-server-header", "--no-access-log"]
