# Plutus

**Autonomous AI agent with configurable guardrails — local-first, self-hosted, and built for safety.**

Plutus is a self-hosted AI runtime that gives you a fully autonomous agent with real computer control — shell execution, file management, browser automation, and more — wrapped in a guardrails system that lets **you** decide how much power the AI has.

```
pip install plutus-ai
plutus start
```

That's it. Plutus launches a local web UI and agent runtime on your machine.

---

## Why Plutus?

| | Plutus | OpenClaw |
|---|---|---|
| **Guardrails** | 4-tier permission system with per-tool controls | Pairing mode only |
| **Interface** | Bundled web UI with real-time chat + dashboard | Messaging apps (WhatsApp, Telegram) |
| **Security** | Sandboxed execution, audit trails, approval workflows | 512 vulnerabilities found in audit |
| **Setup** | `pip install && plutus start` | npm install + daemon + messaging config |
| **UX** | Visual guardrails config, inline tool approvals | CLI-heavy, config file editing |

## Core Concepts

### Guardrails — You Control the Power

Plutus ships with four access tiers. Pick the one that matches your comfort level:

| Tier | What the AI Can Do |
|---|---|
| **Observer** | Read files, view system info — no writes, no execution |
| **Assistant** | Suggest actions, but every single one requires your approval |
| **Operator** | Execute pre-approved action types autonomously; ask for the rest |
| **Autonomous** | Full system control — the AI handles everything |

Every tier lets you toggle individual tools on or off. Running in Operator mode but don't want browser access? One toggle. Want shell execution but not file deletion? Done.

Every action is logged to an audit trail you can review anytime.

### Tools — What Plutus Can Do

- **Shell** — Execute commands, run scripts, install packages
- **Filesystem** — Read, write, search, and manage files
- **Browser** — Navigate, click, fill forms, extract data (Playwright)
- **Process** — List, start, and stop system processes
- **System** — CPU, memory, disk, network information
- **Clipboard** — Read and write clipboard contents

### Skills — Teach Plutus New Tricks

Drop a skill file into `~/.plutus/skills/` and Plutus learns new capabilities:

```yaml
# ~/.plutus/skills/deploy.yaml
name: deploy
description: Deploy the current project to production
tools_required: [shell, filesystem]
tier_minimum: operator
steps:
  - run: npm run build
  - run: npm run deploy
```

### Memory — It Remembers

Plutus maintains persistent memory across sessions:
- Conversation history with full context
- Learned facts about you and your workflows
- Project-specific context that accumulates over time

### Model-Agnostic

Bring your own model. Plutus supports:
- **Anthropic** — Claude Opus, Sonnet, Haiku
- **OpenAI** — GPT-4o, o1, o3
- **Local** — Ollama, LM Studio, any OpenAI-compatible endpoint

## Quick Start

### 1. Install

```bash
pip install plutus-ai
```

### 2. Configure

```bash
plutus setup
```

The interactive wizard walks you through:
- Choosing your LLM provider and API key
- Setting your guardrail tier
- Configuring which tools are enabled

### 3. Launch

```bash
plutus start
```

Opens the Plutus web interface at `http://localhost:7777`. Start chatting.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                 Plutus Web UI (React)                 │
│   Chat  ·  Dashboard  ·  Guardrails  ·  Settings     │
└──────────────────┬───────────────────────────────────┘
                   │ WebSocket + REST
┌──────────────────┴───────────────────────────────────┐
│              Plutus Gateway (FastAPI)                 │
│                                                      │
│  ┌─────────┐  ┌────────────┐  ┌────────────────┐    │
│  │  Agent   │  │ Guardrails │  │  Tool Engine   │    │
│  │ Runtime  │  │   Engine   │  │                │    │
│  └─────────┘  └────────────┘  └────────────────┘    │
│  ┌─────────┐  ┌────────────┐  ┌────────────────┐    │
│  │ Memory  │  │   Skills   │  │  Audit Logger  │    │
│  │  Store  │  │   System   │  │                │    │
│  └─────────┘  └────────────┘  └────────────────┘    │
└──────────────────────────────────────────────────────┘
```

## Configuration

Plutus stores its configuration in `~/.plutus/config.json`:

```json
{
  "model": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "api_key_env": "ANTHROPIC_API_KEY"
  },
  "guardrails": {
    "tier": "assistant",
    "tool_overrides": {
      "shell": { "enabled": true, "require_approval": true },
      "browser": { "enabled": false }
    }
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 7777
  }
}
```

## Development

```bash
git clone https://github.com/plutus-ai/plutus.git
cd plutus

# Backend
pip install -e ".[dev]"

# Frontend
cd ui && npm install && npm run dev

# Run in development mode
plutus start --dev
```

## License

MIT
