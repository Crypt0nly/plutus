"""
Sync engine: Cloud Postgres ↔ Local SQLite
Strategy: last-write-wins with monotonic version counter per user.

Cloud Postgres is the authoritative source of truth. Each entity carries a
monotonically increasing ``sync_version`` scoped to a user. The bridge
``sync_client.py`` sends payloads with ``table``, ``operation``,
``record_id``, ``data``, and ``client_version``.

All write operations are atomic — a batch either fully commits or fully
rolls back.  Conflicts are detected, logged, and resolved via LWW; callers
may also invoke manual resolution through the API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select, func, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_state import Memory, Skill, ScheduledTask
from app.models.sync_log import SyncLog
from shared.models.sync import SyncConflict, SyncPayload

logger = logging.getLogger("plutus.sync")

# ---------------------------------------------------------------------------
# Entity registry
# ---------------------------------------------------------------------------
ENTITY_MAP: dict[str, type] = {
    "memory": Memory,
    "skill": Skill,
    "scheduled_task": ScheduledTask,
}

# If a client is more than MAX_VERSION_GAP versions behind the server, we
# force a full sync instead of an incremental pull.
MAX_VERSION_GAP: int = 500


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class SyncError(Exception):
    """Base exception for all sync-engine errors."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EntityNotFoundError(SyncError):
    """Raised when a referenced entity type is not in ENTITY_MAP."""


class VersionGapError(SyncError):
    """Raised when the client is too far behind and must do a full sync."""

    def __init__(self, client_version: int, server_version: int) -> None:
        super().__init__(
            f"Client version {client_version} is too far behind server "
            f"version {server_version} (gap > {MAX_VERSION_GAP}). "
            "A full sync is required.",
            details={
                "client_version": client_version,
                "server_version": server_version,
                "max_gap": MAX_VERSION_GAP,
            },
        )
        self.client_version = client_version
        self.server_version = server_version


class ConflictError(SyncError):
    """Raised when a write conflict is detected and cannot be auto-resolved."""

    def __init__(self, conflict: SyncConflict) -> None:
        super().__init__(
            f"Unresolved conflict on {conflict.entity_type}/{conflict.entity_id}",
            details={
                "entity_type": conflict.entity_type,
                "entity_id": conflict.entity_id,
                "resolution": conflict.resolution,
            },
        )
        self.conflict = conflict


class BatchProcessingError(SyncError):
    """Raised when a batch push fails partway through (the txn is rolled back)."""

    def __init__(self, index: int, original: Exception) -> None:
        super().__init__(
            f"Batch processing failed at payload index {index}: {original}",
            details={"index": index, "original_error": str(original)},
        )
        self.index = index
        self.original = original


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

