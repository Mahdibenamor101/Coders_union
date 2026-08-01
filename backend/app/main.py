import asyncio
import contextlib
import json
import logging
import secrets as pysecrets

import jwt as pyjwt
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, get_engine
from .events import ALERTS_FEED_CHANNEL, run_worker_event_listener
from .retention import retention_loop
from .routers import (
    alerts,
    auth,
    billing,
    cameras,
    clips,
    gdpr,
    internal,
    stats,
    stores,
    tenants,
)
from .security import decode_access_token, require_api_key

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    tasks = [
        asyncio.create_task(run_worker_event_listener()),
        asyncio.create_task(retention_loop()),
    ]
    yield
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Surveillance SaaS API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoints utilisateurs : auth JWT gérée par endpoint (scoping tenant + rôles).
for router in (
    auth.router,
    tenants.router,
    stores.router,
    cameras.router,
    clips.router,
    alerts.router,
    stats.router,
    billing.router,
    gdpr.router,
):
    app.include_router(router)

# Endpoints de service (workers) : clé API.
app.include_router(internal.router, dependencies=[Depends(require_api_key)])


@app.get("/health")
async def health():
    return {"status": "ok"}


def _websocket_tenant(api_key: str, token: str) -> tuple[bool, str | None]:
    """Retourne (autorisé, tenant_id ou None pour un accès service global)."""
    settings = get_settings()
    if api_key and pysecrets.compare_digest(api_key, settings.api_key):
        return True, None
    if token:
        try:
            payload = decode_access_token(token)
            return True, payload.get("tenant_id")
        except pyjwt.PyJWTError:
            return False, None
    return False, None


@app.websocket("/ws/alerts")
async def alerts_websocket(
    websocket: WebSocket,
    api_key: str = Query(default=""),
    token: str = Query(default=""),
):
    """Flux temps réel des alertes (canal Redis `alerts_feed`).

    Auth : JWT utilisateur (`token`) — filtré sur son tenant — ou clé de
    service (`api_key`) qui voit tout.
    """
    await websocket.accept()
    authorized, tenant_filter = _websocket_tenant(api_key, token)
    if not authorized:
        await websocket.close(code=4401)
        return

    client = aioredis.from_url(get_settings().redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(ALERTS_FEED_CHANNEL)

    async def forward_alerts():
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message["data"]
            text = data.decode() if isinstance(data, bytes) else data
            if tenant_filter is not None:
                try:
                    if json.loads(text).get("tenant_id") != tenant_filter:
                        continue
                except ValueError:
                    continue
            await websocket.send_text(text)

    async def watch_client():
        while True:
            await websocket.receive_text()

    tasks = [
        asyncio.create_task(forward_alerts()),
        asyncio.create_task(watch_client()),
    ]
    try:
        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.warning("alerts websocket ended: %r", exc)
    finally:
        for task in tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            await pubsub.aclose()
            await client.aclose()
