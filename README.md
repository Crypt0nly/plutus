# Plutus — Autonomous AI Agent with Subprocess Orchestration

<p align="center">
  <strong>A better, easier-to-use AI agent that spawns subprocesses to edit code, analyze files, and create new tools on the fly.</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#tools">Tools</a> •
  <a href="#dynamic-tool-creation">Dynamic Tools</a> •
  <a href="#configuration">Configuration</a>
</p>

---

## What is Plutus?

Plutus is an autonomous AI agent system that gives Claude (or any LLM) the ability to **spawn isolated subprocesses** for file editing, code analysis, shell execution, and dynamic tool creation. Think of it as **Claude Code on steroids** — the AI can not only run commands and edit files, but also create entirely new tools at runtime to solve problems it wasn't originally designed for.

### Key Differentiators

| Feature | OpenClaw | Plutus |
|---------|----------|--------|
| File editing | Basic read/write | Subprocess-isolated surgical edits with diff output |
| Code analysis | None | Full AST analysis (functions, classes, complexity, call graphs) |
| Subprocess spawning | None | Parallel worker pool with JSON protocol |
| Dynamic tool creation | None | Create, validate, and hot-load new Python tools at runtime |
| CLI experience | Basic | Rich interactive REPL with slash commands |
| Guardrails | Basic | 4-tier system (observer → autonomous) with audit logging |
| Planning | None | Built-in plan/step tracking with auto-progress |

## Features

### Subprocess Orchestration
The agent spawns isolated worker subprocesses for every operation — file edits, code analysis, shell commands, and custom scripts all run in their own process with resource limits and timeouts.

### Intelligent Code Editing
Surgical find/replace edits with diff output. The agent reads files, applies precise changes, and verifies the result — all in subprocess isolation.

### Deep Code Analysis
AST-based analysis of Python files:
- Function and class extraction with signatures
- Cyclomatic complexity scoring (A–F ratings)
- Import dependency mapping
- Call graph generation
- TODO/FIXME/HACK detection
- Module summarization

### Dynamic Tool Creation
The agent can write new Python tools at runtime:
1. Writes the tool code
2. Validates it (syntax check)
3. Saves it to `~/.plutus/custom_tools/`
4. Hot-loads it into the tool registry
5. Uses it immediately

### 4-Tier Guardrail System
- **Observer** — Read-only, AI can only observe
- **Assistant** — Every action requires user approval
- **Operator** — Pre-approved actions run autonomously
- **Autonomous** — Full control, no restrictions

### Multiple Interfaces
- **Terminal REPL** (`plutus chat`) — Rich interactive chat with slash commands
- **Single prompt** (`plutus run "..."`) — Execute one task and exit
- **Web UI** (`plutus start`) — Full web interface with WebSocket streaming

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Crypt0nly/plutus.git
cd plutus

# Install with pip
pip install -e .

# Run setup wizard
plutus setup
```

### First Run

```bash
# Interactive terminal chat
plutus chat

# Or run a single prompt
plutus run "Create a Python script that sorts a CSV file by the second column"

