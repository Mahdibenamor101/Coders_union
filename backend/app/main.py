import asyncio
import contextlib
import logging
import secrets

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, get_engine
from .events import ALERTS_FEED_CHANNEL, run_worker_event_listener
from .routers import alerts, cameras, clips, stats, stores, tenants
from .security import require_api_key

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1 : create_all suffit ; Alembic prendra le relais quand le schéma évoluera.
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    listener = asyncio.create_task(run_worker_event_listener())
    yield
    listener.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listener


app = FastAPI(title="Surveillance SaaS API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    tenants.router,
    stores.router,
    cameras.router,
    clips.router,
    alerts.router,
    stats.router,
):
    app.include_router(router, dependencies=[Depends(require_api_key)])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/alerts")
async def alerts_websocket(websocket: WebSocket, api_key: str = Query(default="")):
    """Flux temps réel des alertes (relaie le canal Redis `alerts_feed`).

    Phase 4 : auth par clé API en query string ; remplacée par JWT en Phase 5.
    """
    await websocket.accept()
    if not secrets.compare_digest(api_key, get_settings().api_key):
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
            await websocket.send_text(
                data.decode() if isinstance(data, bytes) else data
            )

    async def watch_client():
        # Détecte la déconnexion du client (les messages entrants sont ignorés).
        while True:
            await websocket.receive_text()

    tasks = [
        asyncio.create_task(forward_alerts()),
        asyncio.create_task(watch_client()),
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
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
