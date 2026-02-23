# Architecture Notes for Major Upgrade

## Current State

### LLM (core/llm.py)
- Uses LiteLLM for model-agnostic completions
- Single model configured via ModelConfig (provider + model string)
- No model routing — same model for everything
- Supports Anthropic, OpenAI, Ollama, custom endpoints

### Config (config.py)
- ModelConfig: single provider/model/temperature/max_tokens
- No concept of multiple models or task-based routing
- SecretsStore: per-provider API keys

### SubprocessManager (core/subprocess_manager.py)
- Spawns Python subprocess workers via stdin/stdout JSON protocol
- Worker types: shell, file_edit, code_analysis, custom
- Has max_workers (default 5), priority queue, timeout
- Workers are short-lived — spawn, execute, collect result, stop
- No concept of "agent workers" (workers that can think/plan)

### SubprocessTool (tools/subprocess_tool.py)
- Agent tool interface to SubprocessManager
- Operations: spawn, spawn_many, list_active, list_results, cancel

### Heartbeat (core/heartbeat.py)
- Periodic wake-up system for autonomous operation
- Configurable interval, quiet hours, max consecutive
- Sends synthetic message to agent
- NOT a cron system — just periodic heartbeats

### Workers UI (WorkersView.tsx)
- Shows active workers, recent tasks, stats
- Has auto-refresh, cancel buttons
- Already decent — needs model info + scheduler view

## What Needs to Be Built

### 1. Model Router (NEW)
- ModelRouter class that selects the right model per task
- Task complexity classification: simple/medium/complex
- Model tiers:
  - Claude: opus (complex), sonnet (balanced), haiku (simple)
  - OpenAI: gpt-5.2 (all tasks)
- Agent can override with explicit model choice
- Config: user sets which models are available + cost preferences

### 2. Agent Workers (UPGRADE subprocess system)
- Workers that are mini-agents (can call LLM, use tools)
- Each worker gets its own LLM client with appropriate model
- Main agent can spawn worker agents for parallel tasks
- Workers report status back to main agent
- Need: AgentWorker class, WorkerPool, status tracking

### 3. Scheduler/Cron (NEW)
- CronScheduler class — manages scheduled tasks
- Persistent storage (survives restarts)
- Cron expression support + simple interval support
- Each job has: name, schedule, prompt, model_tier, enabled
- Jobs fire by sending prompt to agent (like heartbeat)
- UI to view/edit/delete scheduled jobs

### 4. Config Updates
- WorkerConfig: max_concurrent_workers (user-configurable)
- ModelRoutingConfig: available models, cost limits
- SchedulerConfig: enabled, max_concurrent_jobs

### 5. UI Updates
- Workers tab: show agent workers with their model, task, status
- Scheduler section: list cron jobs, create/edit/delete
- Settings: max workers slider, model preferences
