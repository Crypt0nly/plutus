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

import asyncio
import logging
import os
import time
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

async def _worker_executor(task: WorkerTask, on_status: Any, *, deadline: float | None = None) -> str:
    """Execute a worker task with an independent multi-turn agent loop.

    Workers have access to ALL tools from the registry and can make multiple
    LLM calls in a loop (just like the coordinator), but they:
      - Have their OWN conversation context (no pollution)
      - Run independently (no self-await deadlocks)
      - Bypass guardrails (the coordinator already approved the spawn)
      - Have a max of 15 tool rounds to prevent runaway workers
    """
    import json as _json
    import litellm

    model_router: ModelRouter | None = _state.get("model_router")
    tool_registry = _state.get("tool_registry")

    # Select model for this worker
    model_string = "anthropic/claude-sonnet-4-6"  # fallback
    model_display = "Claude Sonnet 4-6"

    if model_router:
        spec = model_router.select_for_worker(task.prompt, model_key=task.model_key)
        model_string = model_router.get_litellm_model_string(spec)
        model_display = spec.display_name
        # Record usage
        try:
            from plutus.core.model_router import AVAILABLE_MODELS
            for key, s in AVAILABLE_MODELS.items():
                if s.id == spec.id:
                    model_router.record_usage(key)
                    break
        except Exception:
            pass

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

    # Build tool definitions from the registry (exclude 'worker' to prevent recursion)
    tools_for_llm = []
    if tool_registry:
        for tool in tool_registry._tools.values():
            if tool.name == "worker":  # prevent workers from spawning workers
                continue
            try:
                defn = tool.get_definition()
                tools_for_llm.append({
                    "type": "function",
                    "function": {
                        "name": defn.name,
                        "description": defn.description,
                        "parameters": defn.parameters,
                    },
                })
            except Exception:
                pass

    # Worker system prompt
    worker_system_prompt = (
        "You are a Plutus worker agent. You have been assigned a specific task by the "
        "coordinator. You have access to tools (shell, filesystem, browser, pc control, etc.) "
        "to complete your task. Complete the task thoroughly and return your result. "
        "Be concise but comprehensive. Do not ask follow-up questions — just do the work.\n\n"
        "When you are done, respond with your final result as plain text (no tool calls)."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": worker_system_prompt},
        {"role": "user", "content": task.prompt},
    ]

    MAX_WORKER_ROUNDS = 15
    result = "Task completed (no output)."
    final_texts: list[str] = []
    errored = False
    timed_out = False

    try:
        for round_num in range(MAX_WORKER_ROUNDS):
            # Check deadline BEFORE each round
            if deadline and time.time() >= deadline:
                remaining_text = "\n".join(final_texts) if final_texts else ""
                if remaining_text:
                    result = remaining_text + "\n\n[Worker timed out — partial result above]"
                else:
                    result = f"[Worker timed out after {task.timeout}s]"
                timed_out = True
                logger.warning(f"Worker {task.id} hit deadline at round {round_num + 1}")
                break

            status.current_step = f"Round {round_num + 1}/{MAX_WORKER_ROUNDS} — {model_display}"
            status.progress_pct = min(95.0, (round_num / MAX_WORKER_ROUNDS) * 100)
            try:
                await on_status(status)
            except Exception:
                pass

            call_kwargs: dict[str, Any] = {
                "model": model_string,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4096,
            }
            if tools_for_llm:
                call_kwargs["tools"] = tools_for_llm

            # LLM call with retry logic — litellm/httpx can raise CancelledError
            # on transient connection issues, so we retry up to 2 times
            response = None
            for attempt in range(3):
                try:
                    response = await litellm.acompletion(**call_kwargs)
                    break  # success
                except asyncio.CancelledError:
                    # Check if this is a real cancellation (from pool.cancel)
                    # or a transient error from httpx/aiohttp
                    current_task = asyncio.current_task()
                    if current_task and current_task.cancelled():
                        # Real cancellation — propagate
                        logger.info(f"Worker {task.id} truly cancelled on round {round_num + 1}")
                        raise
                    # Transient CancelledError from HTTP client — retry
                    logger.warning(f"Worker {task.id} got transient CancelledError on round {round_num + 1}, attempt {attempt + 1}/3")
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (attempt + 1))  # backoff
                        continue
                    else:
                        logger.error(f"Worker {task.id} CancelledError persisted after 3 attempts")
                        result = f"[Worker Error] LLM call cancelled after 3 retries"
                        errored = True
                        break
                except Exception as llm_err:
                    logger.error(f"Worker {task.id} LLM call failed on round {round_num + 1}, attempt {attempt + 1}: {llm_err}")
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    else:
                        result = f"[Worker Error] LLM call failed after 3 retries: {llm_err}"
                        errored = True
                        break

            if errored or response is None:
                if not errored:
                    result = "[Worker Error] LLM call returned no response"
                    errored = True
                break

            choice = response.choices[0]
            msg = choice.message

            # Collect any text content
            if msg.content:
                final_texts.append(msg.content)

            # If no tool calls, we're done
            if not msg.tool_calls:
                break

            # Append the assistant message with tool calls
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if msg.content:
                assistant_msg["content"] = msg.content
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments if isinstance(tc.function.arguments, str) else _json.dumps(tc.function.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args_raw = tc.function.arguments
                    args = _json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except Exception:
                    args = {}

                status.current_step = f"Using tool: {tool_name}"
                try:
                    await on_status(status)
                except Exception:
                    pass

                tool_result = "[ERROR] Tool not found"
                if tool_registry:
                    tool_obj = tool_registry.get(tool_name)
                    if tool_obj and tool_name != "worker":
                        try:
                            tool_result = str(await tool_obj.execute(**args))
                        except asyncio.CancelledError:
                            # Check if real cancellation
                            current_task = asyncio.current_task()
                            if current_task and current_task.cancelled():
                                raise
                            tool_result = "[ERROR] Tool execution was interrupted, please retry"
                            logger.warning(f"Worker {task.id} tool {tool_name} got transient CancelledError")
                        except Exception as e:
                            tool_result = f"[ERROR] {e}"

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result[:8000],  # cap to avoid context overflow
                })

        # Assemble final result from all text outputs (unless we already set an error)
        if not errored:
            result = "\n".join(final_texts) if final_texts else "Task completed (no output)."

        # Update status
        status.current_step = "Done"
        status.steps_completed = 1
        status.progress_pct = 100.0
        try:
            await on_status(status)
        except Exception:
            pass

    except Exception as e:
        # Catch all non-cancellation errors. CancelledError is NOT caught here
        # (it's a BaseException in Python 3.9+) so it propagates to _run_worker.
        result = f"[Worker Error] {e}"
        logger.exception(f"Worker {task.id} failed: {e}")

    # Broadcast results to UI and coordinator.
    # Use asyncio.shield to protect broadcasts from cancellation.
    async def _broadcast_results() -> None:
        try:
            # Broadcast completion status to workers panel
            await ws_manager.broadcast({
                "type": "worker_completed",
                "worker": {
                    "task_id": task.id,
                    "name": task.name,
                    "result": result[:500],
                    "state": "timed_out" if timed_out else ("failed" if result.startswith("[Worker Error]") else "completed"),
                },
            })

            # Broadcast the full result to the chat — this is what the user sees
            await ws_manager.broadcast({
                "type": "worker_result",
                "task_id": task.id,
                "name": task.name,
                "model": model_display,
                "result": result,
                "duration": 0.0,
            })

            # Inject the result into the coordinator's conversation context
            # so Plutus can see what the workers produced
            agent: AgentRuntime | None = _state.get("agent")
            if agent and hasattr(agent, 'conversation') and agent.conversation.conversation_id:
                worker_context_msg = (
                    f"[Worker Result — {task.name} ({model_display})]\n"
                    f"{result}"
                )
                await agent.conversation.add_assistant_message(content=worker_context_msg)
        except Exception as broadcast_err:
            logger.error(f"Worker {task.id} failed to broadcast results: {broadcast_err}")

    try:
        await asyncio.shield(_broadcast_results())
    except asyncio.CancelledError:
        # Shield was cancelled but the inner task continues
        # Try one more time synchronously-ish
        try:
            await _broadcast_results()
        except Exception:
            logger.error(f"Worker {task.id}: final broadcast attempt failed")

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
