from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Tenant
from ..schemas import TenantCreate, TenantOut, TenantUpdate

router = APIRouter(prefix="/tenants", tags=["tenants"])


async def get_tenant_or_404(tenant_id: str, session: AsyncSession) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    payload: TenantCreate, session: AsyncSession = Depends(get_session)
):
    tenant = Tenant(**payload.model_dump())
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


@router.get("", response_model=list[TenantOut])
async def list_tenants(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Tenant).order_by(Tenant.created_at))
    return result.scalars().all()


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(tenant_id: str, session: AsyncSession = Depends(get_session)):
    return await get_tenant_or_404(tenant_id, session)


@router.patch("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: str, payload: TenantUpdate, session: AsyncSession = Depends(get_session)
):
    tenant = await get_tenant_or_404(tenant_id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    await session.commit()
    await session.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(tenant_id: str, session: AsyncSession = Depends(get_session)):
    tenant = await get_tenant_or_404(tenant_id, session)
    await session.delete(tenant)
    await session.commit()
