from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Store, Tenant
from ..schemas import StoreCreate, StoreOut, StoreUpdate

router = APIRouter(prefix="/stores", tags=["stores"])


async def get_store_or_404(store_id: str, session: AsyncSession) -> Store:
    store = await session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@router.post("", response_model=StoreOut, status_code=201)
async def create_store(
    payload: StoreCreate, session: AsyncSession = Depends(get_session)
):
    if await session.get(Tenant, payload.tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    store = Store(**payload.model_dump())
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return store


@router.get("", response_model=list[StoreOut])
async def list_stores(
    tenant_id: str | None = None, session: AsyncSession = Depends(get_session)
):
    query = select(Store).order_by(Store.created_at)
    if tenant_id is not None:
        query = query.where(Store.tenant_id == tenant_id)
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/{store_id}", response_model=StoreOut)
async def get_store(store_id: str, session: AsyncSession = Depends(get_session)):
    return await get_store_or_404(store_id, session)


@router.patch("/{store_id}", response_model=StoreOut)
async def update_store(
    store_id: str, payload: StoreUpdate, session: AsyncSession = Depends(get_session)
):
    store = await get_store_or_404(store_id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(store, field, value)
    await session.commit()
    await session.refresh(store)
    return store


@router.delete("/{store_id}", status_code=204)
async def delete_store(store_id: str, session: AsyncSession = Depends(get_session)):
    store = await get_store_or_404(store_id, session)
    await session.delete(store)
    await session.commit()
