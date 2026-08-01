import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import record_audit
from ..config import get_settings
from ..db import get_session
from ..models import Camera, Clip, Store
from ..redis_client import camera_commands_channel, get_redis_client
from ..s3 import presign_clip_url
from ..schemas import ClipOut, ClipRequest, ClipUrlOut
from ..security import CurrentUser, get_current_user, require_min_role
from .cameras import get_tenant_camera

router = APIRouter(tags=["clips"])


async def get_tenant_clip(clip_id: str, tenant_id: str, session: AsyncSession) -> Clip:
    result = await session.execute(
        select(Clip)
        .join(Camera, Clip.camera_id == Camera.id)
        .join(Store, Camera.store_id == Store.id)
        .where(Clip.id == clip_id, Store.tenant_id == tenant_id)
    )
    clip = result.scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip


@router.post("/cameras/{camera_id}/clip", response_model=ClipOut, status_code=202)
async def request_clip(
    camera_id: str,
    payload: ClipRequest = ClipRequest(),
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis_client),
):
    """Demande l'extraction d'un clip autour d'un événement (défaut : maintenant)."""
    await get_tenant_camera(camera_id, user.tenant_id, session)
    settings = get_settings()
    event_ts = payload.event_ts if payload.event_ts is not None else time.time()

    clip = Clip(
        camera_id=camera_id,
        status="pending",
        requested_at=datetime.fromtimestamp(event_ts, tz=timezone.utc),
    )
    session.add(clip)
    await session.commit()
    await session.refresh(clip)

    await redis.publish(
        camera_commands_channel(camera_id),
        json.dumps(
            {
                "action": "extract_clip",
                "clip_id": clip.id,
                "event_ts": event_ts,
                "pre_seconds": settings.clip_pre_seconds,
                "post_seconds": settings.clip_post_seconds,
            }
        ),
    )
    return clip


@router.get("/cameras/{camera_id}/clips", response_model=list[ClipOut])
async def list_clips(
    camera_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_tenant_camera(camera_id, user.tenant_id, session)
    result = await session.execute(
        select(Clip).where(Clip.camera_id == camera_id).order_by(Clip.created_at)
    )
    return result.scalars().all()


@router.get("/clips/{clip_id}", response_model=ClipOut)
async def get_clip(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await get_tenant_clip(clip_id, user.tenant_id, session)


@router.get("/clips/{clip_id}/url", response_model=ClipUrlOut)
async def get_clip_url(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    clip = await get_tenant_clip(clip_id, user.tenant_id, session)
    if clip.status != "ready" or not clip.object_key:
        raise HTTPException(status_code=409, detail=f"Clip is {clip.status}, not ready")
    # RGPD : chaque visionnage de clip est tracé (qui, quoi, quand).
    await record_audit(session, user.tenant_id, user.id, "clip_viewed", clip.id)
    expires_in = 3600
    return ClipUrlOut(
        url=presign_clip_url(clip.object_key, expires_in), expires_in=expires_in
    )
