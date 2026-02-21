"""REST API routes for configuration, guardrails, history, and system status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from plutus.guardrails.tiers import Tier, get_tier_info


def create_router() -> APIRouter:
    router = APIRouter()

    # ── Status ──────────────────────────────────────────────

    @router.get("/status")
    async def get_status() -> dict[str, Any]:
        from plutus.gateway.server import get_state

        state = get_state()
        guardrails = state.get("guardrails")
        tool_registry = state.get("tool_registry")

        return {
            "version": "0.1.0",
            "status": "running",
            "guardrails": guardrails.get_status() if guardrails else None,
            "tools": tool_registry.list_tools() if tool_registry else [],
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

    class TierUpdate(BaseModel):
        tier: str

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

    class ToolOverrideUpdate(BaseModel):
        tool_name: str
        enabled: bool = True
        require_approval: bool = False

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

    class ApprovalDecision(BaseModel):
        approval_id: str
        approved: bool

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

    class ConfigUpdate(BaseModel):
        patch: dict[str, Any]

    @router.patch("/config")
    async def update_config(body: ConfigUpdate) -> dict[str, str]:
        from plutus.gateway.server import get_state

        state = get_state()
        config = state.get("config")
        config.update(body.patch)
        return {"message": "Config updated"}

    return router
