"""Endpoints de service pour les workers vidéo — protégés par la clé API (X-API-Key).

Les workers sont des composants système : pas de scoping tenant ici, mais la clé
de service ne doit jamais être exposée aux utilisateurs.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Camera, Store, Tenant
from ..schemas import StreamUrlOut, ZoneOut
from ..security import decrypt_rtsp_url

router = APIRouter(prefix="/internal/cameras", tags=["internal"])


async def _camera_or_404(camera_id: str, session: AsyncSession) -> Camera:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.get("")
async def list_cameras(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Toutes les caméras — utilisé par le superviseur pour lancer un worker par flux."""
    result = await session.execute(select(Camera).order_by(Camera.created_at))
    return [
        {"id": camera.id, "name": camera.name} for camera in result.scalars().all()
    ]


@router.get("/{camera_id}/stream-url", response_model=StreamUrlOut)
async def get_stream_url(camera_id: str, session: AsyncSession = Depends(get_session)):
    camera = await _camera_or_404(camera_id, session)
    return StreamUrlOut(rtsp_url=decrypt_rtsp_url(camera.rtsp_url_encrypted))


@router.get("/{camera_id}/zones", response_model=list[ZoneOut])
async def get_zones(camera_id: str, session: AsyncSession = Depends(get_session)):
    camera = await _camera_or_404(camera_id, session)
    return camera.zones


@router.get("/{camera_id}/settings")
async def get_settings(
    camera_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Seuils de la caméra, enrichis des réglages tenant (vérification multimodale)."""
    camera = await _camera_or_404(camera_id, session)
    settings = dict(camera.settings or {})
    store = await session.get(Store, camera.store_id)
    tenant = await session.get(Tenant, store.tenant_id) if store else None
    if tenant is not None:
        settings["multimodal_verification"] = tenant.multimodal_verification
    return settings
