import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import Clip
from ..redis_client import camera_commands_channel, get_redis_client
from ..s3 import presign_clip_url
from ..schemas import ClipOut, ClipRequest, ClipUrlOut
from .cameras import get_camera_or_404

router = APIRouter(tags=["clips"])


@router.post("/cameras/{camera_id}/clip", response_model=ClipOut, status_code=202)
async def request_clip(
    camera_id: str,
    payload: ClipRequest = ClipRequest(),
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis_client),
):
    """Demande l'extraction d'un clip autour d'un événement (défaut : maintenant).

    Le worker attend la fin de la fenêtre « après », assemble le clip depuis son
    buffer circulaire, l'uploade sur MinIO puis publie `clip_ready` — le statut
    passe alors de `pending` à `ready`.
    """
    await get_camera_or_404(camera_id, session)
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
async def list_clips(camera_id: str, session: AsyncSession = Depends(get_session)):
    await get_camera_or_404(camera_id, session)
    result = await session.execute(
        select(Clip).where(Clip.camera_id == camera_id).order_by(Clip.created_at)
    )
    return result.scalars().all()


@router.get("/clips/{clip_id}", response_model=ClipOut)
async def get_clip(clip_id: str, session: AsyncSession = Depends(get_session)):
    clip = await session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip


@router.get("/clips/{clip_id}/url", response_model=ClipUrlOut)
async def get_clip_url(clip_id: str, session: AsyncSession = Depends(get_session)):
    clip = await session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.status != "ready" or not clip.object_key:
        raise HTTPException(status_code=409, detail=f"Clip is {clip.status}, not ready")
    expires_in = 3600
    return ClipUrlOut(
        url=presign_clip_url(clip.object_key, expires_in), expires_in=expires_in
    )
