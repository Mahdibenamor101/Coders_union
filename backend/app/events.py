import asyncio
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_sessionmaker
from .models import Camera, Clip
from .redis_client import WORKER_EVENTS_CHANNEL

logger = logging.getLogger(__name__)


async def handle_worker_event(session: AsyncSession, payload: dict) -> None:
    event_type = payload.get("type")

    if event_type in ("clip_ready", "clip_failed"):
        clip = await session.get(Clip, payload.get("clip_id"))
        if clip is None:
            logger.warning("event for unknown clip: %s", payload.get("clip_id"))
            return
        if event_type == "clip_ready":
            clip.status = "ready"
            clip.object_key = payload.get("object_key")
            clip.duration_seconds = payload.get("duration_seconds")
        else:
            clip.status = "failed"
            clip.error = payload.get("error", "unknown error")
        await session.commit()

    elif event_type == "camera_status":
        camera = await session.get(Camera, payload.get("camera_id"))
        if camera is None:
            logger.warning("status for unknown camera: %s", payload.get("camera_id"))
            return
        camera.status = payload.get("status", "offline")
        camera.last_seen_at = datetime.now(timezone.utc)
        await session.commit()


async def run_worker_event_listener() -> None:
    """Écoute les événements des workers sur Redis et les persiste en base."""
    settings = get_settings()
    while True:
        try:
            client = aioredis.from_url(settings.redis_url)
            pubsub = client.pubsub()
            await pubsub.subscribe(WORKER_EVENTS_CHANNEL)
            logger.info("listening on Redis channel %r", WORKER_EVENTS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    async with get_sessionmaker()() as session:
                        await handle_worker_event(session, payload)
                except Exception:
                    logger.exception("failed to process worker event")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker event listener error, retrying in 2s")
            await asyncio.sleep(2)
