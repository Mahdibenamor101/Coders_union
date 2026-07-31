import asyncio
import contextlib
import logging

from fastapi import Depends, FastAPI

from .db import Base, get_engine
from .events import run_worker_event_listener
from .routers import cameras, clips, stores, tenants
from .security import require_api_key

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


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

for router in (tenants.router, stores.router, cameras.router, clips.router):
    app.include_router(router, dependencies=[Depends(require_api_key)])


@app.get("/health")
async def health():
    return {"status": "ok"}
