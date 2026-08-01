from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Tenant
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
):
    tenant = await session.get(Tenant, user.tenant_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    await session.commit()
    await session.refresh(tenant)
    return tenant
