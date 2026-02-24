"""Main FastAPI application — serves the API and static UI files.

Plutus v0.3.0 — Multi-model, multi-worker, scheduled agent.

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
from plutus.core.worker_pool import WorkerPool, WorkerTask, WorkerStatus
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
    """Execute a worker task using a dedicated LLM call.

    This is the function that the WorkerPool calls for each worker.
    It creates a mini agent conversation to handle the task.
    """
    agent: AgentRuntime | None = _state.get("agent")
    model_router: ModelRouter | None = _state.get("model_router")

    if not agent:
        raise RuntimeError("Agent not initialized")

    # Update status
    status = WorkerStatus(
        task_id=task.id,
        state=__import__("plutus.core.worker_pool", fromlist=["WorkerState"]).WorkerState.RUNNING,
        name=task.name,
        current_step="Processing task...",
    )
    if model_router and task.model_key:
        spec = model_router.route(task.prompt, model_override=task.model_key)
        status.model_used = spec.display_name
    await on_status(status)

    # Broadcast to UI
    await ws_manager.broadcast({
        "type": "worker_started",
        "worker": {"task_id": task.id, "name": task.name, "model": status.model_used},
    })

    # Process through the agent
    result_parts = []
    async for event in agent.process_message(
        f"[WORKER TASK: {task.name}]\n{task.prompt}",
    ):
        await ws_manager.broadcast(event.to_dict())
        if hasattr(event, "content") and event.content:
            result_parts.append(event.content)

    result = "\n".join(result_parts) if result_parts else "Task completed."

    await ws_manager.broadcast({
        "type": "worker_completed",
        "worker": {"task_id": task.id, "name": task.name, "result": result[:200]},
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
        f"Plutus v0.3.0 started — tier={config.guardrails.tier}, "
        f"model={config.model.provider}/{config.model.model}, "
        f"api_key={key_status}, computer_use={cu_status}, "
        f"heartbeat={heartbeat_status}, scheduler={scheduler_status}, "
        f"max_workers={config.workers.max_concurrent_workers}, "
        f"model_routing={'auto' if config.model_routing.auto_route else 'manual'}"
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
        description="Autonomous AI agent with multi-model routing, workers, and scheduling",
        version="0.3.1",
        lifespan=lifespan,
    )

    resolved_config = config or PlutusConfig.load()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_config.gateway.cors_origins + ["http://localhost:7777"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(create_router(), prefix="/api")
    app.include_router(create_ws_router())

    ui_dist = Path(__file__).parent.parent.parent / "ui" / "dist"
    if ui_dist.exists():
        app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="ui")

    return app
