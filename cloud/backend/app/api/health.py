from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_session

router = APIRouter()


@router.get("")
async def health_check():
    return {"status": "healthy", "service": "plutus-cloud"}


@router.get("/status")
async def status(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Returns the status fields expected by the local UI's App.tsx.
    In cloud mode, the API key is always 'configured' (Clerk handles auth).
    Onboarding is tracked per-user via the User.settings JSON column.
    New users have onboarding_completed=False so the wizard is shown.
    """
    from app.models.user import User

    user_row = await db.get(User, user["user_id"])
    settings: dict = (user_row.settings or {}) if user_row else {}
    # New users have no settings entry → onboarding_completed defaults to False
    onboarding_completed = settings.get("onboarding_completed", False)

    return {
        "status": "ok",
        "key_configured": True,
        "onboarding_completed": onboarding_completed,
        "mode": "cloud",
        "user_id": user.get("sub"),
    }
