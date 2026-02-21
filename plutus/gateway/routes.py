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


class CreateCustomToolRequest(BaseModel):
    tool_name: str
    description: str = ""
    code: str
    register: bool = True


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

    # ── Workers / Subprocesses ──────────────────────────────

    @router.get("/workers")
    async def get_workers() -> dict[str, Any]:
        """Get active workers and recent results from the subprocess manager."""
        from plutus.gateway.server import get_state

        state = get_state()
        registry = state.get("tool_registry")

        if not registry:
            return {"active": [], "recent": [], "stats": {}}

        # Get the subprocess manager from the subprocess tool
        sub_tool = registry.get("subprocess")
        if not sub_tool or not hasattr(sub_tool, "_manager"):
            return {"active": [], "recent": [], "stats": {}}

        mgr = sub_tool._manager
        active = mgr.list_active()
        recent = mgr.list_results(limit=50)

        # Compute stats
        total = len(recent)
        completed = sum(1 for r in recent if r.get("status") == "completed")
        failed = sum(1 for r in recent if r.get("status") == "failed")
        avg_duration = sum(r.get("duration", 0) for r in recent) / max(total, 1)

        return {
            "active": active,
            "recent": recent,
            "stats": {
                "total_tasks": total,
                "completed": completed,
                "failed": failed,
                "active_count": len(active),
                "avg_duration": round(avg_duration, 3),
                "max_workers": mgr.max_workers,
            },
        }

    @router.post("/workers/{task_id}/cancel")
    async def cancel_worker(task_id: str) -> dict[str, Any]:
        """Cancel a running worker."""
        from plutus.gateway.server import get_state

        state = get_state()
        registry = state.get("tool_registry")

        if not registry:
            raise HTTPException(500, "Registry not initialized")

        sub_tool = registry.get("subprocess")
        if not sub_tool or not hasattr(sub_tool, "_manager"):
            raise HTTPException(500, "Subprocess manager not available")

        cancelled = await sub_tool._manager.cancel(task_id)
        if not cancelled:
            raise HTTPException(404, f"Worker {task_id} not found or not running")

        return {"cancelled": True, "task_id": task_id}

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
        if body.register:
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

    return router
