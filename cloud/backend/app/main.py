import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api import agents, auth, bridge, chat, health, misc, workspace
from app.api.sync import router as sync_router
from app.api.ws import router as ws_router
from app.config import settings
from app.database import async_session_factory, close_db, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Start E2B sandbox cleanup loop (reaps idle per-user sandboxes)
    if settings.e2b_api_key:
        from app.services.e2b_manager import E2BSandboxManager

        await E2BSandboxManager.get_instance().start_cleanup_loop()
        logger.info("E2B sandbox manager started")
    # Auto-start connector bridge tasks for all users that had them running.
    # This ensures 24/7 availability even after pod restarts, without requiring
    # the user to open the web UI first.
    asyncio.create_task(_autostart_connectors())
    asyncio.create_task(_autostart_heartbeats())
    logger.info("Plutus Cloud API started")
    yield
    await close_db()


async def _autostart_connectors() -> None:
    """On startup, re-launch connector bridge tasks for every user that
    previously had a connector running (listening=True in their credentials)."""
    # Small delay so the DB pool is fully warmed up before we hit it.
    await asyncio.sleep(2)
    try:
        from app.database import async_session_factory as sf
        from app.models.user import User
        from app.services.connector_service import is_running, start_connector

        async with sf() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()

        launched = 0
        for user in users:
            creds_map: dict = user.connector_credentials or {}
            for connector_name, creds in creds_map.items():
                if not isinstance(creds, dict):
                    continue
                if not creds.get("listening"):
                    continue
                if is_running(user.id, connector_name):
                    continue
                try:
                    asyncio.create_task(
                        start_connector(user.id, connector_name, creds, async_session_factory),
                        name=f"{connector_name}-startup-{user.id[:8]}",
                    )
                    launched += 1
                    logger.info(
                        f"[startup] Launched {connector_name} connector for user {user.id[:8]}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"[startup] Failed to launch {connector_name} for user {user.id[:8]}: {exc}"
                    )

        if launched:
            logger.info(f"[startup] Auto-started {launched} connector task(s)")
        else:
            logger.info("[startup] No connector tasks to auto-start")
    except Exception as exc:
        logger.error(f"[startup] _autostart_connectors failed: {exc}", exc_info=True)


async def _autostart_heartbeats() -> None:
    """On startup, re-start heartbeats for every user that had them enabled."""
    await asyncio.sleep(5)  # Wait for DB pool and connectors to warm up
    try:
        from app.database import async_session_factory as sf
        from app.models.user import User
        from app.services.cloud_heartbeat import CloudHeartbeatManager

        async with sf() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()

        mgr = CloudHeartbeatManager.get_instance()
        started = 0
        for user in users:
            hb_cfg: dict = (user.settings or {}).get("heartbeat", {})
            if not hb_cfg.get("enabled"):
                continue
            if mgr.is_running(user.id):
                continue
            try:
                await mgr.start(
                    user_id=user.id,
                    session_factory=sf,
                    interval_seconds=hb_cfg.get("interval_seconds", 300),
                    prompt=hb_cfg.get("prompt"),
                    quiet_hours_start=hb_cfg.get("quiet_hours_start"),
                    quiet_hours_end=hb_cfg.get("quiet_hours_end"),
                    max_consecutive=hb_cfg.get("max_consecutive", 5),
                )
                started += 1
                logger.info("[startup] Resumed heartbeat for user %s", user.id[:8])
            except Exception as exc:
                logger.warning(
                    "[startup] Failed to resume heartbeat for user %s: %s", user.id[:8], exc
                )

        if started:
            logger.info("[startup] Auto-started %d heartbeat(s)", started)
        else:
            logger.info("[startup] No heartbeats to auto-start")
    except Exception as exc:
        logger.error("[startup] _autostart_heartbeats failed: %s", exc, exc_info=True)


app = FastAPI(
    title="Plutus Cloud API",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Localhost origins regex — matches http://localhost:<any-port> and
# http://127.0.0.1:<any-port> so that local Plutus instances running on
# any port (default 7777, but user-configurable) can reach the cloud API.
_LOCALHOST_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


class _DynamicCORSMiddleware:
    """Pure ASGI middleware that extends the static CORS allow-list with a
    dynamic localhost pattern.

    Unlike BaseHTTPMiddleware, this implementation does NOT wrap the ASGI
    scope, so WebSocket upgrade requests pass through completely unmodified.
    Only HTTP requests with a matching localhost Origin header are intercepted
    to inject the correct CORS response headers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # WebSocket connections must never be intercepted — pass straight through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract the Origin header from the scope headers list.
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("latin-1")

        if not (origin and _LOCALHOST_ORIGIN_RE.match(origin)):
            # Not a localhost origin — let the standard middleware handle it.
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        if method == "OPTIONS":
            # Preflight — respond immediately without calling the inner app.
            cors_headers = [
                (b"access-control-allow-origin", origin.encode()),
                (b"access-control-allow-credentials", b"true"),
                (b"access-control-allow-methods", b"*"),
                (b"access-control-allow-headers", b"*"),
                (b"content-length", b"0"),
            ]
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": cors_headers,
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return

        # Non-preflight HTTP request — call the inner app but inject CORS
        # headers into the response before forwarding it to the client.
        cors_extra = [
            (b"access-control-allow-origin", origin.encode()),
            (b"access-control-allow-credentials", b"true"),
            (b"access-control-allow-methods", b"*"),
            (b"access-control-allow-headers", b"*"),
        ]

        async def send_with_cors(message: dict) -> None:
            if message["type"] == "http.response.start":
                # Merge our CORS headers into the response, avoiding duplicates.
                existing_names = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in cors_extra if k not in existing_names]
                message = {
                    **message,
                    "headers": list(message.get("headers", [])) + extra,
                }
            await send(message)

        await self.app(scope, receive, send_with_cors)


# Middleware is applied in reverse registration order (last added = outermost).
# _DynamicCORSMiddleware must be added AFTER CORSMiddleware so it runs first
# and can intercept localhost origins before the static middleware rejects them.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(_DynamicCORSMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(bridge.router, prefix="/api/bridge", tags=["bridge"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(sync_router, prefix="/api/sync", tags=["sync"])
app.include_router(ws_router, tags=["websocket"])
app.include_router(misc.router, prefix="/api", tags=["misc"])
app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])
