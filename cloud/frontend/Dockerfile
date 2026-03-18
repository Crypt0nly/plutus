###############################################################################
# Plutus Cloud – Frontend Dockerfile
# Multi-stage build: deps → build → serve with nginx
#
# VITE_CLERK_PUBLISHABLE_KEY is a *publishable* key (safe to embed in the
# JS bundle — it is intentionally public). Docker lint flags ARG/ENV for any
# variable whose name contains "KEY", so we pass it via a build-time .env
# file written by the CI step instead of a named ARG to silence the warning.
###############################################################################

# ── Stage 1: install dependencies ───────────────────────────────────────────
FROM node:20-alpine AS deps

# Enable corepack so pnpm is available without a separate install step
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

# ── Stage 2: build the production bundle ────────────────────────────────────
FROM node:20-alpine AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Vite reads .env at build time and inlines VITE_* vars into the bundle.
# The CI workflow writes a .env file with the real values before building,
# so no ARG/ENV is needed here (avoids the Docker secrets lint warning).
# For local builds, copy .env.example to .env and fill in your values.
RUN pnpm run build

# ── Stage 3: serve with nginx ───────────────────────────────────────────────
FROM nginx:1.27-alpine

LABEL maintainer="Plutus Team" \
      description="Plutus Cloud Frontend (React + Vite)" \
      version="0.1.0"

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Custom nginx config for SPA routing
COPY <<'EOF' /etc/nginx/conf.d/plutus.conf
server {
    listen 3000;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript image/svg+xml;

    # Cache static assets aggressively
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback – serve index.html for all routes
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
EOF

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -qO- http://localhost:3000 || exit 1

CMD ["nginx", "-g", "daemon off;"]
