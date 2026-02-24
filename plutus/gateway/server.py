"""Plutus Gateway Server.

Plutus v0.3.2 — Multi-model, multi-worker, scheduled agent.

Architecture:
  - Model Router: auto-selects Claude Opus/Sonnet/Haiku or GPT-5.2 per task
  - Worker Pool: concurrent agent workers with configurable max concurrency
  - Scheduler: persistent cron-based task scheduling
  - Standard Agent: LLM + function-calling with accessibility tree snapshots
  - Computer Use Agent: Anthropic native (explicit only)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from plutus.config import PlutusConfig, SecretsStore
from plutus.core.agent import AgentEvent, AgentRuntime
from plutus.core.heartbeat import HeartbeatRunner
from plutus.core.memory import MemoryStore
from plutus.core.model_router import ModelRouter, ModelRoutingConfig
from plutus.core.scheduler import Scheduler, ScheduledJob
from plutus.core.worker_pool import WorkerPool, WorkerTask, WorkerStatus, WorkerState
from plutus.gateway.routes import create_router
from plutus.gateway.ws import create_ws_router, manager as ws_manager
from plutus.guardrails.engine import GuardrailEngine
from plutus.tools.registry import create_default_registry

logger = logging.getLogger("plutus.gateway")

# Shared application state
_state: dict[str, Any] = {}


def get_state() -> dict[str, Any]:
    return _state


# ── Heartbeat callbacks ──────────────────────────────────────────────────────

async def _heartbeat_on_beat(prompt: str) -> None:
    """Called by the heartbeat runner — sends a synthetic message through the agent."""
    agent: AgentRuntime | None = _state.get("agent")
    if not agent:
        return
    async for event in agent.process_message(prompt):
        await ws_manager.broadcast(event.to_dict())


async def _heartbeat_on_event(event_data: dict[str, Any]) -> None:
    await ws_manager.broadcast(event_data)


# ── Worker executor ──────────────────────────────────────────────────────────

async def _worker_executor(task: WorkerTask, on_status: Any) -> str:
    """Execute a worker task using an INDEPENDENT LLM call.

    Workers do NOT route through the coordinator agent. They make their own
    standalone API call using litellm, with the model selected by the router.
    This prevents:
      - Self-await deadlocks (coordinator waiting on its own task)
      - Conversation context pollution between coordinator and workers
      - Recursion depth issues from circular dependencies
    """
    import litellm

    model_router: ModelRouter | None = _state.get("model_router")
    secrets: SecretsStore | None = _state.get("secrets")

    # Select model for this worker
    model_string = "anthropic/claude-sonnet-4-6"  # fallback
    model_display = "Claude Sonnet 4-6"

    if model_router:
        spec = model_router.select_for_worker(task.prompt, model_key=task.model_key)
        model_string = model_router.get_litellm_model_string(spec)
        model_display = spec.display_name
        # Record usage
        for key, s in __import__("plutus.core.model_router", fromlist=["AVAILABLE_MODELS"]).AVAILABLE_MODELS.items():
            if s.id == spec.id:
                model_router.record_usage(key)
                break

    # Update status
    status = WorkerStatus(
        task_id=task.id,
        state=WorkerState.RUNNING,
        name=task.name,
        current_step="Processing task...",
        model_used=model_display,
    )
    await on_status(status)

    # Broadcast to UI
    await ws_manager.broadcast({
        "type": "worker_started",
        "worker": {"task_id": task.id, "name": task.name, "model": model_display},
    })

    # Make an independent LLM call — NOT through the coordinator agent
    worker_system_prompt = (
        "You are a Plutus worker agent. You have been assigned a specific task by the "
        "coordinator. Complete the task thoroughly and return your result. "
        "Be concise but comprehensive. Do not ask follow-up questions — just do the work."
    )

    messages = [
        {"role": "system", "content": worker_system_prompt},
        {"role": "user", "content": task.prompt},
    ]

    try:
        # Update status
        status.current_step = f"Calling {model_display}..."
        await on_status(status)

        response = await litellm.acompletion(
            model=model_string,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
        )

        result = response.choices[0].message.content or "Task completed (no output)."

        # Update status
        status.current_step = "Done"
        status.steps_completed = 1
        status.progress_pct = 100.0
        await on_status(status)

    except Exception as e:
        result = f"[Worker Error] {e}"
        logger.exception(f"Worker {task.id} LLM call failed: {e}")

    # Broadcast completion status to workers panel
    await ws_manager.broadcast({
        "type": "worker_completed",
        "worker": {"task_id": task.id, "name": task.name, "result": result[:500]},
    })

    # Broadcast the full result to the chat — this is what the user sees
    await ws_manager.broadcast({
        "type": "worker_result",
        "task_id": task.id,
        "name": task.name,
        "model": model_display,
        "result": result,
        "duration": 0.0,  # will be set by worker_pool via status
    })

    return result


async def _worker_status_change(status: WorkerStatus) -> None:
    """Broadcast worker status changes to the UI."""
    await ws_manager.broadcast({
        "type": "worker_status",
        "worker": status.to_dict(),
    })


# ── Scheduler callback ──────────────────────────────────────────────────────

async def _scheduler_on_fire(job: ScheduledJob) -> str:
    """Called when a scheduled job fires."""
    pool: WorkerPool | None = _state.get("worker_pool")
    agent: AgentRuntime | None = _state.get("agent")

    if job.spawn_worker and pool:
        # Spawn as a worker
        task = WorkerTask(
            name=f"Scheduled: {job.name}",
            prompt=job.prompt,
            model_key=job.model_key,
            timeout=300.0,
        )
        status = await pool.submit(task)
        # Wait for it to complete
        final = await pool.wait_for(status.task_id, timeout=300.0)
        return final.result if final and final.result else "Job completed."
    elif agent:
        # Run on main agent
        result_parts = []
        async for event in agent.process_message(
            f"[SCHEDULED JOB: {job.name}]\n{job.prompt}"
        ):
            await ws_manager.broadcast(event.to_dict())
            if hasattr(event, "content") and event.content:
                result_parts.append(event.content)
        return "\n".join(result_parts) if result_parts else "Job completed."
    else:
        raise RuntimeError("No agent or worker pool available")


async def _scheduler_on_event(event_data: dict[str, Any]) -> None:
    await ws_manager.broadcast(event_data)


# ── Computer Use agent ───────────────────────────────────────────────────────

def _init_computer_use_agent(config: PlutusConfig, secrets: SecretsStore) -> Any:
    """Initialize the Anthropic Computer Use agent if possible."""
    try:
        from plutus.core.computer_use_agent import ComputerUseAgent
        from plutus.pc.computer_use import ComputerUseExecutor

        api_key = secrets.get_key("anthropic")
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("No Anthropic API key found — Computer Use agent disabled")
            return None

        cu_model = config.model.model
        if config.model.provider != "anthropic":
            cu_model = "claude-sonnet-4-6"

        executor = ComputerUseExecutor()
        agent = ComputerUseAgent(
            api_key=api_key,
            model=cu_model,
            executor=executor,
            max_iterations=config.agent.max_tool_rounds or 25,
        )
        logger.info(f"Computer Use agent initialized (model={cu_model})")
        return agent

    except ImportError as e:
        logger.warning(f"Computer Use agent not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize Computer Use agent: {e}")
        return None


# ── Connector auto-start ─────────────────────────────────────────────────────

async def _auto_start_connectors(connector_manager) -> None:
    """Auto-start connectors that have auto_start enabled."""
    for connector in connector_manager.get_configured():
        if not connector.auto_start:
            continue
        try:
            if connector.name == "telegram":
                from plutus.connectors.telegram_bridge import get_telegram_bridge
                bridge = get_telegram_bridge()
                await bridge.start()
                logger.info("Telegram bridge auto-started")
            else:
                await connector.start()
                logger.info(f"Connector auto-started: {connector.name}")
        except Exception as e:
            logger.error(f"Failed to auto-start connector {connector.name}: {e}")


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    config = PlutusConfig.load()

    # Initialize secrets store and inject stored keys into environment
    secrets = SecretsStore()
    secrets.inject_all()

    # Initialize model router
    routing_config = ModelRoutingConfig(
        enabled_models=config.model_routing.enabled_models,
        cost_conscious=config.model_routing.cost_conscious,
        default_worker_model=config.model_routing.default_worker_model,
        default_scheduler_model=config.model_routing.default_scheduler_model,
    )
    model_router = ModelRouter(config=routing_config, secrets=secrets)

    # Initialize memory
    memory = MemoryStore(config.resolve_memory_db())
    await memory.initialize()

    # Initialize guardrails
    guardrails = GuardrailEngine(config)

    # Initialize tool registry
    tool_registry = create_default_registry()

    # Initialize standard agent
    agent = AgentRuntime(
        config=config,
        guardrails=guardrails,
        memory=memory,
        tool_registry=tool_registry,
        secrets=secrets,
    )
    await agent.initialize()

    # Register memory tool
    from plutus.tools.memory_tool import MemoryTool
    memory_tool = MemoryTool(memory, agent.conversation)
    tool_registry.register(memory_tool)

    # Initialize worker pool
    worker_pool = WorkerPool(
        max_workers=config.workers.max_concurrent_workers,
        executor=_worker_executor,
        on_status_change=_worker_status_change,
    )

    # Register worker tool
    from plutus.tools.worker_tool import WorkerTool
    worker_tool = WorkerTool(worker_pool)
    tool_registry.register(worker_tool)

    # Initialize scheduler
    scheduler = Scheduler(
        on_fire=_scheduler_on_fire,
        on_event=_scheduler_on_event,
    )

    # Register scheduler tool
    from plutus.tools.scheduler_tool import SchedulerTool
    scheduler_tool = SchedulerTool(scheduler)
    tool_registry.register(scheduler_tool)

    # Start scheduler if enabled
    if config.scheduler.enabled:
        await scheduler.start()

    # Initialize Computer Use agent
    cu_agent = _init_computer_use_agent(config, secrets)

    # Initialize heartbeat
    heartbeat = HeartbeatRunner(
        config=config.heartbeat,
        on_beat=_heartbeat_on_beat,
        on_event=_heartbeat_on_event,
    )
    if config.heartbeat.enabled:
        heartbeat.start()

    # Initialize connector manager and register connector tool
    from plutus.connectors import create_connector_manager
    from plutus.tools.connector_tool import ConnectorTool
    connector_manager = create_connector_manager()
    connector_tool = ConnectorTool(connector_manager)
    tool_registry.register(connector_tool)

    # Store all state
    _state["config"] = config
    _state["secrets"] = secrets
    _state["memory"] = memory
    _state["guardrails"] = guardrails
    _state["tool_registry"] = tool_registry
    _state["agent"] = agent
    _state["cu_agent"] = cu_agent
    _state["heartbeat"] = heartbeat
    _state["connector_manager"] = connector_manager
    _state["model_router"] = model_router
    _state["worker_pool"] = worker_pool
    _state["scheduler"] = scheduler

    key_status = "configured" if agent.key_configured else "NOT configured"
    cu_status = "enabled" if cu_agent else "disabled"
    heartbeat_status = "enabled" if config.heartbeat.enabled else "disabled"
    scheduler_status = "enabled" if config.scheduler.enabled else "disabled"
    logger.info(
        f"Plutus v0.3.2 started — tier={config.guardrails.tier}, "
        f"model={config.model.provider}/{config.model.model}, "
        f"api_key={key_status}, computer_use={cu_status}, "
        f"heartbeat={heartbeat_status}, scheduler={scheduler_status}, "
        f"max_workers={config.workers.max_concurrent_workers}, "
        f"worker_model={config.model_routing.default_worker_model}, "
        f"scheduler_model={config.model_routing.default_scheduler_model}"
    )

    # Auto-start connectors
    await _auto_start_connectors(connector_manager)

    yield

    # Shutdown
    heartbeat.stop()
    await scheduler.stop()
    await worker_pool.cleanup()
    await connector_manager.stop_all()
    await agent.shutdown()
    logger.info("Plutus shut down")


def create_app(config: PlutusConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Plutus",
        version="0.3.2",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(create_router(), prefix="/api")
    app.include_router(create_ws_router())

    # Serve the UI
    ui_dir = Path(__file__).parent.parent.parent / "ui" / "dist"
    if ui_dir.exists():
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app
