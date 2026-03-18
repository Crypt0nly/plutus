from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
from app.database import get_session
from app.models.conversation import Conversation, Message
from app.api.auth import get_current_user
from app.agent.runtime import CloudAgentRuntime

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str

@router.post("/", response_model=ChatResponse)
async def send_message(
    body: ChatRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    runtime = CloudAgentRuntime(user_id=user["user_id"], session=db)
    result = await runtime.process_message(
        message=body.message,
        conversation_id=body.conversation_id,
    )
    return ChatResponse(response=result["response"], conversation_id=result["conversation_id"])

@router.get("/history")
async def get_history(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user["user_id"])
        .order_by(Conversation.updated_at.desc())
    )
    conversations = result.scalars().all()
    return {"conversations": [c.__dict__ for c in conversations]}

@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user["user_id"]:
        raise HTTPException(status_code=404, detail="Conversation not found")
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return {"conversation": conv.__dict__, "messages": [m.__dict__ for m in messages]}

@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user["user_id"]:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await db.delete(conv)
    await db.commit()
    return {"deleted": conversation_id}
