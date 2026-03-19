from fastapi import APIRouter, Depends

from app.api.auth import get_current_user

router = APIRouter()


@router.get("")
async def health_check():
    return {"status": "healthy", "service": "plutus-cloud"}


@router.get("/status")
async def status(user=Depends(get_current_user)):
    """
    Returns the status fields expected by the local UI's App.tsx.
    In cloud mode, the API key is always 'configured' (Clerk handles auth),
    and onboarding is always completed (no local setup needed).
    """
    return {
        "status": "ok",
        "key_configured": True,
        "onboarding_completed": True,
        "mode": "cloud",
        "user_id": user.get("sub"),
    }
