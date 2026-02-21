# Plutus - AI Agent with Full System Control

## Quick Reference

```bash
# Install
pip install -e ".[dev]"
cd ui && npm install

# Run
plutus start            # Production (serves built UI)
plutus start --dev      # Dev mode (Vite proxy on :5173)

# Test
pytest tests            # All tests
pytest tests -x -q      # Stop on first failure, quiet output

# Lint
ruff check plutus/      # Check Python
ruff check --fix plutus/ # Auto-fix

# Build UI
cd ui && npm run build  # TypeScript check + Vite build → ui/dist/
```

## Architecture

Monorepo: Python backend (`plutus/`) + React/TypeScript frontend (`ui/`).

### Backend (`plutus/`)

- **`core/agent.py`** — Main agent loop. `process_message()` yields `AgentEvent` objects. Tool rounds are capped by `config.agent.max_tool_rounds` (plan tool calls don't count toward the limit).
- **`core/llm.py`** — LLM client via LiteLLM. Model-agnostic (Anthropic, OpenAI, Ollama, custom).
- **`core/memory.py`** — SQLite-backed async store (aiosqlite). Conversations, messages, learned facts.
- **`core/conversation.py`** — Message history management with context windowing.
- **`core/planner.py`** — Built-in plan tool for multi-step task tracking.
- **`core/heartbeat.py`** — Autonomous background execution with configurable intervals.
- **`gateway/server.py`** — FastAPI server, lifespan setup, static UI serving.
- **`gateway/routes.py`** — REST API endpoints for config, guardrails, history, approvals.
- **`gateway/ws.py`** — WebSocket handler for real-time agent events.
- **`guardrails/`** — 4-tier permission system (observer → assistant → operator → autonomous). Policies in `tiers.py`, engine in `engine.py`, audit logging.
- **`tools/`** — Tool implementations (shell, filesystem, browser, process, system_info, clipboard, desktop, app_manager). Each extends base `Tool` class with async `execute()`.
- **`config.py`** — Pydantic config stored at `~/.plutus/config.json`. Secrets in `~/.plutus/.secrets.json` (chmod 600).

### Frontend (`ui/`)

- React 19 + TypeScript 5.6 + Vite 6 + TailwindCSS 3.4
- Zustand for state (`stores/appStore.ts`)
- Components: `chat/`, `dashboard/`, `settings/`, `guardrails/`
- API client: `lib/api.ts` — REST calls to FastAPI backend
- WebSocket hook: `hooks/useWebSocket.ts` — real-time event streaming

### Key Patterns

- **Event streaming**: Agent emits typed events (`thinking`, `text`, `tool_call`, `tool_result`, `done`) → WebSocket → UI renders in real time.
- **Guardrail flow**: Every tool call → `guardrails.check()` → allowed / denied / requires_approval → approval queue with timeout.
- **Config updates**: UI PATCH `/api/config` → `config.update(patch)` → deep merge → save to disk. Some settings (heartbeat) apply live via dedicated endpoints.

## Code Style

- Python: ruff with `line-length = 100`, rules `E, F, I, N, W, UP`, target `py311`
- Use `from __future__ import annotations` in all Python files
- Type hints everywhere (Pydantic models for config, typed dicts for tool results)
- Async-first: all I/O operations use async/await
- Frontend: TypeScript strict mode, functional React components with hooks

## Testing

- pytest with `asyncio_mode = "auto"` — async tests just work
- Test files: `tests/test_config.py`, `tests/test_guardrails.py`, `tests/test_tools.py`
- Run `pytest tests -x -q` before committing

## Config Locations

- `~/.plutus/config.json` — All settings (model, guardrails, gateway, memory, heartbeat, planner, agent)
- `~/.plutus/.secrets.json` — API keys only (chmod 600, never in config.json)
- `~/.plutus/memory.db` — SQLite conversation/memory store
- `~/.plutus/skills/` — User-defined YAML skills
