FROM python:3.11.15-slim

WORKDIR /app

COPY requirements.lock requirements.lock
COPY plexio plexio

RUN pip install --no-cache-dir --require-hashes -r requirements.lock
