"""REST API routes for configuration, guardrails, history, and system status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from plutus.guardrails.tiers import Tier, get_tier_info


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


def create_router() -> APIRouter:
    router = APIRouter()

    # ── Status ──────────────────────────────────────────────

    @router.get("/status")
    async def get_status() -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        guardrails = state.get("guardrails")
        tool_registry = state.get("tool_registry")
        agent = state.get("agent")
        heartbeat = state.get("heartbeat")

        return {
            "version": "0.1.0",
            "status": "running",
            "key_configured": agent.key_configured if agent else False,
            "guardrails": guardrails.get_status() if guardrails else None,
            "tools": tool_registry.list_tools() if tool_registry else [],
            "heartbeat": heartbeat.status() if heartbeat else None,
            "planner_enabled": state.get("config", {}).planner.enabled
            if state.get("config")
            else False,
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
    async def list_conversations(limit: int = 20) -> list[dict[str, Any]]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if not agent:
            return []
        return await agent.conversation.list_conversations(limit)

    @router.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: str) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        agent = state.get("agent")
        if agent:
            await agent.conversation.delete_conversation(conv_id)
        return {"message": "Deleted"}

    @router.get("/conversations/{conv_id}/messages")
    async def get_messages(conv_id: str) -> list[dict[str, Any]]:
        from plutus.gateway.server import get_state

        state = get_state()
        memory = state.get("memory")
        if not memory:
            return []
        return await memory.get_messages(conv_id)

    # ── Tools ───────────────────────────────────────────────

    @router.get("/tools")
    async def list_tools() -> list[dict[str, Any]]:
        from plutus.gateway.server import get_state

        state = get_state()
        registry = state.get("tool_registry")
        return registry.get_tool_info() if registry else []

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
        return {"message": "Config updated"}

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

    return router
