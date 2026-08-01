"""Job de rétention RGPD : purge automatique des clips et alertes expirés.

La durée de rétention est celle du tenant (30 jours par défaut, 90 max).
Tourne périodiquement dans l'API (SPEC §2 : suppression automatique planifiée).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_sessionmaker
from .models import Alert, Camera, Clip, Store, Tenant
from .s3 import delete_object

logger = logging.getLogger(__name__)


async def run_retention_cleanup(
    session: AsyncSession, delete_media=delete_object
) -> dict:
    """Supprime clips et alertes plus vieux que la rétention de leur tenant."""
    deleted = {"clips": 0, "alerts": 0}
    now = datetime.now(timezone.utc)

    tenants = (await session.execute(select(Tenant))).scalars().all()
    for tenant in tenants:
        cutoff = now - timedelta(days=tenant.retention_days)

        clips = (
            await session.execute(
                select(Clip)
                .join(Camera, Clip.camera_id == Camera.id)
                .join(Store, Camera.store_id == Store.id)
                .where(Store.tenant_id == tenant.id, Clip.created_at < cutoff)
            )
        ).scalars().all()
        for clip in clips:
            if clip.object_key:
                delete_media(clip.object_key)
            await session.delete(clip)
            deleted["clips"] += 1

        alerts = (
            await session.execute(
                select(Alert)
                .join(Camera, Alert.camera_id == Camera.id)
                .join(Store, Camera.store_id == Store.id)
                .where(Store.tenant_id == tenant.id, Alert.created_at < cutoff)
            )
        ).scalars().all()
        for alert in alerts:
            for key in (alert.clip_object_key, alert.thumbnail_object_key):
                if key:
                    delete_media(key)
            await session.delete(alert)
            deleted["alerts"] += 1

    await session.commit()
    return deleted


async def retention_loop() -> None:
    interval = get_settings().retention_interval_seconds
    while True:
        try:
            async with get_sessionmaker()() as session:
                deleted = await run_retention_cleanup(session)
            if deleted["clips"] or deleted["alerts"]:
                logger.info(
                    "retention cleanup: %d clips, %d alerts deleted",
                    deleted["clips"],
                    deleted["alerts"],
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("retention cleanup failed")
        await asyncio.sleep(interval)
