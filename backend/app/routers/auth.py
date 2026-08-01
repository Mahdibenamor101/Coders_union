import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import record_audit
from ..config import get_settings
from ..db import get_session
from ..models import Invitation, Tenant, User
from ..schemas import (
    InvitationAcceptIn,
    InvitationCreate,
    InvitationOut,
    LoginIn,
    RegisterIn,
    TokenOut,
    UserOut,
)
from ..security import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    require_min_role,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

INVITATION_TTL_DAYS = 7


def _token_response(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user), user=UserOut.model_validate(user)
    )


@router.post("/auth/register", response_model=TokenOut, status_code=201)
async def register(payload: RegisterIn, session: AsyncSession = Depends(get_session)):
    """Onboarding : crée l'organisation et son premier utilisateur (admin)."""
    email = payload.email.lower()
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    tenant = Tenant(name=payload.company_name)
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role="admin",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    await record_audit(session, tenant.id, user.id, "register", email)
    return _token_response(user)


@router.post("/auth/login", response_model=TokenOut)
async def login(payload: LoginIn, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(User).where(User.email == payload.email.lower())
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    await record_audit(session, user.tenant_id, user.id, "login", user.email)
    return _token_response(user)


@router.get("/auth/me")
async def me(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = await session.get(Tenant, user.tenant_id)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "plan": tenant.plan,
            "retention_days": tenant.retention_days,
        },
    }


@router.get("/users", response_model=list[UserOut])
async def list_users(
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(User).where(User.tenant_id == user.tenant_id).order_by(User.created_at)
    )
    return result.scalars().all()


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    if user_id == user.id:
        raise HTTPException(status_code=409, detail="Cannot delete yourself")
    target = await session.get(User, user_id)
    if target is None or target.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(target)
    await session.commit()
    await record_audit(session, user.tenant_id, user.id, "user_deleted", target.email)


@router.post("/invitations", status_code=201)
async def create_invitation(
    payload: InvitationCreate,
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    email = payload.email.lower()
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    invitation = Invitation(
        tenant_id=user.tenant_id,
        email=email,
        role=payload.role,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_TTL_DAYS),
    )
    session.add(invitation)
    await session.commit()
    await record_audit(session, user.tenant_id, user.id, "invitation_created", email)

    invite_url = f"{get_settings().frontend_url}/invitation?token={invitation.token}"
    # Pas de SMTP en dev : le lien est retourné à l'admin (et loggé) ; brancher
    # un envoi d'email ici en production.
    logger.info("invitation for %s: %s", email, invite_url)
    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.role,
        "invite_url": invite_url,
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.get("/invitations", response_model=list[InvitationOut])
async def list_invitations(
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Invitation)
        .where(Invitation.tenant_id == user.tenant_id)
        .order_by(Invitation.created_at.desc())
    )
    return result.scalars().all()


@router.post("/auth/invitations/accept", response_model=TokenOut, status_code=201)
async def accept_invitation(
    payload: InvitationAcceptIn, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Invitation).where(Invitation.token == payload.token)
    )
    invitation = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.expires_at.replace(tzinfo=timezone.utc) < now
    ):
        raise HTTPException(status_code=404, detail="Invalid or expired invitation")

    existing = await session.execute(
        select(User).where(User.email == invitation.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        tenant_id=invitation.tenant_id,
        email=invitation.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=invitation.role,
    )
    invitation.accepted_at = now
    session.add(user)
    await session.commit()
    await session.refresh(user)
    await record_audit(
        session, user.tenant_id, user.id, "invitation_accepted", user.email
    )
    return _token_response(user)
