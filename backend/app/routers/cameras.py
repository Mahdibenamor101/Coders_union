import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing import camera_limit_for
from ..db import get_session
from ..models import Camera, Store, Tenant
from ..redis_client import camera_commands_channel, get_redis_client
from ..s3 import object_exists, presign_clip_url
from ..schemas import (
    CameraCreate,
    CameraOut,
    CameraSettingsIn,
    CameraUpdate,
    ZoneOut,
    ZonesUpdate,
)
from ..security import CurrentUser, encrypt_rtsp_url, get_current_user, require_min_role

router = APIRouter(prefix="/cameras", tags=["cameras"])


async def get_tenant_camera(
    camera_id: str, tenant_id: str, session: AsyncSession
) -> Camera:
    result = await session.execute(
        select(Camera)
        .join(Store, Camera.store_id == Store.id)
        .where(Camera.id == camera_id, Store.tenant_id == tenant_id)
    )
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.post("", response_model=CameraOut, status_code=201)
async def create_camera(
    payload: CameraCreate,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    store = await session.get(Store, payload.store_id)
    if store is None or store.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Store not found")

    # Plans facturés au nombre de caméras (SPEC §7 Phase 5).
    tenant = await session.get(Tenant, user.tenant_id)
    count = (
        await session.execute(
            select(func.count(Camera.id))
            .join(Store, Camera.store_id == Store.id)
            .where(Store.tenant_id == user.tenant_id)
        )
    ).scalar_one()
    limit = camera_limit_for(tenant.plan)
    if count >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Camera limit reached for plan '{tenant.plan}' ({limit}). Upgrade required.",
        )

    camera = Camera(
        store_id=payload.store_id,
        name=payload.name,
        rtsp_url_encrypted=encrypt_rtsp_url(payload.rtsp_url),
    )
    session.add(camera)
    await session.commit()
    await session.refresh(camera)
    return camera


@router.get("", response_model=list[CameraOut])
async def list_cameras(
    store_id: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(Camera)
        .join(Store, Camera.store_id == Store.id)
        .where(Store.tenant_id == user.tenant_id)
        .order_by(Camera.created_at)
    )
    if store_id is not None:
        query = query.where(Camera.store_id == store_id)
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/{camera_id}", response_model=CameraOut)
async def get_camera(
    camera_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await get_tenant_camera(camera_id, user.tenant_id, session)


@router.get("/{camera_id}/zones", response_model=list[ZoneOut])
async def get_zones(
    camera_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    camera = await get_tenant_camera(camera_id, user.tenant_id, session)
    return camera.zones


@router.put("/{camera_id}/zones", response_model=list[ZoneOut])
async def put_zones(
    camera_id: str,
    payload: ZonesUpdate,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis_client),
):
    """Remplace les zones de la caméra et notifie le worker (`update_zones`)."""
    camera = await get_tenant_camera(camera_id, user.tenant_id, session)
    zones = [
        {**zone.model_dump(), "id": zone.id or str(uuid.uuid4())}
        for zone in payload.zones
    ]
    camera.zones = zones
    await session.commit()
    await redis.publish(
        camera_commands_channel(camera_id),
        json.dumps({"action": "update_zones", "zones": zones}),
    )
    return zones


@router.get("/{camera_id}/snapshot-url")
async def get_snapshot_url(
    camera_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Dernière image publiée par le worker (fond de l'éditeur visuel de zones)."""
    await get_tenant_camera(camera_id, user.tenant_id, session)
    object_key = f"{camera_id}/snapshot.jpg"
    if not object_exists(object_key):
        raise HTTPException(
            status_code=409, detail="No snapshot yet (worker offline?)"
        )
    return {"url": presign_clip_url(object_key, 300), "expires_in": 300}


@router.get("/{camera_id}/settings")
async def get_camera_settings(
    camera_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    camera = await get_tenant_camera(camera_id, user.tenant_id, session)
    return camera.settings or {}


@router.put("/{camera_id}/settings")
async def put_settings(
    camera_id: str,
    payload: CameraSettingsIn,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis_client),
) -> dict:
    """Remplace les seuils du moteur de règles et notifie le worker (`update_settings`)."""
    camera = await get_tenant_camera(camera_id, user.tenant_id, session)
    settings = payload.model_dump(exclude_unset=True, exclude_none=True)
    camera.settings = settings
    await session.commit()
    await redis.publish(
        camera_commands_channel(camera_id),
        json.dumps({"action": "update_settings", "settings": settings}),
    )
    return settings


@router.patch("/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    camera = await get_tenant_camera(camera_id, user.tenant_id, session)
    data = payload.model_dump(exclude_unset=True)
    rtsp_url = data.pop("rtsp_url", None)
    if rtsp_url is not None:
        camera.rtsp_url_encrypted = encrypt_rtsp_url(rtsp_url)
    for field, value in data.items():
        setattr(camera, field, value)
    await session.commit()
    await session.refresh(camera)
    return camera


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(
    camera_id: str,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    camera = await get_tenant_camera(camera_id, user.tenant_id, session)
    await session.delete(camera)
    await session.commit()
