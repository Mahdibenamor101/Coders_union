from sqlalchemy import select

from app.models import Camera
from app.security import decrypt_rtsp_url

from .conftest import create_camera, register


async def test_health_is_open(client):
    response = await client.get("/health", headers={"X-API-Key": ""})
    assert response.status_code == 200


async def test_user_endpoints_require_jwt(client):
    # La clé de service ne donne PAS accès aux endpoints utilisateurs.
    assert (await client.get("/stores")).status_code == 401
    assert (await client.get("/alerts")).status_code == 401
    assert (
        await client.get("/stores", headers={"Authorization": "Bearer bidon"})
    ).status_code == 401


async def test_tenant_me_and_retention_cap(client):
    auth = await register(client, company="Pharma Plus")
    tenant = (await client.get("/tenant", headers=auth["headers"])).json()
    assert tenant["name"] == "Pharma Plus"
    assert tenant["retention_days"] == 30

    # RGPD : rétention plafonnée à 90 jours.
    response = await client.patch(
        "/tenant", json={"retention_days": 120}, headers=auth["headers"]
    )
    assert response.status_code == 422

    updated = (
        await client.patch(
            "/tenant", json={"retention_days": 60}, headers=auth["headers"]
        )
    ).json()
    assert updated["retention_days"] == 60


async def test_store_crud_scoped_to_tenant(client):
    auth = await register(client)
    store = (
        await client.post("/stores", json={"name": "Mag A"}, headers=auth["headers"])
    ).json()

    listed = (await client.get("/stores", headers=auth["headers"])).json()
    assert [s["id"] for s in listed] == [store["id"]]

    assert (
        await client.delete(f"/stores/{store['id']}", headers=auth["headers"])
    ).status_code == 204
    assert (
        await client.get(f"/stores/{store['id']}", headers=auth["headers"])
    ).status_code == 404


async def test_camera_rtsp_url_encrypted_and_never_exposed(client, db_sessionmaker):
    plain_url = "rtsp://admin:secret@192.168.1.10:554/stream"
    camera, auth = await create_camera(client, rtsp_url=plain_url)

    assert "rtsp_url" not in camera
    detail = (
        await client.get(f"/cameras/{camera['id']}", headers=auth["headers"])
    ).json()
    assert "rtsp_url" not in detail

    async with db_sessionmaker() as session:
        row = (await session.execute(select(Camera))).scalar_one()
    assert plain_url not in row.rtsp_url_encrypted
    assert decrypt_rtsp_url(row.rtsp_url_encrypted) == plain_url


async def test_internal_stream_url_requires_service_key(client):
    camera, _auth = await create_camera(client, rtsp_url="rtsp://cam/42")

    # Avec la clé de service (header par défaut du client de test) : OK.
    stream = (await client.get(f"/internal/cameras/{camera['id']}/stream-url")).json()
    assert stream["rtsp_url"] == "rtsp://cam/42"

    # Sans clé valide : refusé.
    response = await client.get(
        f"/internal/cameras/{camera['id']}/stream-url",
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401


async def test_clip_request_publishes_command(client, fake_redis):
    camera, auth = await create_camera(client)

    response = await client.post(
        f"/cameras/{camera['id']}/clip",
        json={"event_ts": 1000.0},
        headers=auth["headers"],
    )
    assert response.status_code == 202
    clip = response.json()
    assert clip["status"] == "pending"

    assert len(fake_redis.published) == 1
    channel, command = fake_redis.published[0]
    assert channel == f"camera_commands:{camera['id']}"
    assert command["action"] == "extract_clip"
    assert command["clip_id"] == clip["id"]

    listed = (
        await client.get(f"/cameras/{camera['id']}/clips", headers=auth["headers"])
    ).json()
    assert [c["id"] for c in listed] == [clip["id"]]


async def test_clip_url_requires_ready_status(client, fake_redis):
    camera, auth = await create_camera(client)
    clip = (
        await client.post(
            f"/cameras/{camera['id']}/clip", json={}, headers=auth["headers"]
        )
    ).json()
    response = await client.get(f"/clips/{clip['id']}/url", headers=auth["headers"])
    assert response.status_code == 409
