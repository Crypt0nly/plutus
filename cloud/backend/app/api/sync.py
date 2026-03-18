"""
Sync API router — exposes push / pull / status / conflict-resolution
endpoints for the Plutus bridge sync client.

All responses use typed Pydantic models.  Rate-limiting headers are
attached to every response via middleware.  Error responses carry
structured JSON bodies with ``detail`` and ``error_code`` keys.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_session
from app.sync.sync_service import (
    ENTITY_MAP,
    BatchProcessingError,
    EntityNotFoundError,
    SyncError,
    SyncService,
    VersionGapError,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class SyncPayloadItem(BaseModel):
    """A single change payload sent by the bridge ``sync_client.py``."""

    table: str = Field(
        ...,
        description="Entity type key — must be one of the ENTITY_MAP keys.",
        examples=["memory", "skill", "scheduled_task"],
    )
    operation: str = Field(
        ...,
        description="The mutation type.",
        pattern=r"^(insert|update|delete|create)$",
        examples=["insert", "update", "delete"],
    )
    record_id: str = Field(
        ...,
        description="Primary key of the entity being synced.",
    )
    data: dict[str, Any] | None = Field(
        default=None,
        description="Column data for insert/update; may be null for deletes.",
    )
    client_version: int = Field(
        ...,
        ge=0,
        description="The sync_version the client believes it is at.",
    )

    @field_validator("table")
    @classmethod
    def validate_table(cls, v: str) -> str:
        if v not in ENTITY_MAP:
            raise ValueError(
                f"Unknown entity type {v!r}. Must be one of: {', '.join(sorted(ENTITY_MAP))}"
            )
        return v

    @field_validator("operation")
    @classmethod
    def normalise_operation(cls, v: str) -> str:
        """Map ``insert`` → ``create`` so the service always sees CRUD verbs."""
        return "create" if v == "insert" else v


class PushRequest(BaseModel):
    """Body for ``POST /sync/push``."""

    payloads: list[SyncPayloadItem] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Batch of change payloads (1–500).",
    )


class ConflictDetail(BaseModel):
    """Serialised representation of a detected sync conflict."""

    entity_type: str
    entity_id: str
    local_data: dict[str, Any]
    cloud_data: dict[str, Any]
    local_timestamp: str
    cloud_timestamp: str
    resolution: str


class PushResponse(BaseModel):
    """Response for ``POST /sync/push``."""

    accepted: int = Field(description="Number of payloads successfully applied.")
    skipped: int = Field(description="Number of payloads skipped (conflicts / unknown).")
    conflicts: list[ConflictDetail] = Field(
        default_factory=list,
        description="Conflicts detected during the push.",
    )
    server_version: int = Field(description="Server sync version after the push.")


class ChangeItem(BaseModel):
    """A single change entry returned by the pull endpoint."""

    version: int
    entity_type: str
    entity_id: str
    action: str
    data: dict[str, Any]
    timestamp: str | None = None


class PullResponse(BaseModel):
    """Response for ``GET /sync/pull``."""

    changes: list[ChangeItem]
    server_version: int
    has_more: bool = Field(
        description="True if there are more changes beyond this page.",
    )
    total: int = Field(description="Total number of changes matching the query.")


class StatusResponse(BaseModel):
    """Response for ``GET /sync/status``."""

    server_version: int
    user_id: str
    last_sync_time: str | None = Field(
        description="ISO-8601 timestamp of the most recent sync log entry.",
    )
    pending_changes_count: int = Field(
        description="Number of cloud-sourced changes awaiting local acknowledgement.",
    )
    entity_counts: dict[str, int] = Field(
        description="Per-entity-type row counts for this user.",
    )


class ResolveConflictRequest(BaseModel):
    """Body for ``POST /sync/resolve-conflict``."""

    entity_type: str = Field(..., description="Entity type key.")
    entity_id: str = Field(..., description="Primary key of the entity.")
    winning_data: dict[str, Any] = Field(
        ...,
        description="The data snapshot that should be written as the winner.",
    )
    resolution: str = Field(
        ...,
        description=(
            "Label for the resolution (e.g. 'manual_local', 'manual_cloud', 'manual_merge')."
        ),
        examples=["manual_local", "manual_cloud", "manual_merge"],
    )

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in ENTITY_MAP:
            raise ValueError(
                f"Unknown entity type {v!r}. Must be one of: {', '.join(sorted(ENTITY_MAP))}"
            )
        return v


class ResolveConflictResponse(BaseModel):
    """Response for ``POST /sync/resolve-conflict``."""

    resolved: bool = True
    entity_type: str
    entity_id: str
    resolution: str
    server_version: int


class ErrorResponse(BaseModel):
    """Standard error body."""

    detail: str
    error_code: str
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rate-limiting helper
# ---------------------------------------------------------------------------

# Simple per-response rate-limit headers.  A production deployment would
# use a Redis-backed sliding window, but these headers let clients know
# the *intended* contract.
_RATE_LIMIT = 120  # requests per window
_RATE_LIMIT_WINDOW = 60  # seconds


def _attach_rate_limit_headers(response: Response) -> None:
    """Attach ``X-RateLimit-*`` headers to *response*."""
    response.headers["X-RateLimit-Limit"] = str(_RATE_LIMIT)
    response.headers["X-RateLimit-Remaining"] = str(_RATE_LIMIT)  # placeholder
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + _RATE_LIMIT_WINDOW)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/push",
    response_model=PushResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid payload or unknown entity type."},
        409: {"model": ErrorResponse, "description": "Version gap — full sync required."},
        500: {"model": ErrorResponse, "description": "Batch processing failed."},
    },
    summary="Push local changes to cloud",
    description=(
        "Accept a batch of change payloads from the bridge sync client and "
        "apply them atomically to the cloud Postgres database.  Conflicts "
        "are auto-resolved using last-write-wins."
    ),
)
async def push(
    body: PushRequest,
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PushResponse:
    _attach_rate_limit_headers(response)
    service = SyncService(session)
    user_id: str = current_user["user_id"]

    try:
        result = await service.apply_changes(
            user_id=user_id,
            payloads=[p.model_dump() for p in body.payloads],
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail=exc.message,
        ) from exc
    except VersionGapError as exc:
        raise HTTPException(
            status_code=409,
            detail=exc.message,
        ) from exc
    except BatchProcessingError as exc:
        raise HTTPException(
            status_code=500,
            detail=exc.message,
        ) from exc
    except SyncError as exc:
        raise HTTPException(
            status_code=500,
            detail=exc.message,
        ) from exc

    return PushResponse(
        accepted=result.applied,
        skipped=result.skipped,
        conflicts=[
            ConflictDetail(
                entity_type=c.entity_type,
                entity_id=c.entity_id,
                local_data=c.local_data,
                cloud_data=c.cloud_data,
                local_timestamp=c.local_timestamp.isoformat(),
                cloud_timestamp=c.cloud_timestamp.isoformat(),
                resolution=c.resolution,
            )
            for c in result.conflicts
        ],
        server_version=result.server_version,
    )


@router.get(
    "/pull",
    response_model=PullResponse,
    responses={
        409: {"model": ErrorResponse, "description": "Version gap — full sync required."},
    },
    summary="Pull cloud changes to local",
    description=(
        "Return a paginated list of changes for the authenticated user "
        "since the given ``since_version``."
    ),
)
async def pull(
    response: Response,
    since_version: int = Query(
        0,
        ge=0,
        description="Return changes with sync_version strictly greater than this.",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum number of changes to return.",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of qualifying changes to skip (pagination).",
    ),
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PullResponse:
    _attach_rate_limit_headers(response)
    service = SyncService(session)
    user_id: str = current_user["user_id"]

    try:
        result = await service.get_changes(
            user_id=user_id,
            since_version=since_version,
            limit=limit,
            offset=offset,
        )
    except VersionGapError as exc:
        raise HTTPException(
            status_code=409,
            detail=exc.message,
        ) from exc

    return PullResponse(
        changes=[ChangeItem(**c) for c in result.changes],
        server_version=result.server_version,
        has_more=result.has_more,
        total=result.total,
    )


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Sync health status",
    description=(
        "Return sync health information for the authenticated user: "
        "current server version, last sync time, pending change count, "
        "and per-entity row counts."
    ),
)
async def status(
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StatusResponse:
    _attach_rate_limit_headers(response)
    service = SyncService(session)
    user_id: str = current_user["user_id"]

    info = await service.get_sync_status(user_id)

    return StatusResponse(
        server_version=info["server_version"],
        user_id=user_id,
        last_sync_time=info["last_sync_time"],
        pending_changes_count=info["pending_changes_count"],
        entity_counts=info["entity_counts"],
    )


@router.post(
    "/resolve-conflict",
    response_model=ResolveConflictResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Unknown entity type."},
        404: {"model": ErrorResponse, "description": "Entity not found."},
        500: {"model": ErrorResponse, "description": "Resolution failed."},
    },
    summary="Manually resolve a sync conflict",
    description=(
        "Write *winning_data* to the specified entity row, record the "
        "resolution in the sync log, and return the new server version."
    ),
)
async def resolve_conflict(
    body: ResolveConflictRequest,
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ResolveConflictResponse:
    _attach_rate_limit_headers(response)
    service = SyncService(session)
    user_id: str = current_user["user_id"]

    try:
        new_version = await service.resolve_conflict_manual(
            user_id=user_id,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            winning_data=body.winning_data,
            resolution=body.resolution,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except SyncError as exc:
        # Entity row not found → 404; other sync errors → 500
        status_code = 404 if "not found" in exc.message.lower() else 500
        raise HTTPException(status_code=status_code, detail=exc.message) from exc

    return ResolveConflictResponse(
        resolved=True,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        resolution=body.resolution,
        server_version=new_version,
    )
