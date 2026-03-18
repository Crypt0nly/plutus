#!/usr/bin/env python3
"""Plutus Local Sync Client.

Handles bidirectional synchronisation between the local SQLite memory store
(~/.plutus/memory.db) and the Plutus Cloud API.

Push format  – POST /api/sync/push  {"payloads": [<SyncPayload>, ...]}
Pull format  – GET  /api/sync/pull?since_version=N
               Response: {"changes": [...], "server_version": <int>}

Each SyncPayload:
    table           – e.g. "memory"
    operation       – "insert" | "update" | "delete"
    record_id       – str
    data            – dict (row data minus id & sync_version)
    client_version  – int
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
import httpx

__all__ = ["LocalSyncClient"]

log = logging.getLogger("plutus_bridge.sync")

SYNC_STATE_FILE = Path("~/.plutus/sync_state.json").expanduser()
DEFAULT_DB_PATH = "~/.plutus/memory.db"

# Retry / back-off constants
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds
_HTTP_TIMEOUT = 30.0  # seconds per request


class SyncError(Exception):
    """Raised when a sync operation fails after retries."""


class LocalSyncClient:
    """Bidirectional sync between local SQLite and Plutus Cloud."""

    def __init__(
        self,
        server_url: str,
        token: str,
        local_db_path: str = DEFAULT_DB_PATH,
    ) -> None:
        self.server_url: str = server_url.rstrip("/")
        self.token: str = token
        self.db_path: Path = Path(local_db_path).expanduser()
        self._headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self._lock = asyncio.Lock()  # serialise concurrent sync calls

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def update_token(self, token: str) -> None:
        """Hot-swap the JWT without recreating the client."""
        self.token = token
        self._headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------
    # Push – send local changes to cloud
    # ------------------------------------------------------------------
    async def push_local_changes(self) -> int:
        """Push rows with sync_version > last-known to the cloud.

        Returns the new server_version after push.
        """
        async with self._lock:
            since = self._get_last_sync_version()

            if not self.db_path.exists():
                log.debug("Local DB does not exist yet – nothing to push.")
                return since

            try:
                rows = await self._read_dirty_rows(since)
            except Exception as exc:
                log.error("Failed to read local DB for push: %s", exc)
                raise SyncError(f"DB read failed: {exc}") from exc

            if not rows:
                log.debug("No local changes to push (since version %d).", since)
                return since

            payloads = self._rows_to_payloads(rows, since)
            log.info("Pushing %d local change(s) to cloud…", len(payloads))

            body = {"payloads": payloads}
            resp_data = await self._post_with_retry(
                f"{self.server_url}/api/sync/push", body
            )

            new_version: int = resp_data.get("server_version", since)
            self._save_sync_version(new_version)
            log.info("Push complete – server_version now %d.", new_version)
            return new_version

    # ------------------------------------------------------------------
    # Pull – fetch cloud changes into local DB
    # ------------------------------------------------------------------
    async def pull_cloud_changes(self) -> int:
        """Pull rows changed on the cloud since last-known version.

        Returns the new server_version after pull.
        """
        async with self._lock:
            since = self._get_last_sync_version()

            resp_data = await self._get_with_retry(
                f"{self.server_url}/api/sync/pull",
                params={"since_version": since},
            )

            changes: List[Dict[str, Any]] = resp_data.get("changes", [])
            new_version: int = resp_data.get("server_version", since)

            if changes:
                log.info(
                    "Applying %d cloud change(s) (version %d → %d).",
                    len(changes),
                    since,
                    new_version,
                )
                await self._apply_changes(changes)
            else:
                log.debug("No cloud changes since version %d.", since)

            self._save_sync_version(new_version)
            return new_version

    # ------------------------------------------------------------------
    # Full sync – push then pull
    # ------------------------------------------------------------------
    async def full_sync(self) -> int:
        """Run a complete push-then-pull cycle.

        Returns the final server_version.
        """
        log.info("Starting full sync cycle…")
        t0 = time.monotonic()
        try:
            await self.push_local_changes()
            version = await self.pull_cloud_changes()
            elapsed = time.monotonic() - t0
            log.info("Full sync finished in %.2fs – version %d.", elapsed, version)
            return version
        except SyncError:
            raise
        except Exception as exc:
            log.error("Full sync failed: %s", exc, exc_info=True)
            raise SyncError(f"full_sync failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal – DB helpers
    # ------------------------------------------------------------------
    async def _read_dirty_rows(self, since: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM memories WHERE sync_version > ? ORDER BY sync_version",
                (since,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def _apply_changes(self, changes: List[Dict[str, Any]]) -> None:
        """Upsert pulled rows into the local memories table."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self.db_path)) as db:
            # Ensure the table exists (minimal schema)
            await db.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                       id TEXT PRIMARY KEY,
                       content TEXT,
                       category TEXT,
                       sync_version INTEGER DEFAULT 0
                   )"""
            )
            for row in changes:
                if not row:
                    continue
                cols = list(row.keys())
                placeholders = ", ".join("?" for _ in cols)
                col_names = ", ".join(cols)
                updates = ", ".join(f"{k}=excluded.{k}" for k in cols if k != "id")
                sql = (
                    f"INSERT INTO memories ({col_names}) VALUES ({placeholders})"
                    f" ON CONFLICT(id) DO UPDATE SET {updates}"
                )
                try:
                    await db.execute(sql, list(row.values()))
                except Exception as exc:
                    log.warning("Failed to upsert row %s: %s", row.get("id"), exc)
            await db.commit()

    @staticmethod
    def _rows_to_payloads(
        rows: List[Dict[str, Any]], fallback_version: int
    ) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        for r in rows:
            payloads.append(
                {
                    "table": "memory",
                    "operation": "update",
                    "record_id": str(r.get("id", "")),
                    "data": {
                        k: v
                        for k, v in r.items()
                        if k not in ("id", "sync_version")
                    },
                    "client_version": r.get("sync_version", fallback_version),
                }
            )
        return payloads

    # ------------------------------------------------------------------
    # Internal – HTTP with retry
    # ------------------------------------------------------------------
    async def _post_with_retry(
        self, url: str, body: dict
    ) -> Dict[str, Any]:
        return await self._request_with_retry("POST", url, json_body=body)

    async def _get_with_retry(
        self, url: str, params: Optional[dict] = None
    ) -> Dict[str, Any]:
        return await self._request_with_retry("GET", url, params=params)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    if method == "POST":
                        resp = await client.post(
                            url,
                            json=json_body,
                            headers=self._headers,
                        )
                    else:
                        resp = await client.get(
                            url,
                            params=params,
                            headers=self._headers,
                        )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # Don't retry auth errors – they won't self-heal
                if status in (401, 403):
                    log.error("Auth error (%d) from %s – not retrying.", status, url)
                    raise SyncError(f"Auth error {status}") from exc
                last_exc = exc
                log.warning(
                    "HTTP %d on %s (attempt %d/%d).",
                    status,
                    url,
                    attempt,
                    _MAX_RETRIES,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                log.warning(
                    "Request error on %s (attempt %d/%d): %s",
                    url,
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )

            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        raise SyncError(
            f"Failed after {_MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Internal – sync-state persistence
    # ------------------------------------------------------------------
    def _get_last_sync_version(self) -> int:
        try:
            if SYNC_STATE_FILE.exists():
                data = json.loads(SYNC_STATE_FILE.read_text())
                return int(data.get("version", 0))
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            log.warning("Corrupt sync state file, resetting: %s", exc)
        return 0

    def _save_sync_version(self, version: int) -> None:
        try:
            SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SYNC_STATE_FILE.write_text(
                json.dumps({"version": version, "updated_at": time.time()})
            )
        except OSError as exc:
            log.error("Failed to save sync state: %s", exc)
