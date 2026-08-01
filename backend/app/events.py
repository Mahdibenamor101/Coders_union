import asyncio
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_sessionmaker
from .models import Alert, Camera, Clip, Store
from .redis_client import WORKER_EVENTS_CHANNEL

logger = logging.getLogger(__name__)

ALERTS_FEED_CHANNEL = "alerts_feed"

# handle_worker_event retourne des (canal, payload) à rediffuser (ex. flux
# d'alertes pour le dashboard) ; le listener s'en charge.
Broadcast = tuple[str, dict]


async def handle_worker_event(session: AsyncSession, payload: dict) -> list[Broadcast]:
    event_type = payload.get("type")

    if event_type in ("clip_ready", "clip_failed"):
        clip = await session.get(Clip, payload.get("clip_id"))
        if clip is None:
            logger.warning("event for unknown clip: %s", payload.get("clip_id"))
            return []
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
            return []
        camera.status = payload.get("status", "offline")
        camera.last_seen_at = datetime.now(timezone.utc)
        await session.commit()

    elif event_type == "behavior_alert":
        camera = await session.get(Camera, payload.get("camera_id"))
        if camera is None:
            logger.warning("alert for unknown camera: %s", payload.get("camera_id"))
            return []
        data = payload.get("alert", {})
        alert = Alert(
            camera_id=camera.id,
            rule=data.get("rule", "inconnu"),
            severity=data.get("severity", "low"),
            score=float(data.get("score", 0)),
            event_ts=datetime.fromtimestamp(
                float(data.get("event_ts", 0)), tz=timezone.utc
            ),
            clip_object_key=data.get("clip_object_key"),
            thumbnail_object_key=data.get("thumbnail_object_key"),
            evidence=data.get("evidence", []),
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        logger.warning(
            "alert stored: %s rule=%s severity=%s score=%.1f",
            alert.id,
            alert.rule,
            alert.severity,
            alert.score,
        )
        store = await session.get(Store, camera.store_id)
        return [
            (
                ALERTS_FEED_CHANNEL,
                {
                    "type": "alert_created",
                    "alert_id": alert.id,
                    "camera_id": alert.camera_id,
                    # Permet au WebSocket de ne diffuser qu'aux clients du tenant.
                    "tenant_id": store.tenant_id if store else None,
                    "rule": alert.rule,
                    "severity": alert.severity,
                    "score": alert.score,
                    "event_ts": data.get("event_ts"),
                },
            )
        ]

    return []


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
                        broadcasts = await handle_worker_event(session, payload)
                    for channel, broadcast in broadcasts:
                        await client.publish(channel, json.dumps(broadcast))
                except Exception:
                    logger.exception("failed to process worker event")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker event listener error, retrying in 2s")
            await asyncio.sleep(2)
