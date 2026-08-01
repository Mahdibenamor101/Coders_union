from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import record_audit
from ..db import get_session
from ..models import Alert, Camera, Store
from ..s3 import delete_object, presign_clip_url
from ..schemas import AlertOut, AlertReviewIn, ClipUrlOut
from ..security import CurrentUser, get_current_user, require_min_role
from .cameras import get_tenant_camera

router = APIRouter(prefix="/alerts", tags=["alerts"])


async def get_tenant_alert(
    alert_id: str, tenant_id: str, session: AsyncSession
) -> Alert:
    result = await session.execute(
        select(Alert)
        .join(Camera, Alert.camera_id == Camera.id)
        .join(Store, Camera.store_id == Store.id)
        .where(Alert.id == alert_id, Store.tenant_id == tenant_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    camera_id: str | None = None,
    status: str | None = None,
    rule: str | None = None,
    limit: int = 100,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(Alert)
        .join(Camera, Alert.camera_id == Camera.id)
        .join(Store, Camera.store_id == Store.id)
        .where(Store.tenant_id == user.tenant_id)
        .order_by(Alert.created_at.desc())
        .limit(min(limit, 500))
    )
    if camera_id is not None:
        await get_tenant_camera(camera_id, user.tenant_id, session)
        query = query.where(Alert.camera_id == camera_id)
    if status is not None:
        query = query.where(Alert.status == status)
    if rule is not None:
        query = query.where(Alert.rule == rule)
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await get_tenant_alert(alert_id, user.tenant_id, session)


@router.post("/{alert_id}/review", response_model=AlertOut)
async def review_alert(
    alert_id: str,
    payload: AlertReviewIn,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    """Workflow de revue humaine : l'IA signale, l'humain décide (SPEC §1)."""
    alert = await get_tenant_alert(alert_id, user.tenant_id, session)
    alert.status = payload.status
    if payload.status == "pending":
        alert.reviewed_by = None
        alert.reviewed_at = None
    else:
        alert.reviewed_by = user.name or user.email
        alert.reviewed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(alert)
    await record_audit(
        session, user.tenant_id, user.id, "alert_reviewed", f"{alert.id}:{payload.status}"
    )
    return alert


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: str,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    """Suppression manuelle (RGPD) : la ligne et ses médias S3."""
    alert = await get_tenant_alert(alert_id, user.tenant_id, session)
    for key in (alert.clip_object_key, alert.thumbnail_object_key):
        if key:
            delete_object(key)
    await session.delete(alert)
    await session.commit()
    await record_audit(session, user.tenant_id, user.id, "alert_deleted", alert_id)


async def _media_url(
    alert_id: str, attribute: str, user: CurrentUser, session: AsyncSession
) -> ClipUrlOut:
    alert = await get_tenant_alert(alert_id, user.tenant_id, session)
    object_key = getattr(alert, attribute)
    if not object_key:
        raise HTTPException(status_code=409, detail="Media not available")
    # RGPD : chaque visionnage est tracé.
    await record_audit(session, user.tenant_id, user.id, "clip_viewed", alert.id)
    expires_in = 3600
    return ClipUrlOut(url=presign_clip_url(object_key, expires_in), expires_in=expires_in)


@router.get("/{alert_id}/clip-url", response_model=ClipUrlOut)
async def get_alert_clip_url(
    alert_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _media_url(alert_id, "clip_object_key", user, session)


@router.get("/{alert_id}/thumbnail-url", response_model=ClipUrlOut)
async def get_alert_thumbnail_url(
    alert_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _media_url(alert_id, "thumbnail_object_key", user, session)