# Or launch the web UI
plutus start
```

### Chat Commands

Inside `plutus chat`, use slash commands:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/tools` | List all available tools |
| `/plan` | Show current execution plan |
| `/clear` | Start a new conversation |
| `/tier` | Show or change guardrail tier |
| `/workers` | Show active subprocesses |
| `/exit` | Exit the chat |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Agent Runtime                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │   LLM    │  │ Planner  │  │   Guardrails     │  │
│  │ (Claude) │  │          │  │ (4-tier system)  │  │
│  └────┬─────┘  └──────────┘  └──────────────────┘  │
│       │                                              │
│  ┌────▼──────────────────────────────────────────┐  │
│  │              Tool Registry                     │  │
│  │  ┌────────┐ ┌────────────┐ ┌───────────────┐  │  │
│  │  │ Shell  │ │ Code Editor│ │ Code Analysis │  │  │
│  │  └────────┘ └────────────┘ └───────────────┘  │  │
│  │  ┌────────────┐ ┌──────────────┐ ┌─────────┐  │  │
│  │  │ Subprocess │ │ Tool Creator │ │ Browser │  │  │
│  │  └────────────┘ └──────────────┘ └─────────┘  │  │
│  │  ┌──────────┐ ┌─────────┐ ┌─────────────────┐ │  │
│  │  │Filesystem│ │ Process │ │ Custom Tools... │ │  │
│  │  └──────────┘ └─────────┘ └─────────────────┘ │  │
│  └───────────────────┬───────────────────────────┘  │
│                      │                               │
│  ┌───────────────────▼───────────────────────────┐  │
│  │           Subprocess Manager                   │  │
│  │  ┌─────────────┐  ┌──────────────────────┐    │  │
│  │  │ Worker Pool │  │  JSON stdin/stdout    │    │  │
│  │  │ (max: 8)    │  │  protocol             │    │  │
│  │  └─────────────┘  └──────────────────────┘    │  │
│  └───────────────────────────────────────────────┘  │
│                      │                               │
│  ┌───────────────────▼───────────────────────────┐  │
│  │           Worker Subprocesses                  │  │
│  │  ┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ │  │
│  │  │Shell │ │File Edit │ │Code Anal.│ │Custom│ │  │
│  │  │Worker│ │Worker    │ │Worker    │ │Worker│ │  │
│  │  └──────┘ └──────────┘ └──────────┘ └──────┘ │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Subprocess Communication Protocol

Workers communicate via **JSON over stdin/stdout** (one JSON object per line):

```
Agent → Worker:  {"action": "edit", "path": "/file.py", "edits": [...]}
Worker → Agent:  {"success": true, "result": {"changes": 2, "diff": "..."}}
```

This design provides:
- **Isolation** — each operation runs in its own process
- **Safety** — crashes in workers don't affect the agent
- **Parallelism** — multiple workers can run simultaneously
- **Simplicity** — JSON protocol is easy to debug and extend

## Tools

### Built-in Tools

| Tool | Description |
|------|-------------|
| `shell` | Execute shell commands |
| `filesystem` | File system operations (legacy, still available) |
| `code_editor` | Create, read, and edit files via subprocess |
| `code_analysis` | AST-based Python code analysis via subprocess |
| `subprocess` | Direct subprocess spawning for parallel tasks |
| `tool_creator` | Create new tools at runtime |
| `process` | System process management |
| `system_info` | System information queries |
| `browser` | Web browsing (Playwright) |
| `clipboard` | Clipboard operations |
| `desktop` | Desktop/window management |
| `app_manager` | Application management |

### Code Editor Operations

```
read       — Read file content (with optional line range)
write      — Create or overwrite a file
append     — Append content to a file
edit       — Apply surgical find/replace edits
delete     — Delete a file or directory
move       — Move/rename a file
copy       — Copy a file or directory
mkdir      — Create directories
list       — List directory contents
find       — Find files by glob pattern
grep       — Search file contents with regex
diff       — Show diff between two files
```

### Code Analysis Operations

```
analyze        — Full analysis (everything below combined)
find_functions — List all function/method definitions with signatures
find_classes   — List all class definitions with methods
find_imports   — Extract all import statements
find_todos     — Find TODO/FIXME/HACK/NOTE comments
complexity     — Calculate cyclomatic complexity per function
symbols        — Extract all top-level symbols
call_graph     — Build function call graph
summarize      — Generate human-readable summary
```

## Dynamic Tool Creation

The agent can create new tools when it encounters a task that requires capabilities it doesn't have:

```python
# Example: Agent creates a CSV processor tool
tool_creator(
    operation="create",
    tool_name="csv_processor",
    description="Process and transform CSV files",
    code="""
import csv
from pathlib import Path

def main(args):
    path = args.get('path', '')
    operation = args.get('operation', 'read')
    
    if operation == 'read':
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        return {'success': True, 'result': {'rows': rows, 'count': len(rows)}}
    
    elif operation == 'sort':
        column = args.get('column', '')
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = sorted(list(reader), key=lambda r: r.get(column, ''))
        return {'success': True, 'result': {'rows': rows, 'count': len(rows)}}
    
    return {'success': False, 'error': f'Unknown operation: {operation}'}
"""
)
```

