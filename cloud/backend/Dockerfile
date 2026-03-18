###############################################################################
# Plutus Cloud – Backend Dockerfile
# Multi-stage build: deps → production image
###############################################################################

# ── Stage 1: dependency builder ─────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build-time system deps (for asyncpg, cryptography, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: production image ───────────────────────────────────────────────
FROM python:3.12-slim

# Metadata
LABEL maintainer="Plutus Team" \
      description="Plutus Cloud Backend (FastAPI)" \
      version="0.1.0"

# Runtime system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r plutus && useradd -r -g plutus -d /app -s /sbin/nologin plutus

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Own files by non-root user
RUN chown -R plutus:plutus /app

USER plutus

EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: production mode (no --reload)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
