###############################################################################
# Plutus Cloud – Backend Dockerfile
# Multi-stage build: deps → production image
# Includes Node.js for the WhatsApp bridge (whatsapp-web.js)
###############################################################################

# ── Stage 1: Python dependency builder ──────────────────────────────────────
FROM python:3.12-slim AS python-builder

WORKDIR /build

# Install build-time system deps (for asyncpg, cryptography, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Node.js dependency builder ─────────────────────────────────────
FROM node:20-slim AS node-builder

WORKDIR /wa-bridge

# Install whatsapp-web.js and its peer dependencies
# puppeteer is bundled with whatsapp-web.js; we skip the Chromium download
# because the bridge uses the system Chromium installed in the final image.
RUN npm install --save whatsapp-web.js qrcode-terminal && \
    npm cache clean --force

# ── Stage 3: production image ────────────────────────────────────────────────
FROM python:3.12-slim

# Metadata
LABEL maintainer="Plutus Team" \
      description="Plutus Cloud Backend (FastAPI)" \
      version="0.1.0"

# Install Node.js (LTS) + Chromium (required by whatsapp-web.js/puppeteer)
# and other runtime system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Python runtime
        libpq5 curl \
        # Node.js
        nodejs npm \
        # Chromium for puppeteer/whatsapp-web.js
        chromium \
        # Fonts and libs needed by Chromium
        fonts-liberation libatk-bridge2.0-0 libatk1.0-0 libcups2 \
        libdbus-1-3 libgdk-pixbuf-xlib-2.0-0 libnspr4 libnss3 libx11-xcb1 \
        libxcomposite1 libxdamage1 libxrandr2 libxss1 libxtst6 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r plutus && useradd -r -g plutus -d /app -s /sbin/nologin plutus

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=python-builder /install /usr/local

# Copy the whatsapp-web.js node_modules from the node builder
COPY --from=node-builder /wa-bridge/node_modules /app/wa_bridge/node_modules

# Copy application code
COPY . .

# Copy the whatsapp_bridge.js from the plutus package (if bundled alongside)
# If not present, the bridge will be resolved at runtime from the installed package.
RUN if [ -f /app/../plutus/connectors/whatsapp_bridge.js ]; then \
        cp /app/../plutus/connectors/whatsapp_bridge.js /app/wa_bridge/whatsapp_bridge.js; \
    fi || true

# Set Puppeteer to use system Chromium instead of downloading its own
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    # Tell the WhatsApp bridge where to find node_modules
    WA_NODE_MODULES=/app/wa_bridge/node_modules

# Create session storage directory (writable by plutus user)
RUN mkdir -p /app/.plutus_whatsapp_sessions && \
    chown -R plutus:plutus /app

USER plutus

EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: production mode (no --reload)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
