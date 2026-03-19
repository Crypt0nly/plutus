from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_session
from app.services.agent_service import AgentService

router = APIRouter()


@router.get("/status")
async def agent_status(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    state = await svc.get_agent_state(user["sub"])
    return {
        "status": state.status if state else "not_initialized",
        "user_id": user["sub"],
    }


@router.post("/restart")
async def restart_agent(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    state = await svc.ensure_agent_state(user["sub"])
    state.status = "idle"
    await session.commit()
    return {"status": "restarted"}


@router.get("/memory")
async def list_memory(
    category: str = Query(None),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    memories = await svc.recall_memories(user["sub"], category=category)
    return {
        "memories": [
            {
                "id": m.id,
                "category": m.category,
                "content": m.content,
                "created_at": str(m.created_at),
            }
            for m in memories
        ]
    }


@router.post("/memory")
async def save_memory(
    payload: dict,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    mem = await svc.save_memory(
        user["sub"],
        category=payload.get("category", "general"),
        content=payload["content"],
    )
    return {"id": mem.id, "category": mem.category, "content": mem.content}


@router.delete("/memory/{fact_id}")
async def delete_memory(
    fact_id: int,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import delete as sql_delete

    from app.models.agent_state import Memory

    await session.execute(
        sql_delete(Memory).where(Memory.id == fact_id, Memory.user_id == user["sub"])
    )
    await session.commit()
    return {"deleted": fact_id}


@router.get("/skills")
async def list_skills(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    skills = await svc.list_skills(user["sub"])
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "skill_type": s.skill_type,
        }
        for s in skills
    ]


@router.get("/scheduled-tasks")
async def list_scheduled_tasks(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    tasks = await svc.list_scheduled_tasks(user["sub"])
    return {
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "schedule": t.schedule,
                "prompt": t.prompt,
            }
            for t in tasks
        ]
    }


@router.post("/scheduled-tasks")
async def create_scheduled_task(
    payload: dict,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    task = await svc.create_scheduled_task(
        user["sub"],
        name=payload["name"],
        schedule=payload["schedule"],
        prompt=payload["prompt"],
        description=payload.get("description", ""),
    )
    return {"id": task.id, "name": task.name, "schedule": task.schedule}
