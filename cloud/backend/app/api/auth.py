import base64

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

router = APIRouter()
security = HTTPBearer()

# Cache JWKS keys
_jwks_cache: dict = {}


def _get_jwks_url() -> str:
    """
    Derive the instance-specific JWKS URL from the Clerk publishable key.

    Clerk publishable keys encode the instance frontend API host in base64:
      pk_test_<base64(host + "$")>  ->  https://<host>/.well-known/jwks.json

    This URL is publicly accessible without authentication, unlike the
    generic https://api.clerk.com/v1/jwks endpoint which requires the
    secret key as a Bearer token.
    """
    pk = settings.clerk_publishable_key
    if pk:
        try:
            # Strip the "pk_test_" or "pk_live_" prefix
            b64_part = pk.split("_", 2)[-1]
            # Add padding and decode
            padded = b64_part + "=" * (4 - len(b64_part) % 4)
            host = base64.urlsafe_b64decode(padded).decode().rstrip("$")
            if host:
                return f"https://{host}/.well-known/jwks.json"
        except Exception:
            pass
    # Fallback: use the generic endpoint (requires secret key auth header)
    return settings.clerk_jwks_url


async def get_clerk_jwks() -> dict:
    """Fetch Clerk's JWKS for token verification."""
    global _jwks_cache
    if not _jwks_cache:
        jwks_url = _get_jwks_url()
        async with httpx.AsyncClient() as client:
            headers = {}
            # Generic api.clerk.com endpoint requires the secret key
            if "api.clerk.com" in jwks_url and settings.clerk_secret_key:
                headers["Authorization"] = f"Bearer {settings.clerk_secret_key}"
            resp = await client.get(jwks_url, headers=headers)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Verify Clerk JWT and extract user info."""
    token = credentials.credentials
    try:
        jwks = await get_clerk_jwks()
        # Get the signing key from JWKS
        header = jwt.get_unverified_header(token)
        key = None
        for k in jwks.get("keys", []):
            if k["kid"] == header["kid"]:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                break
        if not key:
            # JWKS cache may be stale — clear it and retry once
            _jwks_cache.clear()
            jwks = await get_clerk_jwks()
            for k in jwks.get("keys", []):
                if k["kid"] == header["kid"]:
                    key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                    break
        if not key:
            raise HTTPException(status_code=401, detail="Invalid token signing key")

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return {
            "sub": payload.get("sub"),
            "user_id": payload.get("sub"),
            "email": payload.get("email"),
            "session_id": payload.get("sid"),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return the current authenticated user."""
    return {"user": user}