Created tools are:
- **Validated** — syntax-checked before saving
- **Persisted** — saved to `~/.plutus/custom_tools/` across sessions
- **Hot-loaded** — immediately available in the tool registry
- **Isolated** — executed in subprocess workers

## Configuration

### Config File: `~/.plutus/config.json`

```json
{
  "model": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6-20250514",
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "guardrails": {
    "tier": "operator",
    "audit_enabled": true
  },
  "agent": {
    "max_tool_rounds": 25
  },
  "planner": {
    "enabled": true,
    "auto_plan": true
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 7777
  }
}
```

### Supported Providers

| Provider | Models | Config |
|----------|--------|--------|
| Anthropic | Claude 4 Sonnet, Claude 4 Opus, etc. | `ANTHROPIC_API_KEY` |
| OpenAI | GPT-4.1, GPT-4.1-mini, etc. | `OPENAI_API_KEY` |
| Ollama | Llama 3.2, Mistral, etc. | Local, no key needed |
| Custom | Any OpenAI-compatible endpoint | `API_KEY` + base URL |

### API Keys

Keys are stored securely in `~/.plutus/.secrets.json` (chmod 600) and never exposed via the API. Set them via:

```bash
# Setup wizard
plutus setup

# Environment variable
export ANTHROPIC_API_KEY=sk-ant-...

# Or via the web UI settings page
```

## CLI Reference

```bash
plutus                  # Show help
plutus start            # Launch web UI + API server
plutus chat             # Interactive terminal chat
plutus run "prompt"     # Run a single prompt
plutus setup            # Setup wizard
plutus status           # Show configuration
plutus tools            # List available tools
plutus set-tier <tier>  # Change guardrail tier
plutus audit            # Show audit log
plutus config-show      # Display full config as JSON
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run specific test file
pytest tests/test_subprocess.py -v

# Lint
ruff check plutus/
```

## Project Structure

```
plutus/
├── plutus/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                      # CLI with chat REPL
│   ├── config.py                   # Configuration management
│   ├── core/
│   │   ├── agent.py                # Main agent runtime
│   │   ├── conversation.py         # Conversation management
│   │   ├── heartbeat.py            # Heartbeat system
│   │   ├── llm.py                  # LLM client (LiteLLM)
│   │   ├── memory.py               # SQLite memory store
│   │   ├── planner.py              # Plan management
│   │   └── subprocess_manager.py   # Subprocess orchestrator
│   ├── gateway/                    # Web API + WebSocket
│   ├── guardrails/                 # Permission tiers + audit
│   ├── skills/                     # YAML skill definitions
│   ├── tools/
│   │   ├── base.py                 # Tool base class
│   │   ├── registry.py             # Tool registry with hot-reload
│   │   ├── code_analysis.py        # AST-based code analysis
│   │   ├── code_editor.py          # File creation and editing
│   │   ├── subprocess_tool.py      # Direct subprocess spawning
│   │   ├── tool_creator.py         # Dynamic tool creation
│   │   ├── shell.py                # Shell commands
│   │   ├── filesystem.py           # File system operations
│   │   ├── process.py              # Process management
│   │   ├── browser.py              # Web browsing
│   │   └── ...
│   └── workers/
│       ├── shell_worker.py         # Shell command worker
│       ├── file_edit_worker.py     # File editing worker
│       ├── code_analysis_worker.py # Code analysis worker
│       └── custom_worker.py        # Dynamic tool worker
├── ui/                             # React web interface
├── tests/
│   ├── test_subprocess.py          # 34 comprehensive tests
│   ├── test_config.py
│   ├── test_guardrails.py
│   └── test_tools.py
├── pyproject.toml
└── README.md
```

## License

MIT License — see [LICENSE](LICENSE) for details.
