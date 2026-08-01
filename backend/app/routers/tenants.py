import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Camera, Store, Tenant
from ..redis_client import camera_commands_channel, get_redis_client
from ..schemas import TenantOut, TenantUpdateMe
from ..security import CurrentUser, get_current_user, require_min_role

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantOut)
async def get_my_tenant(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await session.get(Tenant, user.tenant_id)


@router.patch("", response_model=TenantOut)
async def update_my_tenant(
    payload: TenantUpdateMe,
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis_client),
):
    tenant = await session.get(Tenant, user.tenant_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(tenant, field, value)
    await session.commit()
    await session.refresh(tenant)

    # Le réglage de vérification multimodale est appliqué à chaud par les workers
    # de toutes les caméras du tenant.
    if "multimodal_verification" in data:
        cameras = (
            await session.execute(
                select(Camera.id)
                .join(Store, Camera.store_id == Store.id)
                .where(Store.tenant_id == tenant.id)
            )
        ).scalars().all()
        command = json.dumps(
            {
                "action": "update_settings",
                "settings": {
                    "multimodal_verification": tenant.multimodal_verification
                },
            }
        )
        for camera_id in cameras:
            await redis.publish(camera_commands_channel(camera_id), command)

    return tenant
