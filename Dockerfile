# ── Stage 1: Build the React frontend ────────────────────────
FROM node:20-slim AS ui-builder

WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# ── Stage 2: Python runtime ─────────────────────────────────
FROM python:3.12-slim

# System deps for optional features (playwright browsers, GUI libs skipped
# in server/container context — only headless CLI + API usage).
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY pyproject.toml plutus/__init__.py ./plutus/
RUN pip install --no-cache-dir -e "." \
    && rm -rf /root/.cache/pip

# Copy the rest of the source
COPY plutus/ ./plutus/

# Copy the built frontend from stage 1
COPY --from=ui-builder /app/ui/dist ./ui/dist

# Plutus stores config/memory in ~/.plutus — mount a volume here for persistence
VOLUME /root/.plutus

# Default gateway port
EXPOSE 7777

# Run Plutus (serves the built UI + API on port 7777)
CMD ["python", "-m", "plutus", "start", "--host", "0.0.0.0"]
