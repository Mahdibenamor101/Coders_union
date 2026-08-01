import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session


def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def encrypt_rtsp_url(url: str) -> str:
    return _fernet().encrypt(url.encode()).decode()


def decrypt_rtsp_url(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Clé de service (workers et intégrations internes) — pas les utilisateurs."""
    if not secrets.compare_digest(x_api_key, get_settings().api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )


# --- Auth utilisateurs (Phase 5) ---

ROLE_RANK = {"viewer": 0, "manager": 1, "admin": 2}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)
    ).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user) -> str:
    settings = get_settings()
    payload = {
        "sub": user.id,
        "tenant_id": user.tenant_id,
        "role": user.role,
        "email": user.email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


@dataclass(frozen=True)
class CurrentUser:
    id: str
    tenant_id: str
    email: str
    name: str
    role: str


async def get_current_user(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    from .models import User  # import tardif (cycle models → db)

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await session.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return CurrentUser(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )


def require_min_role(min_role: str):
    async def dependency(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=403, detail=f"Requires {min_role} role or above"
            )
        return user

    return dependency
