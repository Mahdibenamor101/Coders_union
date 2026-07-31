from sqlalchemy import select

from app.models import Camera
from app.security import decrypt_rtsp_url

from .conftest import create_camera


async def test_health_does_not_require_api_key(client):
    response = await client.get("/health", headers={"X-API-Key": ""})
    assert response.status_code == 200


async def test_endpoints_require_api_key(client):
    response = await client.get("/tenants", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


async def test_tenant_crud(client):
    created = (await client.post("/tenants", json={"name": "Pharma Plus"})).json()
    assert created["retention_days"] == 30
    assert created["plan"] == "starter"

    listed = (await client.get("/tenants")).json()
    assert [t["id"] for t in listed] == [created["id"]]

    # RGPD : rétention plafonnée à 90 jours.
    response = await client.patch(
        f"/tenants/{created['id']}", json={"retention_days": 120}
    )
    assert response.status_code == 422

    updated = (
        await client.patch(f"/tenants/{created['id']}", json={"retention_days": 60})
    ).json()
    assert updated["retention_days"] == 60

    assert (await client.delete(f"/tenants/{created['id']}")).status_code == 204
    assert (await client.get(f"/tenants/{created['id']}")).status_code == 404


async def test_store_requires_existing_tenant(client):
    response = await client.post(
        "/stores", json={"tenant_id": "nope", "name": "Fantôme"}
    )
    assert response.status_code == 404


async def test_store_list_filtered_by_tenant(client):
    tenant_a = (await client.post("/tenants", json={"name": "A"})).json()
    tenant_b = (await client.post("/tenants", json={"name": "B"})).json()
    await client.post("/stores", json={"tenant_id": tenant_a["id"], "name": "Mag A"})
    await client.post("/stores", json={"tenant_id": tenant_b["id"], "name": "Mag B"})

    stores_a = (await client.get(f"/stores?tenant_id={tenant_a['id']}")).json()
    assert [s["name"] for s in stores_a] == ["Mag A"]


async def test_camera_rtsp_url_encrypted_and_never_exposed(client, db_sessionmaker):
    plain_url = "rtsp://admin:secret@192.168.1.10:554/stream"
    camera = await create_camera(client, rtsp_url=plain_url)

    # Jamais d'URL RTSP dans les réponses CRUD.
    assert "rtsp_url" not in camera
    detail = (await client.get(f"/cameras/{camera['id']}")).json()
    assert "rtsp_url" not in detail

    # Chiffrée au repos, déchiffrable avec la clé.
    async with db_sessionmaker() as session:
        row = (await session.execute(select(Camera))).scalar_one()
    assert plain_url not in row.rtsp_url_encrypted
    assert decrypt_rtsp_url(row.rtsp_url_encrypted) == plain_url

    # L'endpoint worker renvoie l'URL en clair (protégé par clé API).
    stream = (await client.get(f"/cameras/{camera['id']}/stream-url")).json()
    assert stream["rtsp_url"] == plain_url


async def test_camera_rtsp_url_update_reencrypts(client, db_sessionmaker):
    camera = await create_camera(client, rtsp_url="rtsp://old/1")
    await client.patch(f"/cameras/{camera['id']}", json={"rtsp_url": "rtsp://new/2"})
    stream = (await client.get(f"/cameras/{camera['id']}/stream-url")).json()
    assert stream["rtsp_url"] == "rtsp://new/2"


async def test_clip_request_publishes_command(client, fake_redis):
    camera = await create_camera(client)

    response = await client.post(
        f"/cameras/{camera['id']}/clip", json={"event_ts": 1000.0}
    )
    assert response.status_code == 202
    clip = response.json()
    assert clip["status"] == "pending"

    assert len(fake_redis.published) == 1
    channel, command = fake_redis.published[0]
    assert channel == f"camera_commands:{camera['id']}"
    assert command["action"] == "extract_clip"
    assert command["clip_id"] == clip["id"]
    assert command["event_ts"] == 1000.0
    assert command["pre_seconds"] == 20
    assert command["post_seconds"] == 20

    listed = (await client.get(f"/cameras/{camera['id']}/clips")).json()
    assert [c["id"] for c in listed] == [clip["id"]]


async def test_clip_url_requires_ready_status(client, fake_redis):
    camera = await create_camera(client)
    clip = (await client.post(f"/cameras/{camera['id']}/clip", json={})).json()
    response = await client.get(f"/clips/{clip['id']}/url")
    assert response.status_code == 409


async def test_clip_for_unknown_camera_is_404(client):
    response = await client.post("/cameras/unknown/clip", json={})
    assert response.status_code == 404