class PushResult:
    """Structured result returned by :meth:`SyncService.push_changes`."""

    __slots__ = ("applied", "skipped", "conflicts", "server_version")

    def __init__(self) -> None:
        self.applied: int = 0
        self.skipped: int = 0
        self.conflicts: list[SyncConflict] = []
        self.server_version: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise for API responses."""
        return {
            "applied": self.applied,
            "skipped": self.skipped,
            "conflicts": [
                {
                    "entity_type": c.entity_type,
                    "entity_id": c.entity_id,
                    "local_data": c.local_data,
                    "cloud_data": c.cloud_data,
                    "local_timestamp": c.local_timestamp.isoformat(),
                    "cloud_timestamp": c.cloud_timestamp.isoformat(),
                    "resolution": c.resolution,
                }
                for c in self.conflicts
            ],
            "server_version": self.server_version,
        }


class PullResult:
    """Structured result returned by :meth:`SyncService.pull_changes`."""

    __slots__ = ("changes", "server_version", "has_more", "total")

    def __init__(self) -> None:
        self.changes: list[dict[str, Any]] = []
        self.server_version: int = 0
        self.has_more: bool = False
        self.total: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise for API responses."""
        return {
            "changes": self.changes,
            "server_version": self.server_version,
            "has_more": self.has_more,
            "total": self.total,
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SyncService:
    """Manages bidirectional sync between local SQLite and cloud Postgres.

    All public methods that mutate state run inside a single transaction so
    that either *every* change in a batch is applied or *none* are.

    Parameters
    ----------
    session:
        An async SQLAlchemy session — typically injected by FastAPI's
        ``Depends(get_session)`` dependency.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Push  (local → cloud)
    # ------------------------------------------------------------------

    async def push_changes(
        self,
        user_id: str,
        changes: list[SyncPayload],
    ) -> PushResult:
        """Apply a batch of local changes to the cloud database atomically.

        Every change in *changes* is validated, conflict-checked, and applied
        inside a single database transaction.  If any individual change fails,
        the entire batch is rolled back and a :class:`BatchProcessingError` is
        raised.

        Parameters
        ----------
        user_id:
            The owning user's ID (from the JWT).
        changes:
            Ordered list of :class:`SyncPayload` objects from the client.

        Returns
        -------
        PushResult
            Counts of applied/skipped changes, any detected conflicts, and
            the new ``server_version``.

        Raises
        ------
        EntityNotFoundError
            If a payload references an unknown entity type.
        BatchProcessingError
            If an unexpected DB error occurs mid-batch (txn rolled back).
        """
        result = PushResult()

        try:
            async with self.session.begin_nested():
                for idx, change in enumerate(changes):
                    try:
                        applied = await self._apply_single_change(
                            user_id, change, result,
                        )
                        if applied:
                            result.applied += 1
                        else:
                            result.skipped += 1
                    except (EntityNotFoundError, ConflictError):
                        # Already recorded in result.conflicts / logged
                        result.skipped += 1
                    except SQLAlchemyError as exc:
                        logger.exception(
                            "DB error at batch index %d for user %s",
                            idx, user_id,
                        )
                        raise BatchProcessingError(idx, exc) from exc

            # Commit the outer transaction
            await self.session.commit()

        except BatchProcessingError:
            await self.session.rollback()
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Transaction commit failed for user %s", user_id)
            raise SyncError(
                "Failed to commit sync batch",
                details={"user_id": user_id, "error": str(exc)},
            ) from exc

        result.server_version = await self.get_version(user_id)
        return result

    # ------------------------------------------------------------------
    # Pull  (cloud → local)
    # ------------------------------------------------------------------

    async def pull_changes(
        self,
        user_id: str,
        since_version: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PullResult:
        """Return changes for *user_id* since *since_version*, paginated.

        Parameters
        ----------
        user_id:
            The owning user's ID.
        since_version:
            The last ``sync_version`` the client has seen.  Only rows with a
            strictly greater version are returned.
        limit:
            Maximum number of change rows to return (default 100).
        offset:
            Number of qualifying rows to skip (for pagination).

        Returns
        -------
        PullResult
            A page of change dicts plus ``server_version``, ``has_more``,
            and ``total`` count.

        Raises
        ------
        VersionGapError
            If ``server_version - since_version > MAX_VERSION_GAP``.
        """
        result = PullResult()
        result.server_version = await self.get_version(user_id)

        # Detect version gap — force full sync
        gap = result.server_version - since_version
        if gap > MAX_VERSION_GAP:
            raise VersionGapError(since_version, result.server_version)

        # Total qualifying rows
        count_q = (
            select(func.count())
            .select_from(SyncLog)
            .where(
                and_(
                    SyncLog.user_id == user_id,
                    SyncLog.sync_version > since_version,
                )
            )
        )
        result.total = (await self.session.execute(count_q)).scalar() or 0

        # Fetch page
        rows_q = (
            select(SyncLog)
            .where(
                and_(
                    SyncLog.user_id == user_id,
                    SyncLog.sync_version > since_version,
                )
            )
            .order_by(SyncLog.sync_version)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(rows_q)).scalars().all()

        result.changes = [self._log_row_to_dict(row) for row in rows]
        result.has_more = (offset + len(rows)) < result.total
        return result

    # ------------------------------------------------------------------
    # Convenience wrappers used by the API router
    # ------------------------------------------------------------------

    async def apply_changes(
        self,
        user_id: str,
        payloads: list[dict[str, Any]],
    ) -> PushResult:
        """Convert raw dicts (from the bridge) to :class:`SyncPayload` and push.

        The bridge ``sync_client.py`` sends payloads shaped as::

            {
                "table": "memory",
                "operation": "update",
                "record_id": "abc-123",
                "data": { ... },
                "client_version": 42
            }

        Parameters
        ----------
        user_id:
            The owning user's ID.
        payloads:
            Raw dicts from the client bridge.

        Returns
        -------
        PushResult
            The result of :meth:`push_changes`.
        """
        changes: list[SyncPayload] = []
        for p in payloads:
            changes.append(
                SyncPayload(
                    entity_type=p["table"],
                    entity_id=p["record_id"],
                    user_id=user_id,
                    action=p["operation"],
                    data=p.get("data") or {},
                    timestamp=datetime.now(timezone.utc),
                    source="local",
                    sync_version=p.get("client_version", 0),
                )
            )
        return await self.push_changes(user_id, changes)

    async def get_changes(
        self,
        user_id: str,
        since_version: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PullResult:
        """Pull changes with pagination and return a :class:`PullResult`.

        Parameters
        ----------
        user_id:
            The owning user's ID.
        since_version:
            Minimum exclusive sync version.
        limit:
            Page size.
        offset:
            Page offset.

        Returns
        -------
        PullResult
        """
        return await self.pull_changes(
            user_id, since_version, limit=limit, offset=offset,
        )

    async def get_version(self, user_id: str) -> int:
        """Return the latest ``sync_version`` for *user_id*, or ``0``."""
        result = await self.session.execute(
            select(func.coalesce(func.max(SyncLog.sync_version), 0)).where(
                SyncLog.user_id == user_id,
            )
        )
        return result.scalar() or 0

    # ------------------------------------------------------------------
    # Sync status / health
    # ------------------------------------------------------------------

    async def get_sync_status(self, user_id: str) -> dict[str, Any]:
        """Return sync health info for *user_id*.

        Returns
        -------
        dict
            Keys: ``server_version``, ``last_sync_time``,
            ``pending_changes_count``, ``entity_counts``.
        """
        server_version = await self.get_version(user_id)

        # Last sync timestamp
        last_sync_q = (
            select(SyncLog.created_at)
            .where(SyncLog.user_id == user_id)
            .order_by(SyncLog.sync_version.desc())
            .limit(1)
        )
        last_sync_row = (await self.session.execute(last_sync_q)).scalar_one_or_none()

        # Pending (unsynced-to-local) changes — entries sourced from cloud
        # that haven't been acknowledged.  We approximate by counting
        # cloud-sourced entries in the last 24 h.
        pending_q = (
            select(func.count())
            .select_from(SyncLog)
            .where(
                and_(
                    SyncLog.user_id == user_id,
                    SyncLog.source == "cloud",
                )
            )
        )
        pending_count: int = (await self.session.execute(pending_q)).scalar() or 0

        # Per-entity-type counts
        entity_counts: dict[str, int] = {}
        for entity_name, model in ENTITY_MAP.items():
            cnt_q = (
                select(func.count())
                .select_from(model)
                .where(model.user_id == user_id)  # type: ignore[attr-defined]
            )
            entity_counts[entity_name] = (await self.session.execute(cnt_q)).scalar() or 0

        return {
            "server_version": server_version,
            "last_sync_time": last_sync_row.isoformat() if last_sync_row else None,
            "pending_changes_count": pending_count,
            "entity_counts": entity_counts,
        }

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    async def resolve_conflict(self, conflict: SyncConflict) -> SyncConflict:
        """Auto-resolve a conflict using the last-write-wins strategy.

        Parameters
        ----------
        conflict:
            An unresolved :class:`SyncConflict`.

        Returns
        -------
        SyncConflict
            The same object with ``resolution`` set to ``local_wins`` or
            ``cloud_wins``.
        """
        resolved = conflict.resolve_last_write_wins()
        logger.info(
            "Auto-resolved conflict %s/%s → %s",
            resolved.entity_type,
            resolved.entity_id,
            resolved.resolution,
        )
        return resolved

    async def resolve_conflict_manual(
        self,
        user_id: str,
        entity_type: str,
        entity_id: str,
        winning_data: dict[str, Any],
        resolution: str,
    ) -> int:
        """Manually resolve a conflict by writing *winning_data* to the entity.

        Parameters
        ----------
        user_id:
            The owning user's ID.
        entity_type:
            Key in :data:`ENTITY_MAP`.
        entity_id:
            Primary key of the entity row.
        winning_data:
            The data that should win.
        resolution:
            A human-readable label for the audit log (e.g. ``"manual_local"``).

        Returns
        -------
        int
            The new ``server_version`` after the resolution is recorded.

        Raises
        ------
        EntityNotFoundError
            If *entity_type* is not in :data:`ENTITY_MAP`.
        SyncError
            If the entity row does not exist.
        """
        model = ENTITY_MAP.get(entity_type)
        if model is None:
            raise EntityNotFoundError(
                f"Unknown entity type: {entity_type!r}",
                details={"entity_type": entity_type},
            )

        try:
            async with self.session.begin_nested():
                row = (
                    await self.session.execute(
                        select(model).where(
                            and_(
                                model.id == entity_id,  # type: ignore[attr-defined]
                                model.user_id == user_id,  # type: ignore[attr-defined]
                            )
                        )
                    )
                ).scalar_one_or_none()

                if row is None:
                    raise SyncError(
                        f"Entity {entity_type}/{entity_id} not found for user",
                        details={
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "user_id": user_id,
                        },
                    )

                for key, value in winning_data.items():
                    if hasattr(row, key):
                        setattr(row, key, value)

                await self._record_change(
                    user_id,
                    entity_type,
                    entity_id,
                    action=f"conflict_resolve:{resolution}",
                    data=winning_data,
                )

            await self.session.commit()
        except SyncError:
            await self.session.rollback()
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(
                "Manual conflict resolution failed for %s/%s user %s",
                entity_type, entity_id, user_id,
            )
            raise SyncError(
                "Failed to resolve conflict",
                details={"error": str(exc)},
            ) from exc

        logger.info(
            "Manually resolved conflict %s/%s for user %s → %s",
            entity_type, entity_id, user_id, resolution,
        )
        return await self.get_version(user_id)

    # ------------------------------------------------------------------
    # Batch processing helpers
    # ------------------------------------------------------------------

    async def push_changes_batched(
        self,
        user_id: str,
        changes: list[SyncPayload],
        *,
        batch_size: int = 50,
    ) -> PushResult:
        """Push a large list of changes in smaller batches for efficiency.

        Each batch of *batch_size* payloads is committed independently.
        If a batch fails the remaining batches are **not** attempted.

        Parameters
        ----------
        user_id:
            The owning user's ID.
        changes:
            Full list of :class:`SyncPayload` objects.
        batch_size:
            Number of payloads per batch (default 50).

        Returns
        -------
        PushResult
            Aggregated result across all batches.
        """
        aggregated = PushResult()

        for start in range(0, len(changes), batch_size):
            batch = changes[start : start + batch_size]
            batch_result = await self.push_changes(user_id, batch)
            aggregated.applied += batch_result.applied
            aggregated.skipped += batch_result.skipped
            aggregated.conflicts.extend(batch_result.conflicts)

        aggregated.server_version = await self.get_version(user_id)
        return aggregated

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _apply_single_change(
        self,
        user_id: str,
        change: SyncPayload,
        result: PushResult,
    ) -> bool:
        """Apply one :class:`SyncPayload` and return ``True`` if applied.

        Conflict detection: if the existing row's ``updated_at`` is *newer*
        than the payload timestamp, a :class:`SyncConflict` is created,
        auto-resolved via LWW, and appended to *result.conflicts*.

        Returns ``False`` (skipped) when:
        * The entity type is unknown.
        * A delete targets a non-existent row.
        * The conflict resolves in favour of the cloud (server data wins).
        """
        model = ENTITY_MAP.get(change.entity_type)
        if model is None:
            logger.warning("Unknown entity type %r — skipping", change.entity_type)
            raise EntityNotFoundError(
                f"Unknown entity type: {change.entity_type!r}",
                details={"entity_type": change.entity_type},
            )

        existing = (
            await self.session.execute(
                select(model).where(
                    and_(
                        model.id == change.entity_id,  # type: ignore[attr-defined]
                        model.user_id == user_id,  # type: ignore[attr-defined]
                    )
                )
            )
        ).scalar_one_or_none()

        # --- INSERT (no existing row) ---
        if existing is None:
            if change.action == "delete":
                logger.debug(
                    "Delete for non-existent %s/%s — skipping",
                    change.entity_type, change.entity_id,
                )
                return False

            self.session.add(
                model(
                    id=change.entity_id,
                    user_id=user_id,
                    **change.data,
                )
            )
            await self._record_change(
                user_id, change.entity_type, change.entity_id,
                "create", change.data,
            )
            return True

        # --- Conflict detection ---
        existing_ts: datetime = getattr(
            existing, "updated_at",
            datetime.min.replace(tzinfo=timezone.utc),
        )

        if change.timestamp < existing_ts:
            # Client data is older → conflict, cloud wins
            conflict = SyncConflict(
                entity_type=change.entity_type,
                entity_id=change.entity_id,
                local_data=change.data,
                cloud_data=self._row_to_data(existing),
                local_timestamp=change.timestamp,
                cloud_timestamp=existing_ts,
            )
            resolved = await self.resolve_conflict(conflict)
            result.conflicts.append(resolved)

            if resolved.resolution == "cloud_wins":
                logger.info(
                    "Conflict on %s/%s resolved → cloud_wins (skipped)",
                    change.entity_type, change.entity_id,
                )
                return False
            # else: local_wins — fall through and apply

        # --- UPDATE / DELETE ---
        if change.action == "delete":
            await self.session.delete(existing)
            await self._record_change(
                user_id, change.entity_type, change.entity_id,
                "delete", change.data,
            )
        else:
            for key, value in change.data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await self._record_change(
                user_id, change.entity_type, change.entity_id,
                change.action, change.data,
            )

        return True

    async def _record_change(
        self,
        user_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        data: dict[str, Any],
    ) -> None:
        """Append an entry to the sync log with a monotonically increasing version.

        Parameters
        ----------
        user_id:
            Owning user.
        entity_type:
            E.g. ``"memory"``, ``"skill"``.
        entity_id:
            Primary key of the entity.
        action:
            ``"create"``, ``"update"``, ``"delete"``, or a conflict label.
        data:
            Snapshot of the data at this point in time.
        """
        current_version = await self.get_version(user_id)
        self.session.add(
            SyncLog(
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                data=data,
                sync_version=current_version + 1,
                source="cloud",
            )
        )

    @staticmethod
    def _log_row_to_dict(row: SyncLog) -> dict[str, Any]:
        """Serialise a :class:`SyncLog` row for the pull response."""
        return {
            "version": row.sync_version,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "action": row.action,
            "data": row.data,
            "timestamp": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _row_to_data(row: Any) -> dict[str, Any]:
        """Extract a plain dict of column values from an ORM instance.

        Skips SQLAlchemy internal state and relationship attributes.
        """
        data: dict[str, Any] = {}
        for col in row.__table__.columns:
            val = getattr(row, col.key, None)
            if isinstance(val, datetime):
                val = val.isoformat()
            data[col.key] = val
        return data
