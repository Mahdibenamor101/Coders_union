import json
import os

from cryptography.fernet import Fernet

# Les settings sont lus à l'import de l'app : l'environnement doit être posé avant.
os.environ["API_KEY"] = "test-key"
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.redis_client import get_redis_client


class FakeRedis:
    """Capture les publications Redis pour vérification dans les tests."""

    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, json.loads(message)))


@pytest_asyncio.fixture
async def db_sessionmaker():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest_asyncio.fixture
async def client(db_sessionmaker, fake_redis):
    async def override_session():
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": "test-key"},
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


async def create_camera(client, name="Cam entrée", rtsp_url="rtsp://user:pass@cam/1"):
    """Raccourci : crée tenant → magasin → caméra, retourne la caméra."""
    tenant = (await client.post("/tenants", json={"name": "Boutique SARL"})).json()
    store = (
        await client.post(
            "/stores", json={"tenant_id": tenant["id"], "name": "Magasin centre"}
        )
    ).json()
    response = await client.post(
        "/cameras",
        json={"store_id": store["id"], "name": name, "rtsp_url": rtsp_url},
    )
    assert response.status_code == 201
    return response.json()
