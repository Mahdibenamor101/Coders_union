from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Store
from ..schemas import StoreCreate, StoreOut, StoreUpdate
from ..security import CurrentUser, get_current_user, require_min_role

router = APIRouter(prefix="/stores", tags=["stores"])


async def get_tenant_store(
    store_id: str, tenant_id: str, session: AsyncSession
) -> Store:
    store = await session.get(Store, store_id)
    if store is None or store.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@router.post("", response_model=StoreOut, status_code=201)
async def create_store(
    payload: StoreCreate,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    store = Store(tenant_id=user.tenant_id, **payload.model_dump())
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return store


@router.get("", response_model=list[StoreOut])
async def list_stores(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Store)
        .where(Store.tenant_id == user.tenant_id)
        .order_by(Store.created_at)
    )
    return result.scalars().all()


@router.get("/{store_id}", response_model=StoreOut)
async def get_store(
    store_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await get_tenant_store(store_id, user.tenant_id, session)


@router.patch("/{store_id}", response_model=StoreOut)
async def update_store(
    store_id: str,
    payload: StoreUpdate,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    store = await get_tenant_store(store_id, user.tenant_id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(store, field, value)
    await session.commit()
    await session.refresh(store)
    return store


@router.delete("/{store_id}", status_code=204)
async def delete_store(
    store_id: str,
    user: CurrentUser = Depends(require_min_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    store = await get_tenant_store(store_id, user.tenant_id, session)
    await session.delete(store)
    await session.commit()
