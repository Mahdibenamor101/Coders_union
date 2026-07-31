from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Alert
from ..s3 import presign_clip_url
from ..schemas import AlertOut, AlertReviewIn, ClipUrlOut
from .cameras import get_camera_or_404

router = APIRouter(prefix="/alerts", tags=["alerts"])


async def get_alert_or_404(alert_id: str, session: AsyncSession) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    camera_id: str | None = None,
    status: str | None = None,
    rule: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    query = select(Alert).order_by(Alert.created_at.desc()).limit(min(limit, 500))
    if camera_id is not None:
        await get_camera_or_404(camera_id, session)
        query = query.where(Alert.camera_id == camera_id)
    if status is not None:
        query = query.where(Alert.status == status)
    if rule is not None:
        query = query.where(Alert.rule == rule)
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: str, session: AsyncSession = Depends(get_session)):
    return await get_alert_or_404(alert_id, session)


@router.post("/{alert_id}/review", response_model=AlertOut)
async def review_alert(
    alert_id: str,
    payload: AlertReviewIn,
    session: AsyncSession = Depends(get_session),
):
    """Workflow de revue humaine : l'IA signale, l'humain décide (SPEC §1)."""
    alert = await get_alert_or_404(alert_id, session)
    alert.status = payload.status
    if payload.status == "pending":
        alert.reviewed_by = None
        alert.reviewed_at = None
    else:
        alert.reviewed_by = payload.reviewed_by
        alert.reviewed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(alert)
    return alert


@router.get("/{alert_id}/clip-url", response_model=ClipUrlOut)
async def get_alert_clip_url(
    alert_id: str, session: AsyncSession = Depends(get_session)
):
    alert = await get_alert_or_404(alert_id, session)
    if not alert.clip_object_key:
        raise HTTPException(status_code=409, detail="Alert has no clip")
    expires_in = 3600
    return ClipUrlOut(
        url=presign_clip_url(alert.clip_object_key, expires_in), expires_in=expires_in
    )


@router.get("/{alert_id}/thumbnail-url", response_model=ClipUrlOut)
async def get_alert_thumbnail_url(
    alert_id: str, session: AsyncSession = Depends(get_session)
):
    alert = await get_alert_or_404(alert_id, session)
    if not alert.thumbnail_object_key:
        raise HTTPException(status_code=409, detail="Alert has no thumbnail")
    expires_in = 3600
    return ClipUrlOut(
        url=presign_clip_url(alert.thumbnail_object_key, expires_in),
        expires_in=expires_in,
    )
