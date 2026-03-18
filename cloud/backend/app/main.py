from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, close_db
from app.api import auth, chat, agents, bridge, health
from app.api.sync import router as sync_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Plutus Cloud API started")
    yield
    await close_db()


app = FastAPI(
    title="Plutus Cloud API",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,   prefix="/api/auth",   tags=["auth"])
app.include_router(chat.router,   prefix="/api/chat",   tags=["chat"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(bridge.router, prefix="/api/bridge", tags=["bridge"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(sync_router,   prefix="/api/sync",   tags=["sync"])
