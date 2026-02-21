# Plutus Agent — Architecture

## Core Enhancement: Subprocess-Spawning AI Agent

The key upgrade is a **subprocess orchestrator** that allows Claude to:

1. **Spawn worker subprocesses** — isolated child processes for file editing, code analysis, and tool creation
2. **Parallel execution** — multiple workers can run simultaneously  
3. **Dynamic tool creation** — Claude can write new tools at runtime and hot-load them
4. **Sandboxed execution** — each subprocess runs in its own context with resource limits

## Module Structure

```
plutus/
├── __init__.py
├── __main__.py
├── cli.py                    # Enhanced CLI with interactive REPL mode
├── config.py                 # Configuration management
├── core/
│   ├── agent.py              # Main agent runtime (enhanced)
│   ├── conversation.py       # Conversation/context management
│   ├── heartbeat.py          # Heartbeat system
│   ├── llm.py                # LLM client (LiteLLM)
│   ├── memory.py             # SQLite memory store
│   ├── planner.py            # Plan management
│   └── subprocess_manager.py # NEW: Subprocess orchestrator
├── gateway/                  # Web API + WebSocket
├── guardrails/               # Permission tiers + audit
├── skills/                   # YAML skill definitions
└── tools/
    ├── base.py               # Tool base class
    ├── registry.py           # Tool registry (enhanced with hot-reload)
    ├── filesystem.py         # File operations
    ├── shell.py              # Shell commands
    ├── process.py            # Process management
    ├── code_analysis.py      # NEW: AST-based code analysis
    ├── code_editor.py        # NEW: Intelligent code editing
    ├── tool_creator.py       # NEW: Dynamic tool creation
    ├── subprocess_tool.py    # NEW: Subprocess spawning tool
    ├── browser.py
    ├── clipboard.py
    ├── desktop.py
    ├── system_info.py
    └── app_manager.py
```

## Subprocess Architecture

```
Main Agent Process
├── SubprocessManager
│   ├── Worker Pool (configurable max)
│   ├── Task Queue (priority-based)
│   └── Result Collector
├── Workers
│   ├── FileEditWorker    — applies diffs, creates files
│   ├── CodeAnalysisWorker — AST parsing, linting, dependency analysis
│   ├── ShellWorker       — sandboxed command execution
│   └── CustomWorker      — runs dynamically-created tools
└── Communication
    ├── stdin/stdout JSON protocol
    ├── Shared temp directory for large payloads
    └── Event stream back to agent
```
