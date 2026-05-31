"""Request dependencies: current user (Supabase JWT) + repo handle.

Dev-lenient: if no token is presented (or auth isn't configured yet), we fall
back to a fixed demo user so the frontend/voice can build before auth lands.
When a Bearer token IS presented and SUPABASE_JWT_SECRET is set, we verify it.
"""
from typing import Optional

from fastapi import Header, HTTPException

from ..config import get_settings

DEMO_USER_ID = "00000000-0000-0000-0000-000000000000"


def get_current_user(authorization: Optional[str] = Header(default=None)) -> str:
    s = get_settings()
    if not authorization:
        return DEMO_USER_ID  # dev convenience; tighten before production

    token = authorization.removeprefix("Bearer ").strip()
    try:
        import jwt  # PyJWT (ships with supabase deps)

        if s.auth_enabled:
            claims = jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"],
                                audience="authenticated")
        else:
            claims = jwt.decode(token, options={"verify_signature": False})
        return claims.get("sub", DEMO_USER_ID)
    except ImportError:
        return DEMO_USER_ID
    except Exception as exc:  # invalid/expired token
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
