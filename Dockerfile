# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps. libjpeg/libwebp for Pillow, libpq for asyncpg/psycopg, ca-certs for TLS.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libjpeg-dev \
        zlib1g-dev \
        libwebp-dev \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager).
RUN pip install --no-cache-dir uv

WORKDIR /app

# Cache deps layer
COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

# Now the source
COPY . .

# Non-root user
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Default entrypoint runs the news bot (userbot + publisher in one process).
CMD ["python", "-m", "bots.news"]
