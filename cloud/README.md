# Plutus Cloud Platform

> Multi-tenant cloud platform for the Plutus AI agent — chat with your personal AI, manage memory and skills, sync state between local and cloud, and connect your desktop via the Bridge daemon.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Authentication Flow](#authentication-flow)
- [Sync Engine](#sync-engine)
- [Bridge Daemon](#bridge-daemon)
- [Deployment Guide](#deployment-guide)

---

## Project Overview

Plutus Cloud is the hosted backend and web frontend for the Plutus AI agent. It provides:

- **Web-based chat UI** — Interact with your Plutus agent from any browser.
- **Persistent agent state** — Memory, skills, scheduled tasks, and conversation history stored in PostgreSQL.
- **Multi-tenancy** — Each user gets fully isolated data via Clerk authentication and per-user row-level filtering.
- **Sync engine** — Bidirectional sync between the local desktop agent (SQLite) and the cloud (Postgres) using a last-write-wins strategy.
- **Bridge connectivity** — A WebSocket channel allows the cloud agent to dispatch tasks to the user's local machine (shell commands, file access, app launching) through the [Bridge daemon](../bridge/README.md).
- **Connector management** — Configure Telegram, GitHub, Gmail, Discord, and other integrations from the web dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Plutus Cloud                               │
│                                                                     │
│  ┌──────────────┐        HTTPS / REST        ┌──────────────────┐  │
│  │              │ ◄─────────────────────────► │                  │  │
│  │   Frontend   │                             │     Backend      │  │
│  │  (React +    │        Clerk JWT in         │   (FastAPI +     │  │
│  │   Vite +     │        Authorization        │    SQLAlchemy)   │  │
│  │   Clerk)     │        header               │                  │  │
│  │              │                             │  ┌────────────┐  │  │
│  │  :3000/5173  │                             │  │  Routers   │  │  │
│  └──────────────┘                             │  │ auth,chat, │  │  │
│                                               │  │ agents,    │  │  │
│                                               │  │ bridge,    │  │  │
│                                               │  │ sync,      │  │  │
│                                               │  │ health     │  │  │
│                                               │  └─────┬──────┘  │  │
│                                               │        │         │  │
│                                               │  ┌─────▼──────┐  │  │
│                                               │  │  Services  │  │  │
│                                               │  │ AgentSvc   │  │  │
│                                               │  │ UserSvc    │  │  │
│                                               │  │ SyncSvc    │  │  │
│                                               │  └─────┬──────┘  │  │
│                                               │        │         │  │
│                                               └────────┼─────────┘  │
│                                                        │            │
│                                          ┌─────────────▼──────┐    │
│                                          │    PostgreSQL 16    │    │
│                                          │  (users, memories,  │    │
│                                          │   skills, tasks,    │    │
│                                          │   conversations,    │    │
│                                          │   sync_log)         │    │
│                                          └────────────────────┘    │
│                                          ┌────────────────────┐    │
│                                          │     Redis 7        │    │
│                                          │  (cache, sessions) │    │
│                                          └────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘

                         ▲ WebSocket (wss://)
                         │ /api/bridge/ws/{token}
                         │
                ┌────────┴────────┐
                │  Bridge Daemon  │         ┌──────────────────┐
                │  (user's PC)    │ ◄──────►│  shared/ module  │
                │                 │  uses   │  (models, sync,  │
                │  Executes local │         │   memory, conns) │
                │  tasks on       │         └──────────────────┘
                │  behalf of the  │                  ▲
                │  cloud agent    │                  │ imported by
                └─────────────────┘                  │
                                            ┌───────┴──────────┐
                                            │  Backend + Bridge │
                                            └──────────────────┘
```

### Data Flow

```
User (Browser)                  Frontend              Backend                PostgreSQL
     │                             │                     │                       │
     │  1. Sign in via Clerk       │                     │                       │
     │ ──────────────────────────► │                     │                       │
     │                             │                     │                       │
     │  2. Send chat message       │                     │                       │
     │ ──────────────────────────► │  3. POST /api/chat  │                       │
     │                             │ ──────────────────► │  4. Load history      │
     │                             │                     │ ────────────────────► │
     │                             │                     │ ◄──────────────────── │
     │                             │                     │                       │
     │                             │                     │  5. Call LLM (Anthropic/OpenAI)
     │                             │                     │ ─────────► LLM API   │
     │                             │                     │ ◄───────── response   │
     │                             │                     │                       │
     │                             │                     │  6. Save messages     │
     │                             │                     │ ────────────────────► │
     │                             │  7. Return response │                       │
     │  8. Display response        │ ◄──────────────────│                       │
     │ ◄────────────────────────── │                     │                       │
```

---

## Directory Structure

```
cloud/
├── docker-compose.yml          # Full-stack: Postgres + Redis + Backend + Frontend
│
├── backend/                    # FastAPI application
│   ├── Dockerfile              # Python 3.12-slim container
│   ├── requirements.txt        # Python dependencies
│   ├── alembic.ini             # Alembic migration config
│   ├── alembic/                # Database migrations
│   │   ├── env.py              # Migration environment
│   │   ├── script.py.mako      # Migration template
│   │   └── versions/           # Migration files
│   ├── .env                    # Environment variables (do NOT commit real secrets)
│   └── app/
│       ├── __init__.py
│       ├── main.py             # FastAPI app: lifespan, CORS, router registration
│       ├── config.py           # Pydantic Settings (reads .env)
│       ├── database.py         # Async SQLAlchemy engine + session factory
│       ├── agent/
│       │   └── runtime.py      # CloudAgentRuntime — LLM orchestration per user
│       ├── api/                # Route handlers
│       │   ├── auth.py         # Clerk JWT verification, get_current_user dependency
│       │   ├── chat.py         # POST /api/chat, GET history, GET/DELETE conversations
│       │   ├── agents.py       # Agent status, memory CRUD, skills, scheduled tasks
│       │   ├── bridge.py       # Bridge WebSocket + task dispatch
│       │   ├── sync.py         # Push/pull sync endpoints
│       │   └── health.py       # GET /api/health
│       ├── models/             # SQLAlchemy ORM models
│       │   ├── base.py         # DeclarativeBase + TimestampMixin
│       │   ├── user.py         # User (Clerk ID, plan, settings, credentials)
│       │   ├── agent_state.py  # AgentState, Memory, Skill, ScheduledTask
│       │   ├── conversation.py # Conversation, Message
│       │   └── sync_log.py     # SyncLog (version-tracked change journal)
│       ├── services/           # Business logic
│       │   ├── agent_service.py # Memory, skills, tasks, conversation management
│       │   └── user_service.py  # User get-or-create, settings updates
│       └── sync/
│           └── sync_service.py # Sync engine: push/pull, conflict resolution
│
├── frontend/                   # React SPA
│   ├── Dockerfile              # Node 20-alpine container
│   ├── package.json            # Dependencies (Clerk, React Router, Zustand, Tailwind)
│   ├── vite.config.ts          # Vite dev server + API proxy
│   ├── tsconfig.json           # TypeScript configuration
│   ├── tailwind.config.js      # Tailwind CSS config
│   ├── postcss.config.js       # PostCSS (Tailwind + Autoprefixer)
│   ├── index.html              # HTML entry point
│   ├── .env.local              # VITE_CLERK_PUBLISHABLE_KEY
│   └── src/
│       ├── main.tsx            # ClerkProvider + BrowserRouter + ReactDOM
│       ├── App.tsx             # Auth-gated routing (Landing ↔ AppLayout)
│       ├── index.css           # Global styles + Tailwind directives
│       ├── lib/
│       │   └── api.ts          # Typed API client with Clerk token injection
│       ├── store/
│       │   └── agentStore.ts   # Zustand store (messages, agent state, UI state)
│       └── pages/
│           ├── Dashboard.tsx   # Agent status overview
│           ├── AgentChat.tsx   # Chat interface
│           ├── Memory.tsx      # Memory/facts browser
│           ├── Connectors.tsx  # Connector configuration
│           └── Settings.tsx    # User + agent settings
│
└── README.md                   # ← You are here
```

---

## Quick Start

The fastest way to run the full stack is with Docker Compose:

```bash
cd cloud

# Start everything: Postgres, Redis, Backend, Frontend
docker-compose up --build

# Services will be available at:
#   Frontend:  http://localhost:3000
#   Backend:   http://localhost:8000
#   API Docs:  http://localhost:8000/docs  (debug mode only)
#   Postgres:  localhost:5432
#   Redis:     localhost:6379
```

> **Note:** You must configure Clerk keys before the app is functional. See [Environment Variables](#environment-variables).

To stop:

```bash
docker-compose down            # Stop containers
docker-compose down -v         # Stop + delete database volume
```

---

## Development Setup

For active development, run services individually for hot-reload support.

### Prerequisites

| Tool              | Version  | Purpose                    |
|-------------------|----------|----------------------------|
| Docker            | 20+      | PostgreSQL & Redis         |
| Node.js           | 20+      | Frontend dev server        |
| Python            | 3.12+    | Backend dev server         |
| Clerk account     | —        | Authentication             |

### 1. Start Infrastructure

```bash
cd cloud
docker-compose up postgres redis -d
```

### 2. Configure Environment

**Backend** — Create `cloud/backend/.env`:

```env
DEBUG=true
SECRET_KEY=your-random-secret-key

# Clerk (https://dashboard.clerk.com → API Keys)
CLERK_PUBLISHABLE_KEY=pk_test_xxxxx
CLERK_SECRET_KEY=sk_test_xxxxx

# Database
DATABASE_URL=postgresql+asyncpg://plutus:plutus@localhost:5432/plutus

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM Providers (at least one required)
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
```

**Frontend** — Create `cloud/frontend/.env.local`:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_xxxxx
VITE_API_URL=http://localhost:8000
```

### 3. Start the Backend

```bash
cd cloud/backend

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Run database migrations (first time)
alembic upgrade head

# Start dev server with hot-reload
uvicorn app.main:app --reload --port 8000
```

The backend auto-creates tables on startup in debug mode. For production, always use Alembic migrations.

### 4. Start the Frontend

```bash
cd cloud/frontend

npm install
npm run dev
```

The Vite dev server starts at `http://localhost:5173` with HMR enabled.

### 5. Database Setup

The PostgreSQL schema is managed by SQLAlchemy models and Alembic migrations.

**Create a new migration** after modifying models:

```bash
cd cloud/backend
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

**Reset the database** (development only):

```bash
docker-compose down -v
docker-compose up postgres -d
# Backend will re-create tables on next startup (debug mode)
```

---

## Environment Variables

### Backend (`cloud/backend/.env`)

| Variable                  | Required | Default                                                 | Description                                    |
|---------------------------|----------|---------------------------------------------------------|------------------------------------------------|
| `DEBUG`                   | No       | `true`                                                  | Enable debug mode (exposes `/docs`, verbose SQL)|
| `SECRET_KEY`              | Yes      | `change-me-in-production`                               | Application secret for signing                 |
| `CLERK_PUBLISHABLE_KEY`   | Yes      | —                                                       | Clerk publishable key (`pk_test_...`)          |
| `CLERK_SECRET_KEY`        | Yes      | —                                                       | Clerk secret key (`sk_test_...`)               |
| `CLERK_JWKS_URL`          | No       | `https://api.clerk.com/v1/jwks`                         | Clerk JWKS endpoint for JWT verification       |
| `DATABASE_URL`            | Yes      | `postgresql+asyncpg://plutus:plutus@localhost:5432/plutus` | Async PostgreSQL connection string          |
| `REDIS_URL`               | No       | `redis://localhost:6379/0`                              | Redis connection string                        |
| `CORS_ORIGINS`            | No       | `["http://localhost:3000", "http://localhost:5173"]`    | Allowed CORS origins (JSON array)              |
| `DEFAULT_LLM_PROVIDER`    | No       | `anthropic`                                             | Default LLM provider (`anthropic` or `openai`) |
| `ANTHROPIC_API_KEY`       | Cond.    | —                                                       | Required if using Anthropic models             |
| `OPENAI_API_KEY`          | Cond.    | —                                                       | Required if using OpenAI models                |

### Frontend (`cloud/frontend/.env.local`)

| Variable                       | Required | Default | Description                              |
|--------------------------------|----------|---------|------------------------------------------|
| `VITE_CLERK_PUBLISHABLE_KEY`   | Yes      | —       | Clerk publishable key (same as backend)  |
| `VITE_API_URL`                 | No       | `""`    | Backend API base URL (empty = same origin)|

---

## API Endpoints

All endpoints (except health) require a valid Clerk JWT in the `Authorization: Bearer <token>` header.

### Health

| Method | Path              | Description              |
|--------|-------------------|--------------------------|
| `GET`  | `/api/health`     | Health check. Returns `{"status": "healthy"}` |

### Authentication

| Method | Path              | Description              |
|--------|-------------------|--------------------------|
| `GET`  | `/api/auth/me`    | Return current user info extracted from the JWT |

### Chat

| Method   | Path                            | Description                                |
|----------|----------------------------------|--------------------------------------------|
| `POST`   | `/api/chat/`                    | Send a message. Body: `{message, conversation_id?}`. Returns `{response, conversation_id}` |
| `GET`    | `/api/chat/history`             | List all conversations for the current user |
| `GET`    | `/api/chat/{conversation_id}`   | Get a conversation with all its messages    |
| `DELETE` | `/api/chat/{conversation_id}`   | Delete a conversation and its messages      |

### Agents

| Method   | Path                            | Description                                |
|----------|----------------------------------|--------------------------------------------|
| `GET`    | `/api/agents/status`            | Get agent status (`idle`, `busy`, `not_initialized`) |
| `POST`   | `/api/agents/restart`           | Reset agent state to `idle`                |
| `GET`    | `/api/agents/memory`            | List memory facts. Query: `?category=`     |
| `POST`   | `/api/agents/memory`            | Save a memory fact. Body: `{content, category?}` |
| `DELETE` | `/api/agents/memory/{fact_id}`  | Delete a memory fact                       |
| `GET`    | `/api/agents/skills`            | List user's custom skills + shared skills  |
| `GET`    | `/api/agents/scheduled-tasks`   | List scheduled tasks                       |
| `POST`   | `/api/agents/scheduled-tasks`   | Create a scheduled task. Body: `{name, schedule, prompt, description?}` |

### Bridge

| Method      | Path                           | Description                                |
|-------------|--------------------------------|--------------------------------------------|
| `GET`       | `/api/bridge/status`           | Check if user's bridge daemon is connected |
| `POST`      | `/api/bridge/send-task`        | Dispatch a task to the bridge. Body: `{task_type, payload}` |
| `WebSocket` | `/api/bridge/ws/{token}`       | Bridge daemon WebSocket connection         |

**Bridge task types:** `shell`, `open_app`, `read_file`, `write_file`, `list_files`, `ping`

### Sync

| Method | Path                            | Description                                |
|--------|----------------------------------|--------------------------------------------|
| `POST` | `/api/sync/push`                | Push local changes to cloud. Body: `{payloads: [{table, operation, record_id, data, client_version}]}` |
| `GET`  | `/api/sync/pull`                | Pull cloud changes. Query: `?since_version=0`. Returns `{changes, server_version}` |
| `GET`  | `/api/sync/status`              | Get current sync version for the user      |

---

## Authentication Flow

Plutus Cloud uses [Clerk](https://clerk.com) for authentication. The flow works as follows:

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  Browser  │     │   Clerk.com  │     │   Frontend   │     │  Backend │
└─────┬─────┘     └──────┬───────┘     └──────┬───────┘     └─────┬────┘
      │                  │                    │                    │
      │  1. Click "Sign In"                   │                    │
      │ ─────────────────────────────────────►│                    │
      │                  │                    │                    │
      │  2. Clerk modal opens                 │                    │
      │ ◄─────────────────────────────────────│                    │
      │                  │                    │                    │
      │  3. User authenticates with Clerk     │                    │
      │ ─────────────────►                    │                    │
      │                  │                    │                    │
      │  4. Clerk returns session + JWT       │                    │
      │ ◄─────────────────                    │                    │
      │                  │                    │                    │
      │  5. Frontend stores session           │                    │
      │ ─────────────────────────────────────►│                    │
      │                  │                    │                    │
      │  6. API call with Authorization: Bearer <JWT>              │
      │ ──────────────────────────────────────────────────────────►│
      │                  │                    │                    │
      │                  │                    │    7. Fetch JWKS   │
      │                  │ ◄──────────────────────────────────────│
      │                  │ ────────────────────────────────────── │
      │                  │    (cached after first fetch)          │
      │                  │                    │                    │
      │                  │                    │  8. Verify JWT     │
      │                  │                    │    signature       │
      │                  │                    │    (RS256 + kid)   │
      │                  │                    │                    │
      │  9. Return authenticated response     │                    │
      │ ◄──────────────────────────────────────────────────────────│
```

**Key implementation details:**

1. **Frontend:** `@clerk/clerk-react` wraps the app in `<ClerkProvider>`. The `<Show>` component gates authenticated vs. unauthenticated views. `useAuth().getToken()` retrieves the session JWT for API calls.

2. **Backend:** The `get_current_user` dependency in `app/api/auth.py`:
   - Extracts the Bearer token from the `Authorization` header.
   - Fetches Clerk's JWKS (cached in memory after first call).
   - Matches the token's `kid` header to a JWKS key.
   - Verifies the RS256 signature and decodes the payload.
   - Returns `{sub, user_id, email, session_id}`.

3. **Per-user isolation:** Every database query filters by `user_id = current_user["sub"]`, which is the Clerk user ID (`user_xxx`). There is no way for one user to access another user's data.

---

## Sync Engine

The sync engine keeps the local desktop agent (SQLite) and the cloud (PostgreSQL) in sync. It is designed for simplicity and reliability.

### Strategy: Last-Write-Wins

```
Local Agent (SQLite)                    Cloud (PostgreSQL)
       │                                       │
       │  1. User saves a memory locally       │
       │                                       │
       │  2. Bridge pushes change ──────────► │
       │     POST /api/sync/push               │
       │     {table: "memory",                 │
       │      operation: "update",             │
       │      record_id: "42",                 │
       │      data: {...},                     │
       │      client_version: 5}               │
       │                                       │  3. Cloud compares timestamps
       │                                       │     - If local.timestamp >= cloud.timestamp → accept
       │                                       │     - If local.timestamp <  cloud.timestamp → skip
       │                                       │
       │                                       │  4. Append to sync_log with
       │                                       │     monotonic version number
       │                                       │
       │  5. Pull changes ◄──────────────────  │
       │     GET /api/sync/pull?since_version=4│
       │                                       │
       │  6. Apply changes to local SQLite     │
       │     INSERT ... ON CONFLICT DO UPDATE  │
```

### Design Principles

- **Cloud is source of truth.** In any unresolvable conflict, the cloud version wins.
- **Monotonic version counter.** Each user has an independent version counter in `sync_log`. The client tracks the last version it has seen and pulls only newer changes.
- **Entity-level sync.** Synced entities: `memory`, `skill`, `scheduled_task`. Each change is logged with `entity_type`, `entity_id`, `action` (create/update/delete), and `data`.
- **Idempotent operations.** Pushing the same change twice is safe — the timestamp comparison prevents stale overwrites.

### Synced Entities

| Entity           | Table             | Sync Fields                                    |
|------------------|-------------------|------------------------------------------------|
| Memory facts     | `memories`        | category, content, metadata                    |
| Skills           | `skills`          | name, description, skill_type, definition      |
| Scheduled tasks  | `scheduled_tasks` | name, schedule, prompt, description, is_active |

### Conflict Resolution

Conflicts are resolved using the `SyncConflict` dataclass in `shared/models/sync.py`:

```python
# If local timestamp >= cloud timestamp → local wins
# If cloud timestamp >  local timestamp → cloud wins
conflict.resolve_last_write_wins()
```

---

## Bridge Daemon

The Bridge daemon is a lightweight Python process that runs on the user's local machine and connects to the cloud via WebSocket. It enables the cloud agent to execute tasks on the user's PC.

See the full [Bridge README](../bridge/README.md) for installation and usage.

### How It Works

1. The bridge authenticates with a Clerk JWT and opens a persistent WebSocket to `/api/bridge/ws/{token}`.
2. The cloud backend registers the connection in `active_bridges[user_id]`.
3. When the cloud agent needs local execution, it calls `POST /api/bridge/send-task` which forwards the task over the WebSocket.
4. The bridge executes the task locally and sends back a `task_result` message.
5. A heartbeat is sent every 30 seconds to keep the connection alive.
6. On disconnect, the bridge auto-reconnects with exponential backoff (5s → 10s → 20s → ... → 5min max).

### Supported Task Types

| Task Type    | Payload                        | Description                     |
|-------------|--------------------------------|---------------------------------|
| `shell`     | `{command, timeout?}`          | Execute a shell command         |
| `open_app`  | `{app_name}`                   | Open an application             |
| `read_file` | `{path}`                       | Read a local file (up to 50KB) |
| `write_file`| `{path, content}`              | Write content to a local file   |
| `list_files`| `{path?, pattern?}`            | List files matching a glob      |
| `ping`      | `{}`                           | Health check + system info      |

---

## Deployment Guide

### Production Checklist

- [ ] **Set `DEBUG=false`** — Disables `/docs` and `/redoc`, reduces SQL logging.
- [ ] **Generate a strong `SECRET_KEY`** — Use `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- [ ] **Use production Clerk keys** — Switch from `pk_test_` / `sk_test_` to `pk_live_` / `sk_live_`.
- [ ] **Use a managed PostgreSQL** — AWS RDS, Supabase, Neon, or similar.
- [ ] **Use a managed Redis** — AWS ElastiCache, Upstash, or similar.
- [ ] **Set `CORS_ORIGINS`** — Restrict to your actual frontend domain(s).
- [ ] **Enable HTTPS** — Use a reverse proxy (Nginx, Caddy, or cloud load balancer) with TLS.
- [ ] **Run Alembic migrations** — `alembic upgrade head` before starting the backend.
- [ ] **Build the frontend** — `npm run build` produces static files in `dist/`.
- [ ] **Serve frontend via CDN** — Deploy `dist/` to Vercel, Netlify, Cloudflare Pages, or serve via Nginx.

### Docker Production Build

```bash
# Backend
cd cloud/backend
docker build -t plutus-backend .

# Frontend (build static assets)
cd cloud/frontend
npm run build
# Deploy dist/ to your static hosting provider
```

### Recommended Infrastructure

```
                    ┌─────────────┐
                    │  CDN / Edge │  ← Frontend (static files)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Reverse   │  ← TLS termination
                    │   Proxy     │     (Nginx / Caddy / ALB)
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │   Backend (FastAPI)     │  ← Gunicorn + Uvicorn workers
              │   2+ replicas          │     (or single Uvicorn for small scale)
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │   PostgreSQL 16         │  ← Managed database with backups
              │   (RDS / Supabase)      │
              └─────────────────────────┘
              ┌─────────────────────────┐
              │   Redis 7               │  ← Managed cache
              │   (ElastiCache / Upstash)│
              └─────────────────────────┘
```

### Running with Gunicorn (Production)

```bash
pip install gunicorn

gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile -
```

### Environment Variable Injection

In production, inject environment variables via your platform's secret manager (AWS Secrets Manager, Kubernetes Secrets, Fly.io secrets, etc.) rather than `.env` files:

```bash
# Example: Fly.io
fly secrets set CLERK_SECRET_KEY=sk_live_xxxxx DATABASE_URL=postgresql+asyncpg://...

# Example: Docker
docker run -e CLERK_SECRET_KEY=sk_live_xxxxx -e DATABASE_URL=... plutus-backend
```
