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
import hashlib
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
DEFAULT_WORKFLOW_PATH = "~/.plutus/agent_workflows.json"

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
        workflow_path: str = DEFAULT_WORKFLOW_PATH,
    ) -> None:
        self.server_url: str = server_url.rstrip("/")
        self.token: str = token
        self.db_path: Path = Path(local_db_path).expanduser()
        self.workflow_path: Path = Path(workflow_path).expanduser()
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

            try:
                if self.db_path.exists():
                    rows = await self._read_dirty_rows(since)
                else:
                    log.debug("Local memory DB does not exist yet – skipping memory push.")
                    rows = []
                workflow_payloads = self._read_dirty_workflow_payloads()
            except Exception as exc:
                log.error("Failed to read local stores for push: %s", exc)
                raise SyncError(f"local store read failed: {exc}") from exc

            if not rows and not workflow_payloads:
                log.debug("No local changes to push (since version %d).", since)
                return since

            payloads = self._rows_to_payloads(rows, since) + workflow_payloads
            log.info("Pushing %d local change(s) to cloud…", len(payloads))

            body = {"payloads": payloads}
            resp_data = await self._post_with_retry(
                f"{self.server_url}/api/sync/push", body
            )

            new_version: int = resp_data.get("server_version", since)
            self._mark_workflows_synced(workflow_payloads)
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
        """Apply pulled rows into local memories and workflow definitions."""
        memory_rows: List[Dict[str, Any]] = []
        workflow_changes: List[Dict[str, Any]] = []
        for change in changes:
            if change.get("entity_type") == "workflow":
                workflow_changes.append(change)
            elif change.get("entity_type") == "memory":
                data = dict(change.get("data") or {})
                data.setdefault("id", change.get("entity_id"))
                data.setdefault("sync_version", change.get("version", 0))
                memory_rows.append(data)

        if memory_rows:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute(
                    """CREATE TABLE IF NOT EXISTS memories (
                           id TEXT PRIMARY KEY,
                           content TEXT,
                           category TEXT,
                           sync_version INTEGER DEFAULT 0
                       )"""
                )
                for row in memory_rows:
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
                        log.warning("Failed to upsert memory row %s: %s", row.get("id"), exc)
                await db.commit()

        if workflow_changes:
            self._apply_workflow_changes(workflow_changes)

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


    def _load_sync_state(self) -> Dict[str, Any]:
        try:
            if SYNC_STATE_FILE.exists():
                data = json.loads(SYNC_STATE_FILE.read_text())
                if isinstance(data, dict):
                    data.setdefault("version", 0)
                    data.setdefault("workflow_hashes", {})
                    return data
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Corrupt sync state file, resetting: %s", exc)
        return {"version": 0, "workflow_hashes": {}}

    def _workflow_payload_hash(self, workflow: Dict[str, Any]) -> str:
        canonical = dict(workflow)
        canonical.pop("content_hash", None)
        canonical.pop("last_synced_at", None)
        return hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _read_workflow_store(self) -> Dict[str, Any]:
        if not self.workflow_path.exists():
            return {"workflows": [], "runs": []}
        try:
            data = json.loads(self.workflow_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("workflows", [])
                data.setdefault("runs", [])
                return data
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to read workflow store: %s", exc)
        return {"workflows": [], "runs": []}

    def _save_workflow_store(self, data: Dict[str, Any]) -> None:
        self.workflow_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.workflow_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.workflow_path)

    def _read_dirty_workflow_payloads(self) -> List[Dict[str, Any]]:
        state = self._load_sync_state()
        known_hashes = dict(state.get("workflow_hashes") or {})
        store = self._read_workflow_store()
        changed = False
        payloads: List[Dict[str, Any]] = []
        for workflow in store.get("workflows", []):
            sync_id = str(workflow.get("sync_id") or f"wf-sync-{workflow.get('id')}")
            if workflow.get("sync_id") != sync_id:
                workflow["sync_id"] = sync_id
                changed = True
            workflow.setdefault("sync_revision", 0)
            workflow.setdefault("deleted_at", None)
            data = self._workflow_to_cloud_data(workflow)
            digest = self._workflow_payload_hash(data)
            if workflow.get("content_hash") != digest:
                workflow["content_hash"] = digest
                data["content_hash"] = digest
                changed = True
            if workflow.get("sync_dirty") or known_hashes.get(sync_id) != digest:
                action = "delete" if workflow.get("deleted_at") else "update"
                payloads.append({
                    "table": "workflow",
                    "operation": action,
                    "record_id": sync_id,
                    "data": data,
                    "client_version": int(state.get("version", 0) or 0),
                })
        if changed:
            self._save_workflow_store(store)
        return payloads

    def _workflow_to_cloud_data(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        labels = list(workflow.get("tags") or [])
        category = workflow.get("category")
        if category and category not in labels:
            labels.insert(0, category)
        return {
            "sync_id": workflow.get("sync_id"),
            "sync_revision": int(workflow.get("sync_revision") or 0),
            "content_hash": workflow.get("content_hash"),
            "name": workflow.get("title") or "Untitled workflow",
            "description": workflow.get("description") or "",
            "status": workflow.get("status") or "draft",
            "trigger_type": workflow.get("trigger_type") or "manual",
            "trigger_config": workflow.get("trigger_config") or {},
            "steps": workflow.get("steps") or [],
            "variables": workflow.get("variables") or {},
            "governance": workflow.get("governance") or {},
            "labels": labels,
            "owner": workflow.get("owner"),
            "deleted_at": workflow.get("deleted_at"),
        }

    def _mark_workflows_synced(self, payloads: List[Dict[str, Any]]) -> None:
        workflow_payloads = [p for p in payloads if p.get("table") == "workflow"]
        if not workflow_payloads:
            return
        state = self._load_sync_state()
        hashes = dict(state.get("workflow_hashes") or {})
        store = self._read_workflow_store()
        by_sync_id = {w.get("sync_id"): w for w in store.get("workflows", [])}
        now = time.time()
        for payload in workflow_payloads:
            sync_id = payload.get("record_id")
            data = payload.get("data") or {}
            hashes[str(sync_id)] = self._workflow_payload_hash(data)
            workflow = by_sync_id.get(sync_id)
            if workflow:
                workflow["sync_dirty"] = False
                workflow["last_synced_at"] = now
        state["workflow_hashes"] = hashes
        self._save_workflow_store(store)
        self._write_sync_state(state)

    def _apply_workflow_changes(self, changes: List[Dict[str, Any]]) -> None:
        store = self._read_workflow_store()
        workflows = list(store.get("workflows") or [])
        by_sync_id = {w.get("sync_id"): w for w in workflows if w.get("sync_id")}
        now = time.time()
        for change in changes:
            sync_id = str(change.get("entity_id") or "")
            if not sync_id:
                continue
            data = dict(change.get("data") or {})
            workflow = by_sync_id.get(sync_id)
            if workflow is None:
                workflow = {
                    "id": f"wf_{sync_id.replace('-', '')[:12]}",
                    "sync_id": sync_id,
                    "created_at": now,
                    "run_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "last_run_at": None,
                    "next_run_at": None,
                }
                workflows.append(workflow)
                by_sync_id[sync_id] = workflow
            labels = list(data.get("labels") or [])
            workflow.update({
                "title": data.get("name") or data.get("title") or workflow.get("title") or "Untitled workflow",
                "description": data.get("description") or "",
                "category": labels[0] if labels else workflow.get("category") or "Synced",
                "status": "archived" if change.get("action") == "delete" else data.get("status") or "draft",
                "trigger_type": data.get("trigger_type") or "manual",
                "trigger_config": data.get("trigger_config") or {},
                "priority": workflow.get("priority") or "normal",
                "tags": labels,
                "steps": data.get("steps") or [],
                "variables": data.get("variables") or {},
                "governance": data.get("governance") or {},
                "owner": data.get("owner"),
                "sync_revision": int(data.get("sync_revision") or workflow.get("sync_revision") or 0),
                "content_hash": data.get("content_hash"),
                "deleted_at": data.get("deleted_at") or (now if change.get("action") == "delete" else None),
                "sync_dirty": False,
                "last_synced_at": now,
                "updated_at": now,
            })
        store["workflows"] = workflows
        self._save_workflow_store(store)

        state = self._load_sync_state()
        hashes = dict(state.get("workflow_hashes") or {})
        for workflow in workflows:
            sync_id = workflow.get("sync_id")
            if sync_id:
                hashes[str(sync_id)] = self._workflow_payload_hash(self._workflow_to_cloud_data(workflow))
        state["workflow_hashes"] = hashes
        self._write_sync_state(state)

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
        state = self._load_sync_state()
        try:
            return int(state.get("version", 0))
        except (TypeError, ValueError):
            return 0

    def _write_sync_state(self, state: Dict[str, Any]) -> None:
        try:
            SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SYNC_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))
        except OSError as exc:
            log.error("Failed to save sync state: %s", exc)

    def _save_sync_version(self, version: int) -> None:
        state = self._load_sync_state()
        state["version"] = version
        state["updated_at"] = time.time()
        state.setdefault("workflow_hashes", {})
        self._write_sync_state(state)
