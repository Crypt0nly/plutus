# Plutus Bridge Daemon

> A lightweight background process that connects your local machine to Plutus Cloud via WebSocket, enabling the cloud agent to execute tasks on your PC — shell commands, file operations, app launching, and more.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Supported Task Types](#supported-task-types)
- [Sync Client](#sync-client)
- [Running as a Service](#running-as-a-service)
- [CLI Reference](#cli-reference)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Plutus Bridge daemon is a small Python process that runs on your local machine and maintains a persistent WebSocket connection to the Plutus Cloud backend. When you interact with your agent through the cloud web UI, the agent can dispatch tasks to your bridge, which executes them locally and returns the results.

**Use cases:**
- Run shell commands on your PC from the cloud agent
- Read and write files on your local filesystem
- Open applications on your desktop
- Sync memory, skills, and scheduled tasks between local SQLite and cloud PostgreSQL

**Requirements:**
- Python 3.10+
- A Plutus Cloud account (Clerk authentication)
- Network access to your Plutus Cloud instance

---

## How It Works

```
┌──────────────────┐         WebSocket (wss://)        ┌──────────────────┐
│                  │ ◄────────────────────────────────► │                  │
│   Plutus Cloud   │   /api/bridge/ws/{jwt_token}      │  Bridge Daemon   │
│   Backend        │                                    │  (your PC)       │
│                  │   1. Authenticate via JWT           │                  │
│                  │   2. Receive tasks                  │  Executes:       │
│                  │   3. Return results                 │  - Shell commands│
│                  │   4. Heartbeat every 30s            │  - File I/O      │
│                  │                                    │  - App launching │
└──────────────────┘                                    └──────────────────┘
```

1. The bridge authenticates with a Clerk JWT and opens a WebSocket to the cloud backend.
2. The backend registers the connection and marks the user's bridge as "connected."
3. When the cloud agent needs to execute something locally, it sends a task message over the WebSocket.
4. The bridge executes the task in a subprocess and sends back the result.
5. A heartbeat is sent every 30 seconds; the server responds with `heartbeat_ack`.
6. If the connection drops, the bridge automatically reconnects with exponential backoff.

---

## Installation

### From the Monorepo

```bash
cd bridge
pip install -r requirements.txt
```

### Dependencies

The bridge has minimal dependencies:

| Package      | Version  | Purpose                  |
|-------------|----------|--------------------------|
| `websockets`| ≥ 12.0   | WebSocket client library |

> **Note:** `websockets` is auto-installed on first run if missing. Additional sync functionality requires `httpx` and `aiosqlite` (from the sync client).

### Install Sync Dependencies (Optional)

If you plan to use the local ↔ cloud sync feature:

```bash
pip install httpx aiosqlite
```

---

## Configuration

### Interactive Setup

Run the setup wizard to configure the bridge for the first time:

```bash
python plutus_bridge.py --setup
```

This will prompt you for:
1. **Auth token** — Your Clerk JWT (obtain from the Plutus Cloud web UI under Settings, or from the Clerk dashboard).
2. **Server URL** — The WebSocket URL of your Plutus Cloud instance (default: `ws://localhost:8000/api/bridge/ws`).

The configuration is saved to `~/.plutus/bridge_config.json`.

### Config File

**Location:** `~/.plutus/bridge_config.json`

```json
{
  "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "server": "wss://cloud.plutus.ai/api/bridge/ws"
}
```

| Field    | Description                                           |
|----------|-------------------------------------------------------|
| `token`  | Clerk JWT for authentication                          |
| `server` | WebSocket URL of the Plutus Cloud bridge endpoint     |

### Config Directory

The bridge stores all configuration in `~/.plutus/`:

```
~/.plutus/
├── bridge_config.json    # Bridge configuration (token, server URL)
├── sync_state.json       # Last sync version (used by sync_client.py)
└── memory.db             # Local SQLite database (used by sync_client.py)
```

---

## Usage

### Basic Usage

```bash
# Start with saved configuration
python plutus_bridge.py

# Start with explicit server URL
python plutus_bridge.py --server wss://cloud.plutus.ai/api/bridge/ws

# Start with explicit token
python plutus_bridge.py --token eyJhbGciOiJSUzI1NiIs...

# Both
python plutus_bridge.py --server wss://cloud.plutus.ai/api/bridge/ws --token eyJ...
```

### Expected Output

```
2025-01-15 10:30:00 [BRIDGE] INFO: Connecting to wss://cloud.plutus.ai/api/bridge/ws...
2025-01-15 10:30:01 [BRIDGE] INFO: Connected to Plutus Cloud!
2025-01-15 10:30:31 [BRIDGE] INFO: Executing task abc123: shell
2025-01-15 10:30:32 [BRIDGE] INFO: Executing task def456: read_file
```

### Checking Bridge Status

From the cloud web UI or API:

```bash
# API check
curl -H "Authorization: Bearer <token>" https://cloud.plutus.ai/api/bridge/status
# → {"connected": true}
```

The Dashboard page in the web UI also shows bridge connection status.

---

## Supported Task Types

The bridge can execute the following task types dispatched from the cloud:

| Task Type    | Payload Fields               | Description                                      | Response Fields                          |
|-------------|------------------------------|--------------------------------------------------|------------------------------------------|
| `shell`     | `command` (str), `timeout` (int, default 60) | Execute a shell command via subprocess | `success`, `stdout`, `stderr`, `exit_code` |
| `open_app`  | `app_name` (str)             | Open an application (cross-platform)             | `success`, `message`                     |
| `read_file` | `path` (str)                 | Read a local file (max 50KB returned)            | `success`, `content` or `error`          |
| `write_file`| `path` (str), `content` (str)| Write content to a local file (creates dirs)     | `success`, `message`                     |
| `list_files`| `path` (str), `pattern` (str, default `*`) | List files matching a glob pattern (max 500) | `success`, `files`                       |
| `ping`      | —                            | Health check; returns system info                | `success`, `message`, `system`           |

### Platform-Specific Behavior

- **`open_app`** uses `os.startfile()` on Windows, `open -a` on macOS, and `xdg-open` on Linux.
- **`shell`** uses `asyncio.create_subprocess_shell()` — the command runs in the system's default shell.
- **`read_file`** output is truncated to 50,000 characters. Binary files are decoded with `errors="replace"`.

---

## Sync Client

The `sync_client.py` module provides bidirectional sync between the local SQLite database and the cloud PostgreSQL:

```python
from sync_client import LocalSyncClient

client = LocalSyncClient(
    server_url="https://cloud.plutus.ai",
    token="eyJ...",
    local_db_path="~/.plutus/memory.db",
)

# Push local changes to cloud
await client.push_local_changes()

# Pull cloud changes to local
await client.pull_cloud_changes()

# Full bidirectional sync
await client.full_sync()
```

### Sync State

The sync client tracks the last synchronized version in `~/.plutus/sync_state.json`:

```json
{"version": 42}
```

On each push/pull, only changes newer than this version are transferred.

### Sync Strategy

- **Push:** Reads local memories with `sync_version > last_known_version`, sends them to `POST /api/sync/push`.
- **Pull:** Fetches changes from `GET /api/sync/pull?since_version=N`, applies them to local SQLite with `INSERT ... ON CONFLICT DO UPDATE`.
- **Conflict resolution:** Last-write-wins. The cloud is the source of truth.

---

## Running as a Service

### Linux (systemd)

Create `/etc/systemd/system/plutus-bridge.service`:

```ini
[Unit]
Description=Plutus Bridge Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/plutus/bridge
ExecStart=/usr/bin/python3 plutus_bridge.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable plutus-bridge
sudo systemctl start plutus-bridge

# Check status
sudo systemctl status plutus-bridge

# View logs
journalctl -u plutus-bridge -f
```

### macOS (launchd)

Create `~/Library/LaunchAgents/com.plutus.bridge.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.plutus.bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/plutus/bridge/plutus_bridge.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/plutus-bridge.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/plutus-bridge.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.plutus.bridge.plist
launchctl start com.plutus.bridge
```

### Windows (Task Scheduler)

1. Open Task Scheduler (`taskschd.msc`).
2. Create a new task:
   - **Trigger:** At log on
   - **Action:** Start a program
     - Program: `python`
     - Arguments: `C:\path\to\plutus\bridge\plutus_bridge.py`
     - Start in: `C:\path\to\plutus\bridge`
   - **Settings:** "If the task fails, restart every 1 minute" (up to 3 retries)
3. Check "Run whether user is logged on or not" if desired.

Alternatively, use `pythonw.exe` instead of `python` to run without a console window.

---

## CLI Reference

```
usage: plutus_bridge.py [-h] [--server SERVER] [--token TOKEN] [--setup]

Plutus Local Bridge Daemon

options:
  -h, --help       Show this help message and exit
  --server SERVER  Cloud WebSocket URL
                   (default: ws://localhost:8000/api/bridge/ws)
  --token TOKEN    Authentication token (Clerk JWT)
  --setup          Run interactive setup wizard
```

**Precedence:** CLI flags override config file values. If neither is provided, defaults are used.

---

## Troubleshooting

### Connection Refused

```
[BRIDGE] WARNING: Connection lost: [Errno 111] Connection refused. Reconnecting in 5s...
```

**Causes:**
- The cloud backend is not running.
- The `--server` URL is incorrect.
- A firewall is blocking the connection.

**Fix:**
- Verify the backend is running: `curl http://localhost:8000/api/health`
- Check the server URL in `~/.plutus/bridge_config.json`
- Ensure ports are open (default: 8000 for HTTP, same for WebSocket)

### Authentication Failed (4001)

```
[BRIDGE] WARNING: Connection lost: received 4001 (private use); ...
```

**Causes:**
- The JWT token has expired.
- The token is invalid or malformed.
- Clerk JWKS keys have rotated.

**Fix:**
- Re-run `python plutus_bridge.py --setup` and enter a fresh token.
- Ensure the Clerk keys in the backend `.env` match the keys used to generate the token.

### Bridge Shows Connected but Tasks Fail

**Causes:**
- The task type is not supported.
- The local command failed (e.g., `shell` command not found).
- File permissions prevent read/write.

**Fix:**
- Check bridge logs for error details.
- Test the command manually on your machine.
- Ensure the bridge process has appropriate permissions.

### Reconnection Loop (Exponential Backoff)

The bridge uses exponential backoff when reconnecting:

| Attempt | Delay  |
|---------|--------|
| 1       | 5s     |
| 2       | 10s    |
| 3       | 20s    |
| 4       | 40s    |
| 5       | 80s    |
| 6       | 160s   |
| 7+      | 300s   |

The delay resets to 5 seconds after a successful connection. If you see the delay climbing, the backend is likely unreachable.

### Sync Not Working

**Causes:**
- `httpx` and/or `aiosqlite` are not installed.
- The local SQLite database doesn't exist or has a different schema.
- The sync version in `~/.plutus/sync_state.json` is ahead of the server.

**Fix:**
- Install sync dependencies: `pip install httpx aiosqlite`
- Delete `~/.plutus/sync_state.json` to force a full re-sync.
- Verify the local database path: default is `~/.plutus/memory.db`.

### High CPU or Memory Usage

The bridge is designed to be lightweight (< 20MB RAM, negligible CPU). If you see high resource usage:

- Check for runaway `shell` tasks with long or infinite output.
- Ensure the `timeout` parameter is set on shell tasks (default: 60 seconds).
- Check for rapid reconnection loops (indicates a persistent auth or network issue).

### Logs

The bridge logs to stdout with the format:

```
2025-01-15 10:30:00 [BRIDGE] INFO: message
```

To redirect logs to a file:

```bash
python plutus_bridge.py 2>&1 | tee -a ~/.plutus/bridge.log
```

Or set `PYTHONUNBUFFERED=1` when running as a service to ensure logs are flushed immediately.
