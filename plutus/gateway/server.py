"""Main FastAPI application — serves the API and static UI files.

Plutus operates in two modes:
  1. Standard mode (PRIMARY): LLM + function-calling tools with accessibility tree
     snapshots for web and desktop interaction. Handles ALL messages by default.
  2. Computer Use mode (EXPLICIT ONLY): Anthropic's native Computer Use Tool
     (screenshot-based vision). Only activated when user explicitly requests it.

Both modes are available simultaneously. The Standard agent is always preferred
because it uses accessibility tree snapshots (fast, precise, token-efficient)
instead of screenshots (slow, imprecise, token-heavy).
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
from plutus.gateway.routes import create_router
from plutus.gateway.ws import create_ws_router, manager as ws_manager
from plutus.guardrails.engine import GuardrailEngine
from plutus.tools.registry import create_default_registry

logger = logging.getLogger("plutus.gateway")

# Shared application state
_state: dict[str, Any] = {}


def get_state() -> dict[str, Any]:
    return _state


async def _heartbeat_on_beat(prompt: str) -> None:
    """Called by the heartbeat runner — sends a synthetic message through the agent."""
    agent: AgentRuntime | None = _state.get("agent")
    if not agent:
        return

    async for event in agent.process_message(prompt):
        await ws_manager.broadcast(event.to_dict())


async def _heartbeat_on_event(event_data: dict[str, Any]) -> None:
    """Forward heartbeat lifecycle events (beat, paused, etc.) to the UI."""
    await ws_manager.broadcast(event_data)


def _init_computer_use_agent(config: PlutusConfig, secrets: SecretsStore) -> Any:
    """Initialize the Anthropic Computer Use agent if possible.

    Returns the ComputerUseAgent instance or None if not available.
    """
    try:
        from plutus.core.computer_use_agent import ComputerUseAgent
        from plutus.pc.computer_use import ComputerUseExecutor

        # Get the Anthropic API key
        api_key = secrets.get_key("anthropic")
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not api_key:
            logger.warning("No Anthropic API key found — Computer Use agent disabled")
            return None

        # Determine the model to use for computer use
        # Claude Sonnet 4 is recommended for computer use
        cu_model = config.model.model
        if config.model.provider == "anthropic":
            # Use the configured model
            pass
        else:
            # Default to Claude Sonnet for computer use
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


async def _auto_start_connectors(connector_manager) -> None:
    """Auto-start connectors that have auto_start enabled in their config."""
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    config = PlutusConfig.load()

    # Initialize secrets store and inject stored keys into environment
    secrets = SecretsStore()
    secrets.inject_all()

    # Initialize memory
    memory = MemoryStore(config.resolve_memory_db())
    await memory.initialize()

    # Initialize guardrails
    guardrails = GuardrailEngine(config)

    # Initialize tool registry
    tool_registry = create_default_registry()

    # Initialize standard agent (LiteLLM + function calling)
    agent = AgentRuntime(
        config=config,
        guardrails=guardrails,
        memory=memory,
        tool_registry=tool_registry,
        secrets=secrets,
    )
    await agent.initialize()

    # Register the memory tool (needs memory store + conversation manager)
    from plutus.tools.memory_tool import MemoryTool
    memory_tool = MemoryTool(memory, agent.conversation)
    tool_registry.register(memory_tool)

    # Initialize Computer Use agent (Anthropic native)
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

    _state["config"] = config
    _state["secrets"] = secrets
    _state["memory"] = memory
    _state["guardrails"] = guardrails
    _state["tool_registry"] = tool_registry
    _state["agent"] = agent
    _state["cu_agent"] = cu_agent
    _state["heartbeat"] = heartbeat
    _state["connector_manager"] = connector_manager

    key_status = "configured" if agent.key_configured else "NOT configured"
    cu_status = "enabled" if cu_agent else "disabled"
    heartbeat_status = "enabled" if config.heartbeat.enabled else "disabled"
    logger.info(
        f"Plutus started — tier={config.guardrails.tier}, "
        f"model={config.model.provider}/{config.model.model}, "
        f"api_key={key_status}, computer_use={cu_status}, heartbeat={heartbeat_status}"
    )

    # Auto-start connectors that have auto_start enabled (e.g. Telegram bridge)
    await _auto_start_connectors(connector_manager)

    yield

    heartbeat.stop()
    await connector_manager.stop_all()
    await agent.shutdown()
    logger.info("Plutus shut down")


def create_app(config: PlutusConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Plutus",
        description="Autonomous AI agent with computer use and configurable guardrails",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS for local development
    resolved_config = config or PlutusConfig.load()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_config.gateway.cors_origins + ["http://localhost:7777"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(create_router(), prefix="/api")
    app.include_router(create_ws_router())

    # Serve built UI static files if they exist
    ui_dist = Path(__file__).parent.parent.parent / "ui" / "dist"
    if ui_dist.exists():
        app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="ui")

    return app
