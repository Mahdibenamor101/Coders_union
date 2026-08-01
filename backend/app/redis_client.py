import redis.asyncio as aioredis

from .config import get_settings

WORKER_EVENTS_CHANNEL = "worker_events"

_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(get_settings().redis_url)
    return _client


def camera_commands_channel(camera_id: str) -> str:
    return f"camera_commands:{camera_id}"
