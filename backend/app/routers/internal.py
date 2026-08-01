"""Endpoints de service pour les workers vidéo — protégés par la clé API (X-API-Key).

Les workers sont des composants système : pas de scoping tenant ici, mais la clé
de service ne doit jamais être exposée aux utilisateurs.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Camera
from ..schemas import StreamUrlOut, ZoneOut
from ..security import decrypt_rtsp_url

router = APIRouter(prefix="/internal/cameras", tags=["internal"])


async def _camera_or_404(camera_id: str, session: AsyncSession) -> Camera:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


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
    camera = await _camera_or_404(camera_id, session)
    return camera.settings or {}
