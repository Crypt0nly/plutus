"""REST API routes for configuration, guardrails, history, and system status."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from plutus.guardrails.tiers import Tier, get_tier_info

logger = logging.getLogger("plutus.gateway.routes")


def _version_newer(latest: str, current: str) -> bool:
    """Return True if *latest* is strictly newer than *current* (semver segments)."""
    try:
        l_parts = [int(x) for x in latest.split(".")]
        c_parts = [int(x) for x in current.split(".")]
        return l_parts > c_parts
    except (ValueError, AttributeError):
        return False


# ── Request body models (module-level for proper FastAPI schema generation) ──


class TierUpdate(BaseModel):
    tier: str


class ToolOverrideUpdate(BaseModel):
    tool_name: str
    enabled: bool = True
    require_approval: bool = False


class ApprovalDecision(BaseModel):
    approval_id: str
    approved: bool


class SetKeyRequest(BaseModel):
    provider: str
    key: str


class ConfigUpdate(BaseModel):
    patch: dict[str, Any]


class CreateCustomToolRequest(BaseModel):
    tool_name: str
    description: str = ""
    code: str
    auto_register: bool = True  # renamed from 'register' to avoid shadowing BaseModel.register


class HeartbeatUpdate(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    max_consecutive: int | None = None
    prompt: str | None = None


class CreatePlanRequest(BaseModel):
    title: str
    goal: str | None = None
    steps: list[dict[str, str]]
    conversation_id: str | None = None


class UpdateStepRequest(BaseModel):
    step_index: int
    status: str
    result: str | None = None


class PlanStatusUpdate(BaseModel):
    status: str


class RenameConversationRequest(BaseModel):
    title: str


class ConnectorConfigUpdate(BaseModel):
    config: dict[str, Any]


class ConnectorSendMessage(BaseModel):
    text: str
    params: dict[str, Any] = {}


class ConnectorAutoStartUpdate(BaseModel):
    auto_start: bool



def create_router() -> APIRouter:
    router = APIRouter()

    # ── Status ──────────────────────────────────────────────

    @router.get("/status")
    async def get_status() -> dict[str, Any]:
        from plutus import __version__, build_tag
        from plutus.gateway.server import get_state

        state = get_state()
        guardrails = state.get("guardrails")
        tool_registry = state.get("tool_registry")
        agent = state.get("agent")
        heartbeat = state.get("heartbeat")

        worker_pool = state.get("worker_pool")
        scheduler = state.get("scheduler")
        model_router = state.get("model_router")

        config = state.get("config")
        return {
            "version": __version__ + build_tag,
            "status": "running",
            "key_configured": agent.key_configured if agent else False,
            "onboarding_completed": config.onboarding_completed if config else False,
            "guardrails": guardrails.get_status() if guardrails else None,
            "tools": tool_registry.list_tools() if tool_registry else [],
            "heartbeat": heartbeat.status() if heartbeat else None,
            "planner_enabled": config.planner.enabled if config else False,
            "worker_pool": worker_pool.stats() if worker_pool else None,
            "scheduler": scheduler.stats() if scheduler else None,
            "model_routing": model_router.config.to_dict() if model_router else None,
        }

    # ── Guardrails ──────────────────────────────────────────

    @router.get("/guardrails")
    async def get_guardrails() -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        guardrails = state.get("guardrails")
        config = state.get("config")

        if not guardrails:
            raise HTTPException(500, "Guardrails not initialized")

        return {
            "current_tier": guardrails.tier.value,
            "tier_info": get_tier_info(),
            "overrides": {
                k: v.model_dump() for k, v in config.guardrails.tool_overrides.items()
            },
            "audit_enabled": config.guardrails.audit_enabled,
        }

    @router.put("/guardrails/tier")
    async def set_tier(body: TierUpdate) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        guardrails = state.get("guardrails")

        try:
            new_tier = Tier(body.tier)
        except ValueError:
            raise HTTPException(400, f"Invalid tier: {body.tier}")

        guardrails.set_tier(new_tier)
        return {"tier": new_tier.value, "message": f"Tier set to {new_tier.label}"}

    @router.put("/guardrails/override")
    async def set_tool_override(body: ToolOverrideUpdate) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")

        from plutus.config import ToolOverride

        config.guardrails.tool_overrides[body.tool_name] = ToolOverride(
            enabled=body.enabled, require_approval=body.require_approval
        )
        config.save()
        return {"message": f"Override set for {body.tool_name}"}

    # ── Approvals ───────────────────────────────────────────

    @router.get("/approvals")
    async def get_pending_approvals() -> list[dict[str, Any]]:
        from plutus.gateway.server import get_state

        state = get_state()
        guardrails = state.get("guardrails")
        return guardrails.pending_approvals() if guardrails else []

    @router.post("/approvals/resolve")
    async def resolve_approval(body: ApprovalDecision) -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        guardrails = state.get("guardrails")

        if not guardrails:
            raise HTTPException(500, "Guardrails not initialized")

        success = guardrails.resolve_approval(body.approval_id, body.approved)
        if not success:
            raise HTTPException(404, f"Approval {body.approval_id} not found")

        return {"resolved": True, "approved": body.approved}

    # ── Audit ───────────────────────────────────────────────

    @router.get("/audit")
    async def get_audit_log(limit: int = 50, offset: int = 0) -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        guardrails = state.get("guardrails")

        if not guardrails:
            return {"entries": [], "total": 0}

        entries = guardrails.audit.recent(limit=limit, offset=offset)
        return {
            "entries": [e.to_dict() for e in entries],
            "total": guardrails.audit.count(),
        }

    # ── Conversations ───────────────────────────────────────

    @router.get("/conversations")
    async def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return []
        return await memory.list_conversations(limit)

    @router.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: str) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if agent:
            await agent.conversation.delete_conversation(conv_id)
        return {"message": "Deleted"}

    @router.patch("/conversations/{conv_id}")
    async def rename_conversation(conv_id: str, body: RenameConversationRequest) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if memory:
            await memory.rename_conversation(conv_id, body.title)
        return {"message": "Renamed", "title": body.title}

    @router.get("/conversations/{conv_id}/messages")
    async def get_messages(conv_id: str) -> list[dict[str, Any]]:
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return []
        return await memory.get_messages(conv_id)

    @router.post("/conversations/cleanup")
    async def cleanup_conversations() -> dict[str, Any]:
        """Manually trigger conversation cleanup."""
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        config = state.get("config")
        if not memory or not config:
            return {"deleted": 0}
        days = config.memory.conversation_auto_delete_days
        if days <= 0:
            return {"deleted": 0, "message": "Auto-delete is disabled"}
        deleted = await memory.cleanup_stale_conversations(days)
        return {"deleted": deleted, "max_age_days": days}

    # ── Tools ───────────────────────────────────────────────

    @router.get("/tools")
    async def list_tools() -> list[dict[str, Any]]:
        from plutus.gateway.server import get_state

        state = get_state()
        registry = state.get("tool_registry")
        return registry.get_tool_info() if registry else []

    @router.get("/tools/details")
    async def get_tools_details() -> dict[str, Any]:
        """Get detailed info about all tools, grouped by category."""
        from plutus.gateway.server import get_state

        state = get_state()
        registry = state.get("tool_registry")
        if not registry:
            return {"tools": [], "categories": {}}

        tools = registry.get_tool_info()

        # Categorize tools
        categories = {
            "core": {"label": "Core Tools", "description": "Essential system tools", "icon": "terminal", "tools": []},
            "code": {"label": "Code Tools", "description": "Code editing and analysis", "icon": "code", "tools": []},
            "subprocess": {"label": "Subprocess", "description": "Process orchestration", "icon": "cpu", "tools": []},
            "desktop": {"label": "Desktop", "description": "Desktop and browser automation", "icon": "monitor", "tools": []},
            "custom": {"label": "Custom Tools", "description": "Dynamically created tools", "icon": "puzzle", "tools": []},
        }

        category_map = {
            "shell": "core", "filesystem": "core", "process": "core", "system_info": "core",
            "code_editor": "code", "code_analysis": "code",
            "subprocess": "subprocess", "tool_creator": "subprocess",
            "pc": "desktop",
            "browser": "desktop", "clipboard": "desktop", "desktop": "desktop", "app_manager": "desktop",
        }

        for tool in tools:
            cat = category_map.get(tool["name"], "custom" if tool["name"].startswith("custom_") else "core")
            categories[cat]["tools"].append(tool)

        return {"tools": tools, "categories": categories, "total": len(tools)}

    # ── Workers (Agent Worker Pool) ──────────────────────────

    @router.get("/workers")
    async def get_workers() -> dict[str, Any]:
        """Get all workers — active, queued, and recent."""
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        pool = state.get("worker_pool")

        if not pool:
            return {"workers": [], "stats": {}}

        stats = pool.stats()
        if config:
            stats["max_tool_rounds"] = config.workers.max_tool_rounds

        return {
            "running": pool.list_running(),
            "queued": pool.list_queued(),
            "completed": pool.list_completed(30),
            "workers": pool.list_all(),  # backward compat
            "stats": stats,
        }

    @router.get("/workers/{task_id}")
    async def get_worker_status(task_id: str) -> dict[str, Any]:
        """Get status of a specific worker."""
        from plutus.gateway.server import get_state

        state = get_state()
        pool = state.get("worker_pool")
        if not pool:
            raise HTTPException(500, "Worker pool not initialized")

        status = pool.get_status(task_id)
        if not status:
            raise HTTPException(404, f"Worker {task_id} not found")
        return status.to_dict()

    @router.post("/workers/{task_id}/cancel")
    async def cancel_worker(task_id: str) -> dict[str, Any]:
        """Cancel a running worker."""
        from plutus.gateway.server import get_state

        state = get_state()
        pool = state.get("worker_pool")
        if not pool:
            raise HTTPException(500, "Worker pool not initialized")

        cancelled = await pool.cancel(task_id)
        if not cancelled:
            raise HTTPException(404, f"Worker {task_id} not found or not running")
        return {"cancelled": True, "task_id": task_id}

    @router.patch("/workers/config")
    async def update_worker_config(body: ConfigUpdate) -> dict[str, Any]:
        """Update worker pool configuration (e.g. max_concurrent_workers)."""
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        pool = state.get("worker_pool")

        if not config or not pool:
            raise HTTPException(500, "Not initialized")

        if "max_concurrent_workers" in body.patch:
            new_max = max(1, min(int(body.patch["max_concurrent_workers"]), 20))
            config.workers.max_concurrent_workers = new_max
            pool.max_workers = new_max

        if "max_tool_rounds" in body.patch:
            new_rounds = max(1, min(int(body.patch["max_tool_rounds"]), 50))
            config.workers.max_tool_rounds = new_rounds

        config.save()

        stats = pool.stats()
        stats["max_tool_rounds"] = config.workers.max_tool_rounds
        return {"message": "Worker config updated", "stats": stats}

    # ── Scheduler ──────────────────────────────────────────────

    @router.get("/scheduler")
    async def get_scheduler_status() -> dict[str, Any]:
        """Get scheduler status and all jobs."""
        from plutus.gateway.server import get_state

        state = get_state()
        scheduler = state.get("scheduler")
        if not scheduler:
            return {"running": False, "jobs": [], "stats": {}}

        return {
            "running": scheduler.running,
            "jobs": scheduler.list_jobs(),
            "stats": scheduler.stats(),
        }

    @router.get("/scheduler/jobs")
    async def list_scheduled_jobs() -> dict[str, Any]:
        """List all scheduled jobs."""
        from plutus.gateway.server import get_state

        state = get_state()
        scheduler = state.get("scheduler")
        if not scheduler:
            return {"jobs": []}
        return {"jobs": scheduler.list_jobs()}

    @router.get("/scheduler/jobs/{job_id}")
    async def get_scheduled_job(job_id: str) -> dict[str, Any]:
        """Get details of a specific scheduled job."""
        from plutus.gateway.server import get_state

        state = get_state()
        scheduler = state.get("scheduler")
        if not scheduler:
            raise HTTPException(500, "Scheduler not initialized")

        job = scheduler.get_job(job_id)
        if not job:
            raise HTTPException(404, f"Job {job_id} not found")
        return job.to_dict()

    @router.post("/scheduler/jobs/{job_id}/pause")
    async def pause_scheduled_job(job_id: str) -> dict[str, Any]:
        """Pause a scheduled job."""
        from plutus.gateway.server import get_state

        state = get_state()
        scheduler = state.get("scheduler")
        if not scheduler:
            raise HTTPException(500, "Scheduler not initialized")

        if not scheduler.pause_job(job_id):
            raise HTTPException(404, f"Job {job_id} not found")
        return {"message": f"Job {job_id} paused"}

    @router.post("/scheduler/jobs/{job_id}/resume")
    async def resume_scheduled_job(job_id: str) -> dict[str, Any]:
        """Resume a paused scheduled job."""
        from plutus.gateway.server import get_state

        state = get_state()
        scheduler = state.get("scheduler")
        if not scheduler:
            raise HTTPException(500, "Scheduler not initialized")

        if not scheduler.resume_job(job_id):
            raise HTTPException(404, f"Job {job_id} not found")
        return {"message": f"Job {job_id} resumed"}

    @router.delete("/scheduler/jobs/{job_id}")
    async def delete_scheduled_job(job_id: str) -> dict[str, Any]:
        """Delete a scheduled job."""
        from plutus.gateway.server import get_state

        state = get_state()
        scheduler = state.get("scheduler")
        if not scheduler:
            raise HTTPException(500, "Scheduler not initialized")

        if not scheduler.remove_job(job_id):
            raise HTTPException(404, f"Job {job_id} not found")
        return {"message": f"Job {job_id} deleted"}

    @router.get("/scheduler/history")
    async def get_scheduler_history(limit: int = 50, job_id: str | None = None) -> dict[str, Any]:
        """Get recent job execution history."""
        from plutus.gateway.server import get_state

        state = get_state()
        scheduler = state.get("scheduler")
        if not scheduler:
            return {"executions": []}
        return {"executions": scheduler.list_executions(limit=limit, job_id=job_id)}

    # ── Model Routing ──────────────────────────────────────────

    @router.get("/models")
    async def get_model_routing() -> dict[str, Any]:
        """Get available models and routing configuration."""
        from plutus.gateway.server import get_state

        state = get_state()
        model_router = state.get("model_router")
        config = state.get("config")

        if not model_router:
            return {"models": [], "routing": {}}

        return {
            "models": model_router.get_available_models(),
            "routing": {
                "cost_conscious": config.model_routing.cost_conscious if config else False,
                "default_worker_model": config.model_routing.default_worker_model if config else "auto",
                "default_scheduler_model": config.model_routing.default_scheduler_model if config else "auto",
                "enabled_models": config.model_routing.enabled_models if config else [],
            },
            "usage": model_router.get_usage_stats(),
        }

    @router.patch("/models/config")
    async def update_model_routing(body: ConfigUpdate) -> dict[str, Any]:
        """Update model routing configuration."""
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        model_router = state.get("model_router")

        if not config:
            raise HTTPException(500, "Config not loaded")

        # Update config
        for key, value in body.patch.items():
            if hasattr(config.model_routing, key):
                setattr(config.model_routing, key, value)
        config.save()

        # Update router
        if model_router:
            model_router.config.cost_conscious = config.model_routing.cost_conscious
            model_router.config.default_worker_model = config.model_routing.default_worker_model
            model_router.config.default_scheduler_model = config.model_routing.default_scheduler_model
            model_router.config.enabled_models = config.model_routing.enabled_models

        return {"message": "Model routing updated"}

    # ── Custom Tools Management ─────────────────────────────

    @router.get("/custom-tools")
    async def list_custom_tools() -> dict[str, Any]:
        """List all custom tools with their metadata."""
        import json as _json
        from pathlib import Path as _Path

        tools_dir = _Path.home() / ".plutus" / "custom_tools"
        tools = []

        if tools_dir.exists():
            for tool_dir in sorted(tools_dir.iterdir()):
                if not tool_dir.is_dir():
                    continue

                meta_path = tool_dir / "metadata.json"
                script_path = tool_dir / "tool.py"

                info = {
                    "name": tool_dir.name,
                    "description": "",
                    "has_script": script_path.exists(),
                    "path": str(tool_dir),
                }

                if meta_path.exists():
                    try:
                        meta = _json.loads(meta_path.read_text())
                        info["description"] = meta.get("description", "")
                        info["created_by"] = meta.get("created_by", "unknown")
                    except Exception:
                        pass

                if script_path.exists():
                    code = script_path.read_text()
                    info["code_lines"] = len(code.splitlines())
                    info["code_preview"] = "\n".join(code.splitlines()[:20])

                tools.append(info)

        return {"tools": tools, "count": len(tools)}

    @router.post("/custom-tools")
    async def create_custom_tool(body: CreateCustomToolRequest) -> dict[str, Any]:
        """Create a new custom tool from the UI wizard."""
        import json as _json
        import re as _re
        from pathlib import Path as _Path

        from plutus.gateway.server import get_state

        # Validate tool name
        if not body.tool_name or not _re.match(r'^[a-z][a-z0-9_]*$', body.tool_name):
            raise HTTPException(
                400,
                "Tool name must be lowercase, start with a letter, and contain only letters, numbers, and underscores."
            )

        if not body.code.strip():
            raise HTTPException(400, "Code cannot be empty.")

        # Check that code defines a main function
        if 'def main(' not in body.code:
            raise HTTPException(
                400,
                "Code must define a 'main(args: dict) -> dict' function."
            )

        # Save the tool to disk
        tools_dir = _Path.home() / ".plutus" / "custom_tools"
        tool_dir = tools_dir / body.tool_name
        tool_dir.mkdir(parents=True, exist_ok=True)

        script_path = tool_dir / "tool.py"
        script_path.write_text(body.code, encoding="utf-8")

        metadata = {
            "name": body.tool_name,
            "description": body.description,
            "script": str(script_path),
            "created_by": "ui_wizard",
        }
        meta_path = tool_dir / "metadata.json"
        meta_path.write_text(_json.dumps(metadata, indent=2), encoding="utf-8")

        # Register the tool in the live registry
        registered = False
        if body.auto_register:
            state = get_state()
            registry = state.get("tool_registry")
            if registry:
                try:
                    from plutus.core.subprocess_manager import SubprocessManager
                    from plutus.tools.tool_creator import DynamicTool

                    # Get or create subprocess manager
                    sub_tool = registry.get("subprocess")
                    mgr = sub_tool._manager if sub_tool and hasattr(sub_tool, '_manager') else SubprocessManager()

                    dynamic_tool = DynamicTool(
                        tool_name=body.tool_name,
                        tool_description=body.description,
                        script_path=str(script_path),
                        subprocess_manager=mgr,
                    )
                    registry.register(dynamic_tool)
                    registered = True
                except Exception as e:
                    # Tool saved but registration failed — not fatal
                    registered = False

        return {
            "created": True,
            "tool_name": body.tool_name,
            "description": body.description,
            "path": str(script_path),
            "registered": registered,
            "code_lines": len(body.code.splitlines()),
        }

    @router.delete("/custom-tools/{tool_name}")
    async def delete_custom_tool(tool_name: str) -> dict[str, str]:
        """Delete a custom tool."""
        import shutil
        from pathlib import Path as _Path

        tools_dir = _Path.home() / ".plutus" / "custom_tools"
        tool_dir = tools_dir / tool_name

        if not tool_dir.exists():
            raise HTTPException(404, f"Custom tool not found: {tool_name}")

        shutil.rmtree(tool_dir)

        # Also unregister from the running registry
        from plutus.gateway.server import get_state
        state = get_state()
        registry = state.get("tool_registry")
        if registry:
            registry.unregister(f"custom_{tool_name}")

        return {"message": f"Deleted custom tool: {tool_name}"}

    # ── API Keys ─────────────────────────────────────────────

    @router.get("/keys/status")
    async def get_key_status() -> dict[str, Any]:
        """Return which providers have API keys configured (never returns actual keys)."""
        from plutus.gateway.server import get_state

        state = get_state()
        secrets = state.get("secrets")
        agent = state.get("agent")

        if not secrets:
            return {"providers": {}, "current_provider_configured": False}

        status = secrets.key_status()
        config = state.get("config")
        current_provider = config.model.provider if config else "anthropic"

        return {
            "providers": status,
            "current_provider": current_provider,
            "current_provider_configured": status.get(current_provider, False),
        }

    @router.post("/keys")
    async def set_api_key(body: SetKeyRequest) -> dict[str, Any]:
        """Store an API key and make it available to the agent immediately."""
        from plutus.gateway.server import get_state

        state = get_state()
        secrets = state.get("secrets")
        agent = state.get("agent")

        if not secrets:
            raise HTTPException(500, "Secrets store not initialized")

        if not body.key.strip():
            raise HTTPException(400, "API key cannot be empty")

        secrets.set_key(body.provider, body.key.strip())

        # Reload the key in the running agent
        key_available = False
        if agent:
            key_available = agent.reload_key()

        return {
            "message": f"API key saved for {body.provider}",
            "key_configured": key_available,
        }

    @router.delete("/keys/{provider}")
    async def delete_api_key(provider: str) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        secrets = state.get("secrets")

        if not secrets:
            raise HTTPException(500, "Secrets store not initialized")

        secrets.delete_key(provider)
        return {"message": f"API key removed for {provider}"}

    # ── Config ──────────────────────────────────────────────

    @router.get("/config")
    async def get_config() -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        if not config:
            raise HTTPException(500, "Config not loaded")

        data = config.model_dump()
        # Redact API key env var name (don't leak the actual key)
        if "model" in data:
            data["model"]["api_key_env"] = config.model.api_key_env
        return data

    @router.patch("/config")
    async def update_config(body: ConfigUpdate) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        config.update(body.patch)

        # Hot-reload the agent's LLM client when model settings change so the
        # user doesn't need to restart the server after switching models.
        if "model" in body.patch:
            agent = state.get("agent")
            if agent is not None:
                agent.reload_model()

        return {"message": "Config updated"}

    # ── Setup / Onboarding ────────────────────────────────────

    @router.post("/setup/complete")
    async def complete_setup() -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        if not config:
            raise HTTPException(500, "Config not loaded")
        config.onboarding_completed = True
        config.save()
        return {"message": "Onboarding completed"}

    # ── Heartbeat ────────────────────────────────────────────

    @router.get("/heartbeat")
    async def get_heartbeat_status() -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        heartbeat = state.get("heartbeat")
        if not heartbeat:
            return {"enabled": False, "running": False}
        return heartbeat.status()

    @router.put("/heartbeat")
    async def update_heartbeat(body: HeartbeatUpdate) -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        heartbeat = state.get("heartbeat")
        config = state.get("config")

        if not heartbeat or not config:
            raise HTTPException(500, "Heartbeat not initialized")

        if body.enabled is not None:
            config.heartbeat.enabled = body.enabled
        if body.interval_seconds is not None:
            config.heartbeat.interval_seconds = body.interval_seconds
        if body.quiet_hours_start is not None:
            config.heartbeat.quiet_hours_start = body.quiet_hours_start or None
        if body.quiet_hours_end is not None:
            config.heartbeat.quiet_hours_end = body.quiet_hours_end or None
        if body.max_consecutive is not None:
            config.heartbeat.max_consecutive = body.max_consecutive
        if body.prompt is not None:
            config.heartbeat.prompt = body.prompt

        config.save()
        heartbeat.update_config(config.heartbeat)

        # Start or stop based on enabled flag
        if config.heartbeat.enabled and not heartbeat.running:
            heartbeat.start()
        elif not config.heartbeat.enabled and heartbeat.running:
            heartbeat.stop()

        return heartbeat.status()

    @router.post("/heartbeat/start")
    async def start_heartbeat() -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        heartbeat = state.get("heartbeat")
        config = state.get("config")

        if not heartbeat:
            raise HTTPException(500, "Heartbeat not initialized")

        config.heartbeat.enabled = True
        config.save()
        heartbeat.update_config(config.heartbeat)
        heartbeat.start()
        return heartbeat.status()

    @router.post("/heartbeat/stop")
    async def stop_heartbeat() -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        heartbeat = state.get("heartbeat")
        config = state.get("config")

        if not heartbeat:
            raise HTTPException(500, "Heartbeat not initialized")

        config.heartbeat.enabled = False
        config.save()
        heartbeat.stop()
        return heartbeat.status()

    # ── Keep Alive ─────────────────────────────────────────────

    @router.get("/keep-alive")
    async def get_keep_alive_status() -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        keep_alive = state.get("keep_alive")

        return {
            "enabled": config.keep_alive.enabled if config else False,
            "active": keep_alive.active if keep_alive else False,
            "platform": keep_alive._system if keep_alive else None,
        }

    @router.put("/keep-alive")
    async def toggle_keep_alive(body: dict[str, Any]) -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        keep_alive = state.get("keep_alive")

        if not config or not keep_alive:
            raise HTTPException(500, "Keep-alive not initialized")

        enabled = body.get("enabled", False)
        config.keep_alive.enabled = enabled
        config.save()

        if enabled:
            keep_alive.enable()
        else:
            keep_alive.disable()

        return {
            "enabled": config.keep_alive.enabled,
            "active": keep_alive.active,
            "platform": keep_alive._system,
        }

    # ── Plans ────────────────────────────────────────────────

    @router.get("/plans")
    async def list_plans(conversation_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if not agent:
            return []
        return await agent.planner.list_plans(conversation_id=conversation_id, limit=limit)

    @router.post("/plans")
    async def create_plan(body: CreatePlanRequest) -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if not agent:
            raise HTTPException(500, "Agent not initialized")

        plan = await agent.planner.create_plan(
            title=body.title,
            steps=body.steps,
            goal=body.goal,
            conversation_id=body.conversation_id,
        )
        return plan

    @router.get("/plans/active")
    async def get_active_plan(conversation_id: str | None = None) -> dict[str, Any] | None:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if not agent:
            return None
        return await agent.planner.get_active_plan(conversation_id)

    @router.get("/plans/{plan_id}")
    async def get_plan(plan_id: str) -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if not agent:
            raise HTTPException(500, "Agent not initialized")

        plan = await agent.planner.get_plan(plan_id)
        if not plan:
            raise HTTPException(404, f"Plan {plan_id} not found")
        return plan

    @router.put("/plans/{plan_id}/status")
    async def update_plan_status(plan_id: str, body: PlanStatusUpdate) -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if not agent:
            raise HTTPException(500, "Agent not initialized")

        plan = await agent.planner.set_plan_status(plan_id, body.status)
        if not plan:
            raise HTTPException(404, f"Plan {plan_id} not found")
        return plan

    @router.put("/plans/{plan_id}/steps/{step_index}")
    async def update_plan_step(plan_id: str, step_index: int, body: UpdateStepRequest) -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if not agent:
            raise HTTPException(500, "Agent not initialized")

        plan = await agent.planner.update_step(plan_id, step_index, body.status, body.result)
        if not plan:
            raise HTTPException(404, f"Plan {plan_id} or step {step_index} not found")
        return plan

    @router.delete("/plans/{plan_id}")
    async def delete_plan(plan_id: str) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if not agent:
            raise HTTPException(500, "Agent not initialized")

        deleted = await agent.planner.delete_plan(plan_id)
        if not deleted:
            raise HTTPException(404, f"Plan {plan_id} not found")
        return {"message": "Plan deleted"}

    # ── PC Control ────────────────────────────────────────────

    @router.get("/pc/context")
    async def get_pc_context() -> dict[str, Any]:
        """Get the current PC context — active app, window, mouse position."""
        try:
            from plutus.pc.context import get_context_engine
            ctx_engine = get_context_engine()
            ctx = await ctx_engine.get_context(force_refresh=True)
            return {
                "active_app": ctx.active_app_name,
                "active_window": ctx.active_window_title,
                "category": ctx.active_app_category,
                "pid": ctx.active_window_pid,
                "browser_tab": ctx.active_browser_tab,
                "document": ctx.active_document,
                "mouse": {"x": ctx.mouse_x, "y": ctx.mouse_y},
                "summary": ctx.summary(),
                "action_count": len(ctx_engine._action_log),
                "recent_actions": [
                    {"action": a["action"], "target_app": a.get("target_app"), "timestamp": a["timestamp"]}
                    for a in ctx_engine._action_log[-10:]
                ],
            }
        except Exception as e:
            return {
                "active_app": "unknown",
                "active_window": "unknown",
                "category": "unknown",
                "mouse": {"x": 0, "y": 0},
                "summary": f"Context unavailable: {e}",
                "error": str(e),
            }

    @router.get("/pc/status")
    async def get_pc_status() -> dict[str, Any]:
        """Get the PC control system status and capabilities."""
        from plutus.gateway.server import get_state

        state = get_state()
        registry = state.get("tool_registry")

        if not registry:
            return {"available": False}

        pc_tool = registry.get("pc")
        if not pc_tool:
            return {"available": False}

        # Get current context
        context_info = {}
        try:
            from plutus.pc.context import get_context_engine
            ctx_engine = get_context_engine()
            ctx = await ctx_engine.get_context()
            context_info = {
                "active_app": ctx.active_app_name,
                "active_window": ctx.active_window_title,
                "category": ctx.active_app_category,
                "mouse": {"x": ctx.mouse_x, "y": ctx.mouse_y},
            }
        except Exception:
            context_info = {"active_app": "unknown", "active_window": "unknown"}

        return {
            "available": True,
            "context": context_info,
            "capabilities": {
                "context": {
                    "label": "Context Awareness",
                    "description": "Always knows which app/window is active. Prevents typing into the wrong window.",
                    "operations": ["get_context", "active_window"],
                },
                "mouse": {
                    "label": "Mouse Control",
                    "description": "Smooth human-like mouse movement, clicking, dragging, scrolling",
                    "operations": ["move", "click", "double_click", "right_click", "drag", "scroll", "hover"],
                },
                "keyboard": {
                    "label": "Keyboard Control",
                    "description": "Natural typing, key presses, hotkeys, and cross-platform shortcuts",
                    "operations": ["type", "press", "hotkey", "shortcut", "key_down", "key_up", "list_shortcuts"],
                },
                "screen": {
                    "label": "Screen Reading",
                    "description": "Screenshots, OCR text reading, element detection, color finding",
                    "operations": ["screenshot", "read_screen", "find_text", "find_elements", "get_pixel_color", "find_color", "wait_for_text", "wait_for_change", "screen_info"],
                },
                "windows": {
                    "label": "Window Management",
                    "description": "List, focus, snap, tile, resize, and manage application windows",
                    "operations": ["list_windows", "find_window", "focus", "close_window", "minimize", "maximize", "move_window", "resize", "snap_left", "snap_right", "snap_top", "snap_bottom", "snap_quarter", "tile", "active_window"],
                },
                "workflows": {
                    "label": "Workflow Automation",
                    "description": "Create, save, and replay multi-step action sequences",
                    "operations": ["run_workflow", "save_workflow", "list_workflows", "list_templates", "get_template", "delete_workflow"],
                },
            },
        }

    @router.get("/pc/computer-use")
    async def get_computer_use_status() -> dict[str, Any]:
        """Get the Computer Use agent status."""
        from plutus.gateway.server import get_state

        state = get_state()
        cu_agent = state.get("cu_agent")

        if not cu_agent:
            return {
                "available": False,
                "reason": "No Anthropic API key configured or anthropic package not installed",
            }

        return {
            "available": True,
            "running": cu_agent.is_running,
            "iterations": cu_agent.iteration_count,
            "model": cu_agent._model,
            "max_iterations": cu_agent._max_iterations,
        }

    @router.get("/pc/screenshot")
    async def get_latest_screenshot() -> dict[str, Any]:
        """Get the latest screenshot as base64."""
        from pathlib import Path
        import base64

        screenshot_path = Path.home() / ".plutus" / "screenshots" / "latest.png"
        if not screenshot_path.exists():
            return {"available": False}

        try:
            b64 = base64.b64encode(screenshot_path.read_bytes()).decode("utf-8")
            return {
                "available": True,
                "image_base64": b64,
                "media_type": "image/png",
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    @router.get("/pc/workflows")
    async def list_pc_workflows() -> dict[str, Any]:
        """List all saved workflows and templates."""
        from plutus.gateway.server import get_state

        state = get_state()
        registry = state.get("tool_registry")

        if not registry:
            return {"workflows": [], "templates": []}

        pc_tool = registry.get("pc")
        if not pc_tool or not hasattr(pc_tool, "_workflow"):
            return {"workflows": [], "templates": []}

        return {
            "workflows": pc_tool._workflow.list_workflows(),
            "templates": pc_tool._workflow.list_templates(),
        }

    @router.get("/skills")
    async def list_skills(category: str | None = None) -> dict[str, Any]:
        """List all available skills."""
        from plutus.skills.registry import create_default_registry
        registry = create_default_registry()
        if category:
            skills = registry.find_by_category(category)
            return {"skills": [s.to_dict() for s in skills], "category": category}
        return {"skills": registry.list_all(), "categories": registry.list_categories()}

    @router.get("/skills/saved")
    async def list_saved_skills() -> dict[str, Any]:
        """List all user-created / AI-created skills (not built-in)."""
        from plutus.skills.creator import get_skill_creator
        creator = get_skill_creator()
        return {"skills": creator.list_saved_skills()}

    @router.get("/skills/{skill_name}")
    async def get_skill_detail(skill_name: str) -> dict[str, Any]:
        """Get details about a specific skill."""
        from plutus.skills.registry import create_default_registry
        registry = create_default_registry()
        skill = registry.get(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
        return skill.to_dict()

    @router.get("/pc/shortcuts")
    async def list_pc_shortcuts() -> dict[str, Any]:
        """List all available keyboard shortcuts."""
        from plutus.pc.keyboard import KeyboardController
        raw = KeyboardController.list_shortcuts()  # dict {name: keys}
        SHORTCUT_DESCRIPTIONS = {
            "copy": "Copy selection", "paste": "Paste from clipboard", "cut": "Cut selection",
            "undo": "Undo last action", "redo": "Redo last action", "save": "Save file",
            "save_as": "Save file as", "find": "Find in page", "replace": "Find and replace",
            "select_all": "Select all", "new_tab": "Open new tab", "close_tab": "Close current tab",
            "reopen_tab": "Reopen closed tab", "next_tab": "Switch to next tab",
            "prev_tab": "Switch to previous tab", "switch_window": "Switch between windows",
            "switch_app": "Switch between apps", "minimize": "Minimize all windows",
            "maximize": "Maximize window", "lock_screen": "Lock the screen",
            "screenshot": "Take screenshot", "screenshot_area": "Screenshot selected area",
            "task_manager": "Open task manager", "file_explorer": "Open file explorer",
            "terminal": "Open terminal", "address_bar": "Focus browser address bar",
            "refresh": "Refresh page", "hard_refresh": "Hard refresh (clear cache)",
            "dev_tools": "Open developer tools", "zoom_in": "Zoom in", "zoom_out": "Zoom out",
            "zoom_reset": "Reset zoom", "go_back": "Go back", "go_forward": "Go forward",
            "new_window": "Open new window", "close_window": "Close window",
            "spotlight": "Open search / spotlight",
        }
        shortcuts = [
            {"name": name, "keys": keys, "description": SHORTCUT_DESCRIPTIONS.get(name, name.replace("_", " ").title())}
            for name, keys in raw.items()
        ]
        return {"shortcuts": shortcuts}

    # ── Skill Import / Export / Community ──────────────────────────

    @router.get("/skills/{skill_name}/export")
    async def export_skill(skill_name: str) -> dict[str, Any]:
        """Export a skill as a shareable JSON package."""
        from plutus.skills.creator import get_skill_creator
        creator = get_skill_creator()
        source = creator.get_skill_source(skill_name)
        if not source:
            # Try built-in skills
            from plutus.skills.registry import create_default_registry
            registry = create_default_registry()
            skill = registry.get(skill_name)
            if not skill:
                raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
            source = skill.to_dict()

        # Add export metadata
        import time
        export_pkg = {
            "plutus_skill": True,
            "export_version": 1,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "skill": source,
        }
        return export_pkg

    class SkillImportRequest(BaseModel):
        skill_data: dict

    @router.post("/skills/import")
    async def import_skill(req: SkillImportRequest) -> dict[str, Any]:
        """Import a skill from a JSON package (uploaded by user or from community)."""
        from plutus.skills.creator import get_skill_creator
        from plutus.skills.registry import create_default_registry

        data = req.skill_data

        # Handle both raw skill dicts and export packages
        if data.get("plutus_skill") and "skill" in data:
            skill_dict = data["skill"]
        else:
            skill_dict = data

        # Validate required fields
        required = ["name", "description", "steps"]
        missing = [f for f in required if not skill_dict.get(f)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields: {', '.join(missing)}",
            )

        # Ensure defaults
        skill_dict.setdefault("app", skill_dict.get("name", "Custom"))
        skill_dict.setdefault("category", "custom")
        skill_dict.setdefault("triggers", [skill_dict["name"]])
        skill_dict.setdefault("required_params", [])
        skill_dict.setdefault("optional_params", [])
        skill_dict.setdefault("reason", "Imported by user")

        creator = get_skill_creator()
        registry = create_default_registry()
        success, msg, skill = creator.create_from_dict(skill_dict, registry=registry)

        if not success:
            raise HTTPException(status_code=400, detail=msg)

        return {
            "success": True,
            "message": msg,
            "skill_name": skill_dict["name"],
        }

    @router.delete("/skills/{skill_name}")
    async def delete_skill_endpoint(skill_name: str) -> dict[str, Any]:
        """Delete a user-created skill."""
        from plutus.skills.creator import get_skill_creator
        from plutus.skills.registry import create_default_registry
        creator = get_skill_creator()
        registry = create_default_registry()
        success, msg = creator.delete_skill(skill_name, registry=registry)
        if not success:
            raise HTTPException(status_code=404, detail=msg)
        return {"success": True, "message": msg}

    # ── Memory / Facts / Goals / Summaries ──────────────────────────

    @router.get("/memory/stats")
    async def get_memory_stats() -> dict[str, Any]:
        """Get overall memory statistics."""
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return {}
        return await memory.get_memory_stats()

    @router.get("/memory/facts")
    async def get_facts(category: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Get stored facts, optionally filtered by category."""
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return {"facts": [], "count": 0}

        facts = await memory.get_facts(category=category, limit=limit)
        return {"facts": facts, "count": len(facts)}

    @router.delete("/memory/facts/{fact_id}")
    async def delete_fact(fact_id: int) -> dict[str, str]:
        """Delete a stored fact."""
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            raise HTTPException(500, "Memory not initialized")

        await memory.delete_fact(fact_id)
        return {"message": "Fact deleted"}

    @router.get("/memory/goals")
    async def get_goals(conversation_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Get all goals."""
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return {"goals": [], "count": 0}

        goals = await memory.get_all_goals(conversation_id=conversation_id, limit=limit)
        return {"goals": goals, "count": len(goals)}

    @router.get("/memory/goals/active")
    async def get_active_goals(conversation_id: str | None = None) -> dict[str, Any]:
        """Get active goals."""
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return {"goals": [], "count": 0}

        goals = await memory.get_active_goals(conversation_id=conversation_id)
        return {"goals": goals, "count": len(goals)}

    @router.get("/conversations/{conv_id}/summary")
    async def get_conversation_summary(conv_id: str) -> dict[str, Any]:
        """Get the summary for a conversation."""
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return {"summary": None}

        summary = await memory.get_conversation_summary(conv_id)
        return {"summary": summary}

    @router.get("/conversations/{conv_id}/checkpoints")
    async def get_checkpoints(conv_id: str, limit: int = 10) -> dict[str, Any]:
        """Get checkpoints for a conversation."""
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return {"checkpoints": [], "count": 0}

        checkpoints = await memory.list_checkpoints(conv_id, limit=limit)
        return {"checkpoints": checkpoints, "count": len(checkpoints)}

    # ── Self-Improvement ────────────────────────────────────────────

    @router.get("/improvement/log")
    async def get_improvement_log(limit: int = 50) -> dict[str, Any]:
        """Get the self-improvement log — all skills created/updated/deleted by the agent."""
        try:
            from plutus.skills.creator import get_skill_creator
            creator = get_skill_creator()
            return {"log": creator.get_improvement_log(limit=limit)}
        except Exception as e:
            return {"log": [], "error": str(e)}

    @router.get("/improvement/stats")
    async def get_improvement_stats() -> dict[str, Any]:
        """Get self-improvement statistics."""
        try:
            from plutus.skills.creator import get_skill_creator
            creator = get_skill_creator()
            return creator.get_improvement_stats()
        except Exception as e:
            return {
                "total_created": 0, "total_updated": 0, "total_deleted": 0,
                "categories": {}, "recent": [], "error": str(e),
            }

    # ── Files ──────────────────────────────────────────────────────

    @router.get("/files")
    async def download_file(path: str) -> FileResponse:
        """Serve a file for download (used by the UI for attachment previews)."""
        from pathlib import Path as P

        file = P(path)
        if not file.exists() or not file.is_file():
            raise HTTPException(404, "File not found")

        # Security: only allow files under home dir or /tmp
        home = P.home()
        allowed = (home, P("/tmp"))
        try:
            resolved = file.resolve()
            if not any(
                str(resolved).startswith(str(d)) for d in allowed
            ):
                raise HTTPException(403, "Access denied")
        except Exception:
            raise HTTPException(403, "Access denied")

        return FileResponse(
            path=str(resolved),
            filename=file.name,
        )

    # ── Connectors ────────────────────────────────────────────────

    @router.get("/connectors")
    async def list_connectors() -> dict[str, Any]:
        """List all available connectors and their status."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            return {"connectors": []}
        return {"connectors": connector_mgr.list_all()}

    @router.get("/connectors/{name}")
    async def get_connector(name: str) -> dict[str, Any]:
        """Get a single connector's status and config."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            raise HTTPException(500, "Connector manager not initialized")
        connector = connector_mgr.get(name)
        if not connector:
            raise HTTPException(404, f"Connector '{name}' not found")
        return connector.status()

    @router.put("/connectors/{name}/config")
    async def update_connector_config(name: str, body: ConnectorConfigUpdate) -> dict[str, Any]:
        """Save configuration for a connector."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            raise HTTPException(500, "Connector manager not initialized")
        connector = connector_mgr.get(name)
        if not connector:
            raise HTTPException(404, f"Connector '{name}' not found")
        connector.save_config(body.config)
        return {"message": f"{connector.display_name} configuration saved", "status": connector.status()}

    @router.post("/connectors/{name}/test")
    async def test_connector(name: str) -> dict[str, Any]:
        """Test a connector's connection."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            raise HTTPException(500, "Connector manager not initialized")
        connector = connector_mgr.get(name)
        if not connector:
            raise HTTPException(404, f"Connector '{name}' not found")
        result = await connector.test_connection()
        # If test detected new config (e.g. chat_id), return updated status
        result["status"] = connector.status()
        return result

    @router.post("/connectors/{name}/send")
    async def send_connector_message(name: str, body: ConnectorSendMessage) -> dict[str, Any]:
        """Send a test message through a connector."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            raise HTTPException(500, "Connector manager not initialized")
        connector = connector_mgr.get(name)
        if not connector:
            raise HTTPException(404, f"Connector '{name}' not found")
        if not connector.is_configured:
            raise HTTPException(400, f"{connector.display_name} is not configured")
        return await connector.send_message(body.text, **body.params)

    @router.post("/connectors/{name}/start")
    async def start_connector(name: str) -> dict[str, Any]:
        """Start a connector's two-way messaging (polling + agent bridge)."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            raise HTTPException(500, "Connector manager not initialized")
        connector = connector_mgr.get(name)
        if not connector:
            raise HTTPException(404, f"Connector '{name}' not found")

        if name == "telegram":
            # Use the bridge for two-way Telegram messaging
            from plutus.connectors.telegram_bridge import get_telegram_bridge
            bridge = get_telegram_bridge()
            await bridge.start()
            return {
                "message": f"{connector.display_name} two-way messaging started — you can now chat with Plutus via Telegram",
                "status": connector.status(),
                "listening": True,
            }
        elif name == "discord":
            # Use the bridge for two-way Discord messaging
            from plutus.connectors.discord_bridge import get_discord_bridge
            bridge = get_discord_bridge()
            await bridge.start()
            return {
                "message": f"{connector.display_name} two-way messaging started — you can now chat with Plutus via Discord",
                "status": connector.status(),
                "listening": True,
            }
        else:
            await connector.start()
            return {"message": f"{connector.display_name} started", "status": connector.status()}

    @router.post("/connectors/{name}/stop")
    async def stop_connector(name: str) -> dict[str, Any]:
        """Stop a connector's two-way messaging."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            raise HTTPException(500, "Connector manager not initialized")
        connector = connector_mgr.get(name)
        if not connector:
            raise HTTPException(404, f"Connector '{name}' not found")

        if name == "telegram":
            from plutus.connectors.telegram_bridge import get_telegram_bridge
            bridge = get_telegram_bridge()
            await bridge.stop()
            return {
                "message": f"{connector.display_name} two-way messaging stopped",
                "status": connector.status(),
                "listening": False,
            }
        elif name == "discord":
            from plutus.connectors.discord_bridge import get_discord_bridge
            bridge = get_discord_bridge()
            await bridge.stop()
            return {
                "message": f"{connector.display_name} two-way messaging stopped",
                "status": connector.status(),
                "listening": False,
            }
        else:
            await connector.stop()
            return {"message": f"{connector.display_name} stopped", "status": connector.status()}

    @router.get("/connectors/{name}/bridge-status")
    async def get_bridge_status(name: str) -> dict[str, Any]:
        """Check if the two-way bridge is running for a connector."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        connector = connector_mgr.get(name) if connector_mgr else None
        auto_start = connector.auto_start if connector else False

        if name == "telegram":
            from plutus.connectors.telegram_bridge import get_telegram_bridge
            bridge = get_telegram_bridge()
            return {
                "listening": bridge.is_running,
                "processing": bridge._processing,
                "auto_start": auto_start,
            }
        elif name == "discord":
            from plutus.connectors.discord_bridge import get_discord_bridge
            bridge = get_discord_bridge()
            return {
                "listening": bridge.is_running,
                "processing": bridge._processing,
                "auto_start": auto_start,
            }
        return {"listening": False, "processing": False, "auto_start": auto_start}

    @router.put("/connectors/{name}/auto-start")
    async def set_connector_auto_start(name: str, body: ConnectorAutoStartUpdate) -> dict[str, Any]:
        """Enable or disable auto-start for a connector on Plutus launch."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            raise HTTPException(500, "Connector manager not initialized")
        connector = connector_mgr.get(name)
        if not connector:
            raise HTTPException(404, f"Connector '{name}' not found")
        if not connector.is_configured:
            raise HTTPException(
                400,
                f"{connector.display_name} must be configured before enabling auto-start",
            )

        connector.set_auto_start(body.auto_start)
        action = "enabled" if body.auto_start else "disabled"
        return {
            "message": f"Auto-start {action} for {connector.display_name}",
            "auto_start": connector.auto_start,
            "status": connector.status(),
        }

    @router.delete("/connectors/{name}")
    async def disconnect_connector(name: str) -> dict[str, Any]:
        """Remove a connector's configuration."""
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            raise HTTPException(500, "Connector manager not initialized")
        connector = connector_mgr.get(name)
        if not connector:
            raise HTTPException(404, f"Connector '{name}' not found")
        await connector.stop()
        connector.clear_config()
        return {"message": f"{connector.display_name} disconnected", "status": connector.status()}

    # ── WSL (Windows Subsystem for Linux) ─────────────────────

    @router.get("/wsl/status")
    async def get_wsl_status() -> dict[str, Any]:
        """Check WSL availability and configuration."""
        import platform
        import shutil

        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")

        is_windows = platform.system() == "Windows"
        wsl_binary = shutil.which("wsl") or shutil.which("wsl.exe") if is_windows else None
        wsl_installed = wsl_binary is not None

        return {
            "platform": platform.system(),
            "is_windows": is_windows,
            "wsl_installed": wsl_installed,
            "enabled": config.wsl.enabled if config else False,
            "setup_completed": config.wsl.setup_completed if config else False,
            "preferred_distro": config.wsl.preferred_distro if config else "Ubuntu",
        }

    @router.put("/wsl/enable")
    async def enable_wsl(body: dict[str, Any]) -> dict[str, str]:
        """Toggle WSL integration on/off."""
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        if not config:
            raise HTTPException(500, "Config not loaded")

        enabled = body.get("enabled", False)
        config.update({"wsl": {"enabled": enabled}})
        return {"message": f"WSL {'enabled' if enabled else 'disabled'}"}

    @router.post("/wsl/setup-complete")
    async def mark_wsl_setup_complete() -> dict[str, str]:
        """Mark WSL setup as finished after user completes the guide."""
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        if not config:
            raise HTTPException(500, "Config not loaded")

        config.update({"wsl": {"setup_completed": True, "enabled": True}})
        return {"message": "WSL setup completed"}

    @router.get("/wsl/setup-guide")
    async def get_wsl_setup_guide() -> dict[str, Any]:
        """Return step-by-step WSL setup instructions."""
        import platform
        import shutil

        is_windows = platform.system() == "Windows"

        if not is_windows:
            return {
                "needed": False,
                "message": (
                    "You're already running on Linux/macOS. "
                    "Plutus has full access to Linux tools natively — no WSL needed."
                ),
                "steps": [],
                "prerequisites": [],
                "troubleshooting": [],
            }

        wsl_binary = shutil.which("wsl") or shutil.which("wsl.exe")
        wsl_already_installed = wsl_binary is not None

        return {
            "needed": True,
            "wsl_detected": wsl_already_installed,
            "prerequisites": [
                {
                    "id": "windows_version",
                    "label": "Windows 10 (version 2004+) or Windows 11",
                    "detail": (
                        "WSL 2 requires Windows 10 May 2020 Update (build 19041) or later. "
                        "Press Win+R, type 'winver', and press Enter to check your version."
                    ),
                },
                {
                    "id": "admin_access",
                    "label": "Administrator access on this PC",
                    "detail": (
                        "You'll need to run one command as Administrator. If this is a "
                        "work computer, you may need to ask your IT department."
                    ),
                },
                {
                    "id": "disk_space",
                    "label": "~2 GB of free disk space",
                    "detail": (
                        "Ubuntu needs about 1.5-2 GB for the base installation. "
                        "Additional tools you install later will need more space."
                    ),
                },
                {
                    "id": "internet",
                    "label": "Internet connection",
                    "detail": (
                        "Required to download Ubuntu. The download is around 400-500 MB."
                    ),
                },
            ],
            "steps": [
                {
                    "id": "open_terminal",
                    "title": "Open Terminal as Administrator",
                    "description": (
                        "Right-click the Start button (Windows icon, bottom-left) and "
                        "select 'Terminal (Admin)' or 'PowerShell (Admin)' from the menu."
                    ),
                    "substeps": [
                        "Right-click the Start button (or press Win + X)",
                        "Click 'Terminal (Admin)' — on older Windows 10, look for 'Windows PowerShell (Admin)'",
                        "Click 'Yes' on the User Account Control popup",
                    ],
                    "command": None,
                    "note": (
                        "You must use an Administrator terminal for the install command. "
                        "A regular terminal will fail with a permissions error."
                    ),
                    "warning": None,
                },
                {
                    "id": "install_wsl",
                    "title": "Install WSL and Ubuntu",
                    "description": (
                        "In the Administrator terminal, paste this command and press Enter. "
                        "It will download and install everything automatically."
                    ),
                    "substeps": [
                        "Copy the command below (click the copy button)",
                        "Right-click in the terminal window to paste it",
                        "Press Enter and wait — this will take 2-10 minutes",
                        "You'll see progress messages as it downloads Ubuntu",
                    ],
                    "command": "wsl --install",
                    "note": (
                        "This single command enables the WSL feature, downloads the Linux kernel, "
                        "and installs Ubuntu. If you already have WSL with a different distro, "
                        "run 'wsl --install -d Ubuntu' to add Ubuntu specifically."
                    ),
                    "warning": None,
                },
                {
                    "id": "reboot",
                    "title": "Restart your computer",
                    "description": (
                        "Windows needs to restart to finish enabling WSL. "
                        "Save all your work, close your apps, and restart."
                    ),
                    "substeps": [
                        "Save any open documents and close your applications",
                        "Click Start > Power > Restart (don't use Shut Down)",
                        "Wait for your PC to fully restart and log back in",
                        "After logging in, wait 30-60 seconds — Ubuntu may auto-launch",
                    ],
                    "command": None,
                    "note": (
                        "A full restart is required — just logging out and back in won't work. "
                        "After rebooting, Plutus will remember your progress so you can "
                        "continue right where you left off."
                    ),
                    "warning": "Make sure to use Restart, not Shut Down. Shut Down on Windows "
                    "doesn't fully reset all system components due to Fast Startup.",
                },
                {
                    "id": "create_user",
                    "title": "Set up your Linux account",
                    "description": (
                        "After the restart, an Ubuntu terminal window should pop up automatically. "
                        "If it doesn't, open the Start menu and type 'Ubuntu' to launch it."
                    ),
                    "substeps": [
                        "Wait for the message 'Enter new UNIX username:'",
                        "Type a short, lowercase username (e.g. your first name) and press Enter",
                        "Type a password when prompted — characters won't appear as you type, that's normal",
                        "Re-type the password to confirm",
                    ],
                    "command": None,
                    "note": (
                        "This Linux username and password are completely separate from your "
                        "Windows account. They're only used inside the Linux environment. "
                        "Pick something short and easy to remember — you'll rarely need to type it."
                    ),
                    "warning": (
                        "When typing your password, nothing will appear on screen — no dots, "
                        "no asterisks, nothing. This is normal Linux behavior, not a bug. "
                        "Just type your password and press Enter."
                    ),
                },
                {
                    "id": "update_packages",
                    "title": "Update Linux packages",
                    "description": (
                        "While the Ubuntu terminal is still open, run this command to make sure "
                        "everything is up to date. This ensures Plutus has access to the "
                        "latest tools."
                    ),
                    "substeps": [
                        "Type the command below into the Ubuntu terminal",
                        "Enter your Linux password if prompted",
                        "Wait for it to finish — this takes 1-3 minutes",
                    ],
                    "command": "sudo apt update && sudo apt upgrade -y",
                    "note": (
                        "This downloads security patches and updates for the Linux system. "
                        "It's like running Windows Update but for your Linux environment."
                    ),
                    "warning": None,
                },
                {
                    "id": "verify",
                    "title": "Verify everything works",
                    "description": (
                        "Open a new PowerShell or Command Prompt window (regular, not Admin) "
                        "and run this command to confirm WSL is working."
                    ),
                    "substeps": [
                        "Open a regular (non-Admin) PowerShell or Terminal",
                        "Copy and paste the command below",
                        "You should see 'Hello from Linux!' printed",
                        "Then run the second command to see your Linux version",
                    ],
                    "command": "wsl echo 'Hello from Linux!'",
                    "command_verify": "wsl lsb_release -a",
                    "note": (
                        "If both commands work, WSL is fully set up and ready. "
                        "Plutus can now use Linux tools like apt, pip, Docker, Git, "
                        "compilers, and thousands of other programs."
                    ),
                    "warning": None,
                },
            ],
            "troubleshooting": [
                {
                    "id": "not_recognized",
                    "problem": "'wsl' is not recognized as a command",
                    "solution": (
                        "Your Windows version may be too old. Press Win+R, type 'winver', and check "
                        "that you're on Windows 10 version 2004 (build 19041) or later. "
                        "If not, update Windows first via Settings > Update & Security > Windows Update."
                    ),
                },
                {
                    "id": "virtualization",
                    "problem": "Error about virtualization or Hyper-V not enabled",
                    "solution": (
                        "You need to enable virtualization in your BIOS/UEFI. Restart your PC, "
                        "press F2/Del/F12 during boot (varies by manufacturer) to enter BIOS, "
                        "find 'Intel VT-x', 'AMD-V', or 'SVM Mode', enable it, save, and restart. "
                        "You can also try running this in an Admin PowerShell: "
                        "dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart"
                    ),
                },
                {
                    "id": "ubuntu_no_launch",
                    "problem": "Ubuntu doesn't open after restart",
                    "solution": (
                        "Open the Start menu, type 'Ubuntu', and click on it. "
                        "If it's not listed, open PowerShell as Admin and run: wsl --install -d Ubuntu. "
                        "If that says it's already installed, try: wsl --set-default Ubuntu"
                    ),
                },
                {
                    "id": "error_0x80370102",
                    "problem": "Error 0x80370102 — virtualization not enabled",
                    "solution": (
                        "This means hardware virtualization is disabled. Enter your BIOS settings "
                        "(restart and press F2/Del) and look for Intel VT-x or AMD SVM and enable it. "
                        "If you're in a virtual machine, enable nested virtualization in your VM settings."
                    ),
                },
                {
                    "id": "error_0x80040154",
                    "problem": "Error 0x80040154 — WSL feature not enabled",
                    "solution": (
                        "Run these two commands in Admin PowerShell, then restart:\n"
                        "dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart\n"
                        "dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart"
                    ),
                },
                {
                    "id": "slow_filesystem",
                    "problem": "WSL feels slow or file access is laggy",
                    "solution": (
                        "Store your project files inside the Linux filesystem (e.g. ~/projects/) "
                        "rather than accessing /mnt/c/. Cross-filesystem access is significantly "
                        "slower. You can also run 'wsl --update' to ensure you have the latest version."
                    ),
                },
            ],
        }

    # ── Updates ───────────────────────────────────────────────

    @router.get("/updates/check")
    async def check_for_update() -> dict[str, Any]:
        """Check PyPI for a newer version, with optional GitHub release notes."""
        import httpx

        from plutus import __version__
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        pypi_package = "plutus-ai"
        repo = "Crypt0nly/plutus"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Primary: check PyPI for the latest published version
                pypi_resp = await client.get(
                    f"https://pypi.org/pypi/{pypi_package}/json",
                )
                if pypi_resp.status_code == 404:
                    return {
                        "update_available": False,
                        "current_version": __version__,
                        "latest_version": __version__,
                    }
                pypi_resp.raise_for_status()
                pypi_data = pypi_resp.json()

            latest_version = pypi_data.get("info", {}).get("version", __version__)
            project_url = pypi_data.get("info", {}).get("project_url", "")
            update_available = _version_newer(latest_version, __version__)

            # Try to fetch GitHub release notes (best-effort, non-blocking)
            release_name = ""
            release_body = ""
            release_url = ""
            published_at = ""
            if update_available:
                try:
                    async with httpx.AsyncClient(timeout=5) as client:
                        gh_resp = await client.get(
                            f"https://api.github.com/repos/{repo}/releases/tags/v{latest_version}",
                            headers={"Accept": "application/vnd.github+json"},
                        )
                        if gh_resp.status_code == 200:
                            gh_data = gh_resp.json()
                            release_name = gh_data.get("name", "")
                            release_body = gh_data.get("body", "")
                            release_url = gh_data.get("html_url", "")
                            published_at = gh_data.get("published_at", "")
                except Exception:
                    pass  # GitHub notes are optional

            if not release_url:
                release_url = f"https://pypi.org/project/{pypi_package}/{latest_version}/"

            dismissed = (
                config.updates.dismissed_version == latest_version if config else False
            )

            return {
                "update_available": update_available,
                "dismissed": dismissed,
                "current_version": __version__,
                "latest_version": latest_version,
                "release_name": release_name,
                "release_notes": release_body,
                "release_url": release_url,
                "published_at": published_at,
            }
        except Exception as e:
            return {
                "update_available": False,
                "current_version": __version__,
                "latest_version": __version__,
                "error": str(e),
            }

    @router.post("/updates/dismiss")
    async def dismiss_update(body: dict[str, Any]) -> dict[str, str]:
        """Dismiss an update banner so it won't show again for this version."""
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        if not config:
            raise HTTPException(500, "Config not loaded")
        version = body.get("version", "")
        config.update({"updates": {"dismissed_version": version}})
        return {"message": f"Dismissed update v{version}"}

    @router.post("/updates/apply")
    async def apply_update() -> dict[str, Any]:
        """Upgrade Plutus and restart. Works for both pip and git installs."""
        import asyncio
        import sys

        from plutus import __version__

        async def run(
            cmd: list[str], cwd: str | None = None, timeout: float = 120,
        ) -> tuple[int, str, str]:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout,
                )
            except TimeoutError:
                proc.kill()
                return (1, "", "Command timed out")
            return (
                proc.returncode or 0,
                stdout.decode(errors="replace"),
                stderr.decode(errors="replace"),
            )

        def _clean_pip_stderr(stderr: str) -> str:
            """Strip noisy pip warnings so real errors are visible."""
            lines = stderr.splitlines()
            filtered = [
                ln for ln in lines
                if not ln.strip().startswith("WARNING: Ignoring invalid distribution")
                and not ln.strip().startswith("DEPRECATION:")
            ]
            return "\n".join(filtered).strip()

        from pathlib import Path

        import plutus as _pkg

        pkg_dir = Path(_pkg.__file__).resolve().parent.parent
        git_dir = pkg_dir / ".git"
        is_git = git_dir.is_dir()

        steps: list[dict[str, Any]] = []

        if is_git:
            # ── Git install: pull + editable reinstall ──
            code, out, err = await run(
                ["git", "pull", "--ff-only", "origin", "main"], cwd=str(pkg_dir),
            )
            steps.append({
                "step": "git_pull",
                "success": code == 0,
                "output": out.strip() or err.strip(),
            })
            if code != 0:
                return {
                    "success": False,
                    "error": f"git pull failed: {err.strip()}",
                    "steps": steps,
                    "previous_version": __version__,
                }

            pip_cmd = [sys.executable, "-m", "pip", "install", "-e", "."]
            code, out, err = await run(pip_cmd, cwd=str(pkg_dir))
            clean_err = _clean_pip_stderr(err)
            steps.append({
                "step": "pip_install",
                "success": code == 0,
                "output": (out.strip() or clean_err)[:500],
            })
            if code != 0:
                return {
                    "success": False,
                    "error": f"pip install failed: {clean_err[:300]}",
                    "steps": steps,
                    "previous_version": __version__,
                }
        else:
            # ── Pip install: just upgrade from PyPI ──
            pip_cmd = [
                sys.executable, "-m", "pip", "install",
                "--upgrade", "plutus-ai",
            ]
            code, out, err = await run(pip_cmd, timeout=180)
            clean_err = _clean_pip_stderr(err)
            steps.append({
                "step": "pip_upgrade",
                "success": code == 0,
                "output": (out.strip() or clean_err)[:500],
            })
            if code != 0:
                return {
                    "success": False,
                    "error": f"pip upgrade failed: {clean_err[:300]}",
                    "steps": steps,
                    "previous_version": __version__,
                }

        # Read new version from the freshly installed package
        new_version = __version__
        try:
            code, out, _err = await run(
                [sys.executable, "-c", "import plutus; print(plutus.__version__)"],
            )
            if code == 0 and out.strip():
                new_version = out.strip()
        except Exception:
            pass

        # Schedule a server restart so the new code is loaded
        async def _restart_server() -> None:
            await asyncio.sleep(1.5)  # let the response reach the client
            logger.info("Restarting Plutus after update...")
            # Re-exec with the original command line to preserve --host/--port/etc.
            os.execv(sys.executable, [sys.executable] + sys.argv)

        asyncio.get_event_loop().create_task(_restart_server())

        return {
            "success": True,
            "previous_version": __version__,
            "new_version": new_version,
            "steps": steps,
            "restart_required": True,
        }

    return router
