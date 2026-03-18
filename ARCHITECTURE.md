# Plutus — Monorepo Architecture

> Comprehensive architecture reference for the Plutus AI agent platform: a desktop agent, cloud backend, local-to-cloud bridge, and shared library — all in one repository.

---

## Table of Contents

- [Monorepo Layout](#monorepo-layout)
- [Module Overview](#module-overview)
- [Technology Stack](#technology-stack)
- [Data Flow](#data-flow)
- [Security Model](#security-model)
- [Sync Strategy](#sync-strategy)
- [Subprocess Architecture](#subprocess-architecture)
- [Gateway & WebSocket](#gateway--websocket)

---

## Monorepo Layout

```
plutus/
│
├── plutus/                     # Desktop Agent (core application)
│   ├── __init__.py             # Package metadata, version
│   ├── __main__.py             # Entry point (python -m plutus)
│   ├── cli.py                  # Interactive REPL + CLI commands
│   ├── config.py               # Configuration management
│   ├── core/                   # Agent runtime
│   │   ├── agent.py            # Main agent loop (tool execution, LLM orchestration)
│   │   ├── conversation.py     # Conversation/context management
│   │   ├── heartbeat.py        # Heartbeat system
│   │   ├── llm.py              # LLM client (LiteLLM — multi-provider)
│   │   ├── memory.py           # SQLite memory store (local)
│   │   ├── planner.py          # Plan management
│   │   ├── scheduler.py        # Cron-based task scheduler
│   │   ├── session_registry.py # Multi-session management
│   │   ├── subprocess_manager.py # Subprocess orchestrator
│   │   ├── summarizer.py       # Context summarization
│   │   ├── model_router.py     # Intelligent model selection
│   │   ├── worker_pool.py      # Parallel worker pool
│   │   ├── keep_alive.py       # Keep-alive system
│   │   ├── computer_use_agent.py # Computer-use agent
│   │   └── openai_computer_use.py # OpenAI computer-use integration
│   ├── gateway/                # Web API + WebSocket server
│   │   ├── server.py           # HTTP server (FastAPI)
│   │   ├── routes.py           # REST API routes
│   │   └── ws.py               # WebSocket handlers
│   ├── guardrails/             # Permission & safety system
│   │   ├── engine.py           # Guardrails evaluation engine
│   │   ├── policies.py         # Security policies
│   │   ├── tiers.py            # Permission tiers (restricted → full)
│   │   └── audit.py            # Audit logging
│   ├── tools/                  # Built-in tool implementations
│   │   ├── base.py             # Tool base class
│   │   ├── registry.py         # Tool registry (hot-reload capable)
│   │   ├── filesystem.py       # File operations
│   │   ├── shell.py            # Shell command execution
│   │   ├── process.py          # Process management
│   │   ├── browser.py          # Browser automation
│   │   ├── desktop.py          # Desktop GUI control
│   │   ├── clipboard.py        # Clipboard access
│   │   ├── app_manager.py      # Application launcher
│   │   ├── system_info.py      # System information
│   │   ├── code_analysis.py    # AST-based code analysis
│   │   ├── code_editor.py      # Intelligent code editing
│   │   ├── tool_creator.py     # Dynamic tool creation at runtime
│   │   └── subprocess_tool.py  # Subprocess spawning tool
│   ├── pc/                     # PC control layer
│   │   ├── browser_control.py  # Browser automation engine
│   │   ├── browser_detect.py   # Browser detection
│   │   ├── computer_use.py     # Desktop computer-use
│   │   └── context.py          # Execution context
│   ├── connectors/             # External service integrations
│   │   ├── base.py             # Connector base class
│   │   ├── telegram.py         # Telegram bot
│   │   ├── discord.py          # Discord bot
│   │   ├── github.py           # GitHub API
│   │   ├── google.py           # Google services (Gmail, Calendar, Drive)
│   │   ├── email.py            # SMTP email
│   │   ├── whatsapp.py         # WhatsApp
│   │   ├── custom_api.py       # Custom API connector
│   │   └── web_hosting.py      # Web deployment (Vercel/Netlify)
│   └── skills/                 # YAML skill definitions
│
├── cloud/                      # Cloud Platform (backend + frontend)
│   ├── docker-compose.yml      # Full-stack Docker orchestration
│   ├── backend/                # FastAPI + PostgreSQL + Redis
│   │   ├── app/
│   │   │   ├── main.py         # FastAPI application
│   │   │   ├── config.py       # Pydantic Settings
│   │   │   ├── database.py     # Async SQLAlchemy
│   │   │   ├── agent/          # Cloud agent runtime (LLM calls)
│   │   │   ├── api/            # REST + WebSocket routes
│   │   │   ├── models/         # ORM models
│   │   │   ├── services/       # Business logic
│   │   │   └── sync/           # Sync engine
│   │   ├── alembic/            # Database migrations
│   │   └── requirements.txt
│   ├── frontend/               # React + Vite + Clerk + Tailwind
│   │   ├── src/
│   │   │   ├── App.tsx         # Auth-gated routing
│   │   │   ├── pages/          # Dashboard, Chat, Memory, Connectors, Settings
│   │   │   ├── store/          # Zustand state management
│   │   │   └── lib/            # API client
│   │   └── package.json
│   └── README.md
│
├── bridge/                     # Local Bridge Daemon
│   ├── plutus_bridge.py        # WebSocket client + local task executor
│   ├── sync_client.py          # Local ↔ Cloud sync client
│   ├── requirements.txt        # websockets>=12.0
│   └── README.md
│
├── shared/                     # Shared Library (used by cloud + bridge)
│   ├── __init__.py             # Public API exports
│   ├── pyproject.toml          # Package metadata
│   ├── models/
│   │   ├── message.py          # Message, Conversation dataclasses
│   │   └── sync.py             # SyncPayload, SyncConflict dataclasses
│   ├── memory/
│   │   ├── __init__.py         # BaseMemoryStore (abstract)
│   │   ├── local_store.py      # SQLite implementation
│   │   └── cloud_store.py      # PostgreSQL implementation
│   ├── connectors/
│   │   └── __init__.py         # ConnectorConfig, BaseConnector, ConnectorRegistry
│   └── skills/                 # (reserved for shared skill definitions)
│
├── .github/workflows/          # CI/CD
│   ├── cloud-ci.yml            # Cloud platform CI
│   └── publish.yml             # Package publishing
├── ARCHITECTURE.md             # ← You are here
├── CLAUDE.md                   # Agent instructions
├── Dockerfile                  # Desktop agent container
├── install.sh                  # Linux/macOS installer
├── install.ps1                 # Windows installer
└── LICENSE
```

---

## Module Overview

### `plutus/` — Desktop Agent

The core Plutus AI agent. Runs locally on the user's machine with full access to the operating system — file system, shell, browser, desktop GUI, clipboard, and applications. Powered by LLMs (Claude, GPT-4, etc.) via LiteLLM with a tool-use architecture.

**Key capabilities:**
- Interactive REPL and web gateway (REST + WebSocket)
- 15+ built-in tools (filesystem, shell, browser, desktop, code analysis, etc.)
- Dynamic tool creation at runtime
- Subprocess-based parallel execution
- Persistent memory (SQLite)
- Cron-based task scheduler
- Permission tiers and audit logging
- Multi-provider LLM support with intelligent model routing

### `cloud/` — Cloud Platform

Multi-tenant hosted platform. Users sign in via Clerk, chat with their agent through a web UI, and manage memory/skills/tasks. The backend stores all state in PostgreSQL and can call LLM APIs (Anthropic, OpenAI) directly.

**Key capabilities:**
- Web-based chat with conversation history
- Memory, skills, and scheduled task management
- Bridge WebSocket for remote desktop control
- Bidirectional sync with local agent
- Per-user data isolation

### `bridge/` — Local Bridge Daemon

A lightweight background process on the user's PC that maintains a persistent WebSocket connection to the cloud backend. Enables the cloud agent to execute local tasks (shell commands, file access, app launching) on the user's machine.

**Key capabilities:**
- Authenticated WebSocket connection (Clerk JWT)
- Local task execution (shell, file I/O, app launching)
- Auto-reconnect with exponential backoff
- Heartbeat-based connection monitoring
- State sync between local SQLite and cloud PostgreSQL

### `shared/` — Shared Library

Common code imported by both the cloud backend and the bridge daemon. Provides canonical data models, abstract interfaces, and sync logic that must stay consistent across local and cloud environments.

**Exports:**
- `Message`, `Conversation` — Chat data models
- `SyncPayload`, `SyncConflict` — Sync protocol types
- `BaseMemoryStore` — Abstract memory interface (SQLite and Postgres implementations)
- `ConnectorConfig`, `BaseConnector`, `ConnectorRegistry` — Connector abstractions

---

## Technology Stack

| Layer             | Technology                                   | Purpose                                    |
|-------------------|----------------------------------------------|--------------------------------------------|
| **Desktop Agent** | Python 3.12, LiteLLM, SQLite, FastAPI        | Local AI agent with tool-use               |
| **Cloud Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0, asyncpg | Async REST API + WebSocket server         |
| **Cloud Frontend**| React 18, Vite 5, TypeScript, Tailwind CSS   | Single-page web application                |
| **Auth**          | Clerk (clerk-react + PyJWT JWKS verification)| Authentication & user management           |
| **State**         | Zustand                                      | Frontend state management                  |
| **Database**      | PostgreSQL 16 (cloud), SQLite (local)        | Persistent storage                         |
| **Cache**         | Redis 7                                      | Session cache, rate limiting               |
| **Migrations**    | Alembic                                      | Database schema versioning                 |
| **Containers**    | Docker, Docker Compose                       | Development & deployment orchestration     |
| **LLM Providers** | Anthropic (Claude), OpenAI (GPT-4)           | AI model inference                         |
| **Sync**          | Custom (last-write-wins, version counters)   | Local ↔ Cloud state synchronization       |
| **Bridge**        | websockets (Python)                          | Persistent local ↔ cloud connection       |

---

## Data Flow

### Local Agent (Desktop)

```
User Input (CLI / Web Gateway)
       │
       ▼
┌─────────────────┐
│   Agent Loop    │ ◄──── Memory (SQLite)
│   (agent.py)    │ ◄──── Conversation History
│                 │ ◄──── Tool Registry
└────────┬────────┘
         │
         ▼
┌─────────────────┐       ┌─────────────────┐
│   LLM Client    │ ─────►│ Anthropic / OpenAI│
│   (llm.py)      │ ◄─────│ API              │
└────────┬────────┘       └─────────────────┘
         │
         ▼ (tool calls)
┌─────────────────┐
│  Tool Execution │
│  ├── filesystem │
│  ├── shell      │
│  ├── browser    │
│  ├── desktop    │
│  ├── code_editor│
│  └── ...        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Subprocess     │ ─── FileEditWorker
│  Manager        │ ─── CodeAnalysisWorker
│                 │ ─── ShellWorker
│                 │ ─── CustomWorker
└─────────────────┘
```

### Cloud Agent (Web)

```
Browser (React)
       │
       ▼ POST /api/chat
┌─────────────────┐
│  FastAPI Router  │
│  (chat.py)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐       ┌─────────────────┐
│ CloudAgentRuntime│ ─────►│ Anthropic / OpenAI│
│ (runtime.py)     │ ◄─────│ API              │
│                  │       └─────────────────┘
│ Builds system    │
│ prompt with:     │
│ - User memory    │◄────── PostgreSQL
│ - Available tools│
│ - Context        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PostgreSQL     │
│  ├── messages   │
│  ├── memories   │
│  ├── skills     │
│  └── sync_log   │
└─────────────────┘
```

### Sync Flow (Local ↔ Cloud)

```
┌──────────────────┐                           ┌──────────────────┐
│  Local Agent     │                           │  Cloud Backend   │
│  (SQLite)        │                           │  (PostgreSQL)    │
│                  │                           │                  │
│  Memory changed  │                           │                  │
│  locally         │                           │                  │
│        │         │                           │                  │
│        ▼         │    POST /api/sync/push    │                  │
│  sync_client.py  │ ────────────────────────► │  SyncService     │
│  push_local()    │    {payloads: [...]}      │  apply_changes() │
│                  │                           │        │         │
│                  │                           │        ▼         │
│                  │                           │  Compare timestamps│
│                  │                           │  Append sync_log │
│                  │                           │  Increment version│
│                  │                           │                  │
│                  │    GET /api/sync/pull      │                  │
│  sync_client.py  │ ────────────────────────► │  SyncService     │
│  pull_cloud()    │    ?since_version=N       │  get_changes()   │
│                  │                           │        │         │
│                  │    {changes, version}      │        │         │
│  Apply to SQLite │ ◄──────────────────────── │        │         │
│  ON CONFLICT     │                           │                  │
│  DO UPDATE       │                           │                  │
└──────────────────┘                           └──────────────────┘
```

### Bridge Flow (Cloud → Local PC)

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Web UI  │    │   Backend    │    │  WebSocket   │    │   Bridge     │
│          │    │              │    │  Connection  │    │   Daemon     │
└────┬─────┘    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
     │                 │                   │                   │
     │  "Run ls -la"   │                   │                   │
     │ ───────────────►│                   │                   │
     │                 │                   │                   │
     │                 │  send_task()      │                   │
     │                 │ ─────────────────►│  {type: "task",   │
     │                 │                   │   task_type:"shell"│
     │                 │                   │   payload:{cmd}}  │
     │                 │                   │ ─────────────────►│
     │                 │                   │                   │
     │                 │                   │                   │ Execute locally
     │                 │                   │                   │ subprocess.run()
     │                 │                   │                   │
     │                 │                   │  {type:           │
     │                 │                   │   "task_result",  │
     │                 │                   │   result: {...}}  │
     │                 │                   │ ◄─────────────────│
     │                 │                   │                   │
     │  Result         │ ◄─────────────────│                   │
     │ ◄───────────────│                   │                   │
```

---

## Security Model

### Authentication: Clerk

All authentication is handled by [Clerk](https://clerk.com), a third-party identity provider.

| Component     | Mechanism                                                |
|---------------|----------------------------------------------------------|
| **Frontend**  | `@clerk/clerk-react` — session management, sign-in/up UI |
| **Backend**   | JWT verification via Clerk JWKS (RS256 signatures)       |
| **Bridge**    | JWT token passed in WebSocket URL path                   |

### Per-User Isolation

Every database table that stores user data includes a `user_id` column (the Clerk user ID, e.g., `user_2abc123`). All queries filter by this column:

```python
# Every service method enforces user isolation
select(Memory).where(Memory.user_id == user_id)
select(Conversation).where(Conversation.user_id == user_id)
```

There is **no cross-user data access** — the `get_current_user` dependency extracts the user ID from the verified JWT, and it is passed through every service call.

### Data Model

```
users
├── id (Clerk user ID — primary key)
├── email
├── plan (free / pro / enterprise)
├── settings (JSON — agent preferences)
└── connector_credentials (JSON — encrypted)

agent_states         (1:1 with users)
memories             (N:1 with users)
skills               (N:1 with users)
scheduled_tasks      (N:1 with users)
conversations        (N:1 with users)
├── messages         (N:1 with conversations)
sync_log             (N:1 with users)
```

### Bridge Security

- The bridge daemon authenticates by passing a Clerk JWT in the WebSocket URL.
- The backend verifies the JWT before accepting the connection.
- If verification fails, the WebSocket is closed with code `4001`.
- Each user can have at most one active bridge connection (keyed by `user_id`).
- Task dispatch (`POST /api/bridge/send-task`) requires a valid JWT and only sends to the authenticated user's bridge.

### Desktop Agent Guardrails

The local desktop agent has a multi-tier permission system:

| Tier          | Capabilities                                           |
|---------------|--------------------------------------------------------|
| `restricted`  | Read-only file access, safe shell commands              |
| `standard`    | File read/write, most shell commands, browser control   |
| `elevated`    | System modifications, process management                |
| `full`        | Unrestricted access (requires explicit user consent)    |

All tool executions are logged in the audit system (`guardrails/audit.py`).

---

## Sync Strategy

### Overview

Plutus uses a **custom sync engine** to keep local (SQLite) and cloud (PostgreSQL) state consistent. The design prioritizes simplicity and correctness over real-time performance.

### Core Principles

1. **Cloud is source of truth.** If both local and cloud have been modified and the cloud version is newer, the cloud version wins.

2. **Last-write-wins (LWW).** Conflict resolution compares `updated_at` timestamps. The most recent write is accepted.

3. **Monotonic version counter.** Each user has an independent, auto-incrementing version number in the `sync_log` table. Clients track `since_version` to pull only new changes.

4. **Entity-level granularity.** Sync operates on whole entities (a memory fact, a skill definition, a scheduled task) — not on individual fields.

5. **Append-only change log.** Every accepted change is appended to `sync_log` with the new version number. This log is the canonical record of all changes and enables any client to catch up from any point.

### Sync Protocol

**Push (local → cloud):**
```
POST /api/sync/push
{
  "payloads": [
    {
      "table": "memory",
      "operation": "update",
      "record_id": "42",
      "data": {"category": "user_preference", "content": "Prefers dark mode"},
      "client_version": 5
    }
  ]
}
→ {"accepted": 1, "server_version": 6}
```

**Pull (cloud → local):**
```
GET /api/sync/pull?since_version=4
→ {
    "changes": [
      {"version": 5, "entity_type": "memory", "entity_id": "42", "action": "update", "data": {...}},
      {"version": 6, "entity_type": "skill", "entity_id": "7", "action": "create", "data": {...}}
    ],
    "server_version": 6
  }
```

**Status:**
```
GET /api/sync/status
→ {"server_version": 6, "user_id": "user_2abc123"}
```

### Shared Types

Both the cloud backend and the bridge daemon import canonical types from `shared/`:

```python
from shared.models.sync import SyncPayload, SyncConflict

# SyncPayload: entity_type, entity_id, user_id, action, data, timestamp, source
# SyncConflict: local_data, cloud_data, local_timestamp, cloud_timestamp
#               → resolve_last_write_wins()
```

---

## Subprocess Architecture

The desktop agent can spawn isolated worker subprocesses for parallel task execution:

```
Main Agent Process
├── SubprocessManager
│   ├── Worker Pool (configurable max concurrency)
│   ├── Task Queue (priority-based)
│   └── Result Collector
├── Workers
│   ├── FileEditWorker    — applies diffs, creates files
│   ├── CodeAnalysisWorker — AST parsing, complexity analysis
│   ├── ShellWorker       — sandboxed command execution
│   └── CustomWorker      — runs dynamically-created tools
└── Communication
    ├── stdin/stdout JSON protocol
    ├── Shared temp directory for large payloads
    └── Event stream back to agent
```

Workers are spawned on-demand and communicate with the main agent via JSON over stdin/stdout. Each worker runs in its own process with resource limits, providing isolation and parallel execution.

**Dynamic tool creation:** The agent can write new Python tools at runtime (`tool_creator.py`), validate them, and hot-load them into the tool registry without restarting.

---

## Gateway & WebSocket

The desktop agent exposes a local web interface via the gateway module:

- **`gateway/server.py`** — FastAPI HTTP server for the local web UI and REST API.
- **`gateway/routes.py`** — All REST endpoints (chat, tools, memory, skills, settings, etc.).
- **`gateway/ws.py`** — WebSocket handlers for real-time streaming of agent responses and events.

This is separate from the cloud backend — it runs locally alongside the desktop agent and provides a browser-based interface for interacting with the local agent directly.
